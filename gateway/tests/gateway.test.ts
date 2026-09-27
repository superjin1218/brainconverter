import {env} from "cloudflare:workers";
import {runInDurableObject, runDurableObjectAlarm, evictDurableObject} from "cloudflare:test";
import {beforeAll, beforeEach, afterEach, describe, expect, it, vi} from "vitest";
import {exportJWK, generateKeyPair, SignJWT} from "jose";
import worker from "../src/index";
import {hexDigest, type Env} from "../src/shared";

const bindings = env as unknown as Env;
const secret = bindings.GATEWAY_SHARED_SECRET;
let keys: Awaited<ReturnType<typeof generateKeyPair>>;
let publicKey: Awaited<ReturnType<typeof exportJWK>>;
let replies: {delay: number; status: number}[] = [];
beforeAll(async () => {
  keys = await generateKeyPair("RS256", {extractable: true});
  publicKey = await exportJWK(keys.publicKey);
});
beforeEach(async () => {
  replies = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input instanceof Request ? input.url : input);
    if (url === "https://brain-test.cloudflareaccess.com/cdn-cgi/access/certs")
      return Response.json({keys: [{...publicKey, kid: "test", alg: "RS256"}]});
    if (url !== "https://brain-test.run.app/api/convert") throw new Error("Unexpected network request");
    const next = replies.shift();
    if (!next) throw new Error("No backend reply queued");
    const headers = new Headers(init?.headers);
    const prefix = `${headers.get("x-gateway-timestamp")}\nPOST\n/api/convert\n${headers.get("x-user-email")}\n${headers.get("x-request-id")}\n`;
    expect(headers.get("x-gateway-signature")).toBe(await hexDigest(prefix + init?.body, secret));
    if (next.delay) await new Promise(resolve => setTimeout(resolve, next.delay));
    return Response.json(next.status === 200 ? {status: "PASS", usage: {costMicrousd: 3510}} :
      {detail: "private upstream error"}, {status: next.status});
  });
  const stub = bindings.PILOT.get(bindings.PILOT.idFromName("q-lab-pilot-v1"));
  await runInDurableObject(stub, async (_instance, state) => {
    await state.storage.deleteAll();
    await state.storage.deleteAlarm();
  });
});
afterEach(() => { expect(replies).toHaveLength(0); vi.restoreAllMocks(); });

async function token(email = "member@example.com", audience = bindings.ACCESS_AUD, expires = "1h") {
  return new SignJWT({email}).setProtectedHeader({alg: "RS256", kid: "test"})
    .setIssuedAt().setExpirationTime(expires).setIssuer(`https://${bindings.ACCESS_TEAM_DOMAIN}`)
    .setAudience(audience).sign(keys.privateKey);
}
async function request(path = "/api/usage", options: {email?: string; body?: string; key?: string; token?: string} = {}) {
  const headers: Record<string, string> = {"Cf-Access-Jwt-Assertion": options.token ?? await token(options.email)};
  if (options.body !== undefined) {
    headers["content-type"] = "application/json";
    headers["idempotency-key"] = options.key ?? crypto.randomUUID();
  }
  const response = await worker.fetch(new Request(`https://club.example${path}`, {
    method: options.body === undefined ? "GET" : "POST", headers, body: options.body,
  }), bindings);
  // Drain the DO response stream, as a browser's response.json() would, before eviction.
  return new Response(await response.arrayBuffer(), {status: response.status, headers: response.headers});
}
const body = JSON.stringify({strategy: "최근 5일 동안 많이 떨어진 종목"});
async function finished(id: string) {
  for (let i = 0; i < 100; i++) {
    const response = await request(`/api/jobs/${id}`);
    if (response.status !== 202) return response;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error("job did not finish");
}
function backend(delay = 0, status = 200) {
  replies.push({delay, status});
}

describe("authentication and request boundary", () => {
  it("rejects forged email headers", async () => {
    const response = await worker.fetch(new Request("https://club.example/api/usage", {
      headers: {"Cf-Access-Authenticated-User-Email": "member@example.com"},
    }), bindings);
    expect(response.status).toBe(401);
  });
  it("checks audience, expiration and allowlist", async () => {
    expect((await request("/api/usage", {token: await token(undefined, "other")})).status).toBe(401);
    expect((await request("/api/usage", {token: await token(undefined, undefined, "-1h")})).status).toBe(401);
    expect((await request("/api/usage", {email: "outsider@example.com"})).status).toBe(401);
  });
  it("denies members access to admin and arbitrary proxy paths", async () => {
    expect((await request("/api/admin/usage")).status).toBe(403);
    expect((await request("//evil.example/path")).status).toBe(404);
    expect((await request("/openapi.json")).status).toBe(404);
  });
  it("validates size and strategy before billing", async () => {
    expect((await request("/api/convert", {body: "x".repeat(17000)})).status).toBe(413);
    expect((await request("/api/convert", {body: JSON.stringify({strategy: "x".repeat(2001)})})).status).toBe(422);
    const usage = await (await request()).json() as {monthlyUsed: number};
    expect(usage.monthlyUsed).toBe(0);
  });
});

describe("durable quota and idempotency", () => {
  it("charges a concurrent duplicate once and caches its result", async () => {
    backend(20);
    const key = crypto.randomUUID();
    const responses = await Promise.all([request("/api/convert", {body, key}), request("/api/convert", {body, key})]);
    expect(responses.every(response => [200, 202].includes(response.status))).toBe(true);
    expect((await finished(key)).status).toBe(200);
    expect((await request("/api/convert", {body, key})).status).toBe(200);
    const usage = await (await request()).json() as {monthlyUsed: number};
    expect(usage.monthlyUsed).toBe(1);
    expect((await request("/api/convert", {body: JSON.stringify({strategy: "다른 전략입니다"}), key})).status).toBe(409);
    expect((await request(`/api/jobs/${key}`, {email: "admin@example.com"})).status).toBe(404);
  });
  it("caps global concurrency at two even across members", async () => {
    backend(100); backend(100);
    const keys = [crypto.randomUUID(), crypto.randomUUID()];
    expect((await request("/api/convert", {body, key: keys[0]})).status).toBe(202);
    expect((await request("/api/convert", {body, key: keys[1], email: "admin@example.com"})).status).toBe(202);
    expect((await request("/api/convert", {body})).status).toBe(503);
    await finished(keys[0]);
    // Wait for the admin job as well before resetting storage.
    const admin = await token("admin@example.com");
    for (let i = 0; i < 100; i++) {
      if ((await request(`/api/jobs/${keys[1]}`, {token: admin})).status !== 202) break;
      await new Promise(resolve => setTimeout(resolve, 10));
    }
  });
  it("enforces monthly quota and budget atomically", async () => {
    const member = await hexDigest("member:member@example.com", secret);
    const month = new Date().toISOString().slice(0, 7);
    const stub = bindings.PILOT.get(bindings.PILOT.idFromName("q-lab-pilot-v1"));
    const base = {month, requests: 50, cost: 0, passed: 0, rejected: 0, errors: 0, active: {}, latencies: []};
    await runInDurableObject(stub, async (_, state) => state.storage.put("ledger", {...base,
      members: {[member]: {month, day: "old", minute: "old", monthly: 50, daily: 0, minutely: 0}},
    }));
    expect((await request("/api/convert", {body})).status).toBe(429);
    await runInDurableObject(stub, async (_, state) => state.storage.put("ledger", {...base, cost: 9_950_000, members: {}}));
    expect((await request("/api/convert", {body})).status).toBe(429);
  });
  it("retains cost reservation on upstream failure and never exposes its body", async () => {
    backend(0, 500);
    const key = crypto.randomUUID();
    await request("/api/convert", {body, key});
    const response = await finished(key);
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private");
    const usage = await (await request("/api/admin/usage", {email: "admin@example.com"})).json() as {costMicrousd: number};
    expect(usage.costMicrousd).toBe(100_000);
  });
  it("persists completed jobs and quota after eviction", async () => {
    backend();
    const key = crypto.randomUUID();
    await request("/api/convert", {body, key});
    await finished(key);
    const stub = bindings.PILOT.get(bindings.PILOT.idFromName("q-lab-pilot-v1"));
    await evictDurableObject(stub);
    expect((await request("/api/convert", {body, key})).status).toBe(200);
    const usage = await (await request()).json() as {monthlyUsed: number};
    expect(usage.monthlyUsed).toBe(1);
    const admin = await (await request("/api/admin/usage", {email: "admin@example.com"})).json() as {costMicrousd: number};
    expect(admin.costMicrousd).toBe(3510);
  });
  it("blocks access to expired cache and deletes it via alarm", async () => {
    const id = crypto.randomUUID();
    const member = await hexDigest("member:member@example.com", secret);
    const key = `job:${member}:${id}`;
    const stub = bindings.PILOT.get(bindings.PILOT.idFromName("q-lab-pilot-v1"));
    await runInDurableObject(stub, async (_, state) => {
      await state.storage.put(key, {state: "done", expires: Date.now() - 1, result: {private: true}, status: 200});
      await state.storage.setAlarm(Date.now() + 60000);
    });
    expect((await request(`/api/jobs/${id}`)).status).toBe(404);
    await runDurableObjectAlarm(stub);
    await runInDurableObject(stub, async (_, state) => expect(await state.storage.get(key)).toBeUndefined());
  });
});
