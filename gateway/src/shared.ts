export interface Env {
  PILOT: DurableObjectNamespace;
  BACKEND_URL: string;
  GATEWAY_SHARED_SECRET: string;
  ACCESS_TEAM_DOMAIN: string;
  ACCESS_AUD: string;
  ALLOWED_EMAILS: string;
  ADMIN_EMAILS?: string;
  MONTHLY_LIMIT?: string;
  MEMBER_MONTHLY_LIMITS?: string;
  DAILY_LIMIT?: string;
  GLOBAL_MONTHLY_LIMIT?: string;
  MONTHLY_BUDGET_USD?: string;
  SERVICE_ENABLED?: string;
}
export function json(data: unknown, status = 200): Response {
  return Response.json(data, {status, headers: {"Cache-Control": "no-store"}});
}
export function failure(detail: string, status: number): Response { return json({detail}, status); }
export function emails(value = ""): string[] {
  return value.split(",").map(item => item.trim().toLowerCase()).filter(Boolean);
}
export function limit(value: string | undefined, fallback: number): number {
  const n = Number(value ?? fallback);
  if (!Number.isInteger(n) || n < 1) throw new Error("Invalid limit configuration");
  return n;
}
export function memberMonthlyLimit(env: Env, email: string): number {
  const overrides = JSON.parse(env.MEMBER_MONTHLY_LIMITS || "{}");
  return limit(Object.hasOwn(overrides, email) ? String(overrides[email]) : env.MONTHLY_LIMIT, 50);
}
export async function hexDigest(text: string, secret?: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  let digest: ArrayBuffer;
  if (secret) {
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret),
      {name: "HMAC", hash: "SHA-256"}, false, ["sign"]);
    digest = await crypto.subtle.sign("HMAC", key, bytes);
  } else { digest = await crypto.subtle.digest("SHA-256", bytes); }
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}
export async function readLimited(request: Request, maximum = 16384): Promise<string> {
  if (Number(request.headers.get("content-length")) > maximum) throw new Error("size");
  const reader = request.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maximum) { await reader.cancel(); throw new Error("size"); }
    chunks.push(value);
  }
  const joined = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.length; }
  return new TextDecoder("utf-8", {fatal: true, ignoreBOM: false}).decode(joined);
}
export function backendUrl(env: Env, path: string): URL {
  const url = new URL(env.BACKEND_URL);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash ||
      url.pathname !== "/" || !url.hostname.endsWith(".run.app")) throw new Error("Invalid backend");
  url.pathname = path;
  return url;
}
