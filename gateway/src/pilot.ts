import {DurableObject} from "cloudflare:workers";
import {backendUrl, emails, failure, hexDigest, json, limit, memberMonthlyLimit, type Env} from "./shared";

const RESERVE = 100_000; // $0.10: 6 agents × 2 bounded model attempts.
const TTL = 24 * 60 * 60 * 1000;
interface Counter {month: string; day: string; minute: string; monthly: number; daily: number; minutely: number}
interface Ledger {
  month: string; requests: number; cost: number; passed: number; rejected: number; errors: number;
  members: Record<string, Counter>; active: Record<string, number>; latencies: number[];
}
interface Job {
  hash: string; state: "pending" | "done"; expires: number; lease: number; month: string;
  result?: unknown; status?: number;
}
function periods(now: number) {
  const iso = new Date(now).toISOString();
  return {month: iso.slice(0, 7), day: iso.slice(0, 10), minute: iso.slice(0, 16)};
}
function fresh(now: number): Ledger {
  return {month: periods(now).month, requests: 0, cost: 0, passed: 0, rejected: 0, errors: 0,
    members: {}, active: {}, latencies: []};
}

export class PilotCoordinator extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    const path = new URL(request.url).pathname;
    const member = request.headers.get("x-member-id")!;
    if (path === "/api/usage" || path === "/api/admin/usage") {
      const ledger = await this.current(now);
      if (path === "/api/admin/usage") {
        const members = await Promise.all(emails(this.env.ALLOWED_EMAILS).map(async email => {
          const id = await hexDigest(`member:${email}`, this.env.GATEWAY_SHARED_SECRET);
          return {email, used: ledger.members[id]?.monthly ?? 0};
        }));
        const sorted = [...ledger.latencies].sort((a, b) => a - b);
        return json({month: ledger.month, requests: ledger.requests, costMicrousd: ledger.cost,
          passed: ledger.passed, rejected: ledger.rejected, errors: ledger.errors,
          p95Ms: sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? 0, members});
      }
      const counter = ledger.members[member];
      const monthlyLimit = memberMonthlyLimit(this.env, request.headers.get("x-member")!);
      return json({monthlyLimit, monthlyUsed: counter?.monthly ?? 0,
        monthlyRemaining: Math.max(0, monthlyLimit - (counter?.monthly ?? 0)),
        dailyLimit: limit(this.env.DAILY_LIMIT, 20),
        dailyUsed: counter?.day === periods(now).day ? counter.daily : 0,
        admin: emails(this.env.ADMIN_EMAILS).includes(request.headers.get("x-member")!),
        resetTimezone: "UTC"});
    }
    if (path.startsWith("/api/jobs/")) {
      const key = `job:${member}:${path.split("/").at(-1)}`;
      return this.jobResponse(await this.ctx.storage.get<Job>(key), now);
    }
    const body = await request.text();
    const hash = await hexDigest(body);
    const id = request.headers.get("idempotency-key")!;
    const key = `job:${member}:${id}`;
    const decision = await this.ctx.storage.transaction(async txn => {
      const existing = await txn.get<Job>(key);
      if (existing && existing.expires > now) {
        if (existing.hash !== hash) return {response: failure("같은 요청 ID에 다른 입력을 사용할 수 없습니다.", 409)};
        return {response: this.jobResponse(existing, now)};
      }
      if (this.env.SERVICE_ENABLED === "false") return {response: failure("운영자가 변환을 일시 중지했습니다.", 503)};
      const ledger = await this.current(now, txn);
      for (const [active, lease] of Object.entries(ledger.active)) if (lease < now) delete ledger.active[active];
      if (Object.keys(ledger.active).length >= 2) return {response: failure("두 요청을 처리 중입니다. 잠시 후 다시 시도하세요.", 503)};
      const p = periods(now);
      const counter = ledger.members[member] ?? {...p, monthly: 0, daily: 0, minutely: 0};
      if (counter.day !== p.day) {counter.day = p.day; counter.daily = 0;}
      if (counter.minute !== p.minute) {counter.minute = p.minute; counter.minutely = 0;}
      if (counter.minutely >= 2 || counter.daily >= limit(this.env.DAILY_LIMIT, 20) ||
          counter.monthly >= memberMonthlyLimit(this.env, request.headers.get("x-member")!))
        return {response: failure("사용 한도에 도달했습니다. 분당 2회·일일·월간 한도를 확인하세요.", 429)};
      const budget = Number(this.env.MONTHLY_BUDGET_USD ?? "10") * 1_000_000;
      if (!Number.isFinite(budget) || budget <= 0) return {response: failure("예산 설정이 필요합니다.", 503)};
      if (ledger.requests >= limit(this.env.GLOBAL_MONTHLY_LIMIT, 1000) || ledger.cost + RESERVE > budget)
        return {response: failure("이번 달 서비스 요청 또는 모델 예산 한도에 도달했습니다.", 429)};
      counter.monthly++; counter.daily++; counter.minutely++;
      ledger.members[member] = counter;
      ledger.requests++; ledger.cost += RESERVE;
      ledger.active[key] = now + 120_000;
      const job: Job = {hash, state: "pending", expires: now + TTL, lease: now + 120_000, month: p.month};
      await txn.put("ledger", ledger);
      await txn.put(key, job);
      return {job};
    });
    if (decision.response) return decision.response;
    await this.ctx.storage.setAlarm(now + 60_000);
    this.ctx.waitUntil(this.execute(key, decision.job!, body, request.headers.get("x-member")!, id));
    return json({status: "PENDING", jobId: id}, 202);
  }

  private jobResponse(job: Job | undefined, now: number): Response {
    if (!job || job.expires <= now) return failure("요청이 없거나 보관 기간이 지났습니다.", 404);
    if (job.state === "done") return json(job.result, job.status);
    if (job.lease <= now) return failure("중단된 요청입니다. 새 요청으로 다시 시도하세요.", 504);
    return json({status: "PENDING"}, 202);
  }

  private async current(now: number, storage: Pick<DurableObjectStorage, "get"> = this.ctx.storage): Promise<Ledger> {
    const ledger = await storage.get<Ledger>("ledger");
    if (!ledger || ledger.month !== periods(now).month) {
      const next = fresh(now);
      next.active = ledger?.active ?? {};
      return next;
    }
    return ledger;
  }

  private async execute(key: string, job: Job, body: string, email: string, id: string): Promise<void> {
    const started = Date.now();
    let result: unknown = {detail: "변환 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요."};
    let status = 503, actualCost = RESERVE;
    let outcome: "passed" | "rejected" | "errors" = "errors";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 55_000);
    try {
      const timestamp = String(Math.floor(Date.now() / 1000));
      const signature = await hexDigest(`${timestamp}\nPOST\n/api/convert\n${email}\n${id}\n${body}`, this.env.GATEWAY_SHARED_SECRET);
      const response = await fetch(backendUrl(this.env, "/api/convert"), {
        method: "POST", body, redirect: "manual", signal: controller.signal,
        headers: {"content-type": "application/json", "x-user-email": email, "x-request-id": id,
          "x-gateway-timestamp": timestamp, "x-gateway-signature": signature},
      });
      if (response.ok) {
        const data = await response.json() as {status: string; usage?: {costMicrousd?: number}};
        if (!["PASS", "REJECTED"].includes(data.status)) throw new Error("invalid bundle");
        const cost = data.usage?.costMicrousd;
        if (typeof cost === "number" && Number.isSafeInteger(cost) && cost >= 0) actualCost = cost;
        result = data; status = 200;
        outcome = data.status === "PASS" ? "passed" : "rejected";
      } else if (response.status === 422) {
        result = {detail: "전략 또는 시뮬레이션 설정을 확인하세요."}; status = 422; actualCost = 0;
      }
    } catch { /* Keep reservation for unknown billing; never log request content. */ }
    finally { clearTimeout(timer); }
    await this.ctx.storage.transaction(async txn => {
      const ledger = await this.current(Date.now(), txn);
      delete ledger.active[key];
      if (ledger.month === job.month) {
        ledger.cost += actualCost - RESERVE;
        ledger[outcome]++;
        ledger.latencies = [...ledger.latencies.slice(-999), Date.now() - started];
      }
      await txn.put("ledger", ledger);
      await txn.put(key, {...job, state: "done", result, status});
    });
  }

  async alarm(): Promise<void> {
    const now = Date.now();
    const jobs = await this.ctx.storage.list<Job>({prefix: "job:"});
    const expired = [...jobs].filter(([, job]) => job.expires <= now).map(([key]) => key);
    for (let i = 0; i < expired.length; i += 128) await this.ctx.storage.delete(expired.slice(i, i + 128));
    if (jobs.size > expired.length) await this.ctx.storage.setAlarm(now + 60_000);
  }
}
