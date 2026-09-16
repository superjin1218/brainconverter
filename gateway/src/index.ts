interface Env {
  QUOTA: KVNamespace;
  BACKEND_URL: string;
  GATEWAY_SHARED_SECRET: string;
}

const DAILY_LIMIT = 20;
const MINUTE_LIMIT = 2;

function json(detail: string, status: number): Response {
  return Response.json({ detail }, { status });
}

function utcDate(): string {
  return new Date().toISOString().slice(0, 10);
}

async function enforceQuota(env: Env, email: string): Promise<Response | null> {
  const now = Math.floor(Date.now() / 60000);
  const minuteKey = `minute:${email}:${now}`;
  const dailyKey = `daily:${email}:${utcDate()}`;
  const [minuteValue, dailyValue] = await Promise.all([
    env.QUOTA.get(minuteKey),
    env.QUOTA.get(dailyKey),
  ]);
  const minuteCount = Number(minuteValue || 0);
  const dailyCount = Number(dailyValue || 0);
  if (minuteCount >= MINUTE_LIMIT) return json("분당 요청 한도를 초과했습니다.", 429);
  if (dailyCount >= DAILY_LIMIT) return json("오늘의 요청 한도를 모두 사용했습니다.", 429);
  await Promise.all([
    env.QUOTA.put(minuteKey, String(minuteCount + 1), { expirationTtl: 120 }),
    env.QUOTA.put(dailyKey, String(dailyCount + 1), { expirationTtl: 172800 }),
  ]);
  return null;
}

async function hmacHex(secret: string, timestamp: string, body: ArrayBuffer): Promise<string> {
  const prefix = new TextEncoder().encode(`${timestamp}.`);
  const bytes = new Uint8Array(prefix.byteLength + body.byteLength);
  bytes.set(prefix, 0);
  bytes.set(new Uint8Array(body), prefix.byteLength);
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, bytes);
  return Array.from(new Uint8Array(signature), byte => byte.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!env.BACKEND_URL || !env.GATEWAY_SHARED_SECRET) {
      return json("Gateway 환경설정이 완료되지 않았습니다.", 503);
    }

    const email = request.headers.get("Cf-Access-Authenticated-User-Email")?.trim().toLowerCase();
    if (!email) return json("로그인이 필요합니다.", 401);

    const incomingUrl = new URL(request.url);
    const backendUrl = new URL(incomingUrl.pathname + incomingUrl.search, env.BACKEND_URL);
    const headers = new Headers(request.headers);
    headers.delete("authorization");
    headers.delete("cookie");
    headers.set("x-user-email", email);

    let body: ArrayBuffer | undefined;
    if (request.method !== "GET" && request.method !== "HEAD") {
      body = await request.arrayBuffer();
    }

    if (incomingUrl.pathname === "/api/convert") {
      if (request.method !== "POST") return json("허용되지 않은 요청 방식입니다.", 405);
      const quotaError = await enforceQuota(env, email);
      if (quotaError) return quotaError;
      const timestamp = String(Math.floor(Date.now() / 1000));
      const signature = await hmacHex(env.GATEWAY_SHARED_SECRET, timestamp, body || new ArrayBuffer(0));
      headers.set("x-gateway-timestamp", timestamp);
      headers.set("x-gateway-signature", signature);
    }

    const response = await fetch(backendUrl, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
    });
    const responseHeaders = new Headers(response.headers);
    responseHeaders.set("Cache-Control", incomingUrl.pathname.startsWith("/api/") ? "no-store" : "public, max-age=300");
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  },
};

