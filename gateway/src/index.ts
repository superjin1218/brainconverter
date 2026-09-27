import {authenticate} from "./auth";
import {backendUrl, emails, failure, hexDigest, readLimited, type Env} from "./shared";
export {PilotCoordinator} from "./pilot";
const ASSETS = new Set(["/", "/index.html", "/app.css", "/js/app.js", "/js/api.js",
  "/js/form.js", "/js/view.js", "/js/webmcp.js"]);
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 || !env.ALLOWED_EMAILS)
        return failure("서비스 계정 설정이 필요합니다.", 503);
      const email = await authenticate(request, env);
      if (!email) return failure("로그인 또는 회원 접근 권한을 확인하세요.", 401);
      const url = new URL(request.url);
      if (ASSETS.has(url.pathname) && request.method === "GET") {
        const response = await fetch(backendUrl(env, url.pathname), {redirect: "manual"});
        const headers = new Headers(response.headers);
        headers.set("Cache-Control", "private, no-store");
        return new Response(response.body, {status: response.status, headers});
      }
      if (!["/api/convert", "/api/usage", "/api/admin/usage"].includes(url.pathname) &&
          !/^\/api\/jobs\/[a-zA-Z0-9-]{16,64}$/.test(url.pathname)) return failure("없는 경로입니다.", 404);
      if (url.pathname === "/api/convert" && request.method !== "POST") return failure("POST 요청이 필요합니다.", 405);
      if (url.pathname !== "/api/convert" && request.method !== "GET") return failure("GET 요청이 필요합니다.", 405);
      if (url.pathname === "/api/admin/usage" && !emails(env.ADMIN_EMAILS).includes(email))
        return failure("운영진 권한이 필요합니다.", 403);
      const headers = new Headers({"x-member": email});
      headers.set("x-member-id", await hexDigest(`member:${email}`, env.GATEWAY_SHARED_SECRET));
      let body: string | undefined;
      if (request.method === "POST") {
        const origin = request.headers.get("origin");
        if ((origin && origin !== url.origin) || request.headers.get("sec-fetch-site") === "cross-site")
          return failure("같은 사이트에서 요청해 주세요.", 403);
        if (!request.headers.get("content-type")?.startsWith("application/json")) return failure("JSON 입력이 필요합니다.", 415);
        try { body = await readLimited(request); } catch { return failure("입력은 16KB 이하여야 합니다.", 413); }
        let parsed;
        try { parsed = JSON.parse(body); } catch { return failure("JSON 형식이 올바르지 않습니다.", 400); }
        if (!parsed || typeof parsed.strategy !== "string" || parsed.strategy.trim().length < 3 ||
            [...parsed.strategy].length > 2000 || Object.keys(parsed).some(k => !["strategy", "settings"].includes(k)))
          return failure("전략은 3~2,000자로 입력하세요.", 422);
        const key = request.headers.get("idempotency-key") || "";
        if (!/^[a-zA-Z0-9-]{16,64}$/.test(key)) return failure("유효한 요청 식별자가 필요합니다.", 400);
        headers.set("idempotency-key", key);
        headers.set("content-type", "application/json");
      }
      const coordinator = env.PILOT.get(env.PILOT.idFromName("q-lab-pilot-v1"));
      return await coordinator.fetch(new Request(`https://pilot.internal${url.pathname}`, {
        method: request.method, headers, body,
      }));
    } catch { return failure("서비스 연결에 실패했습니다. 잠시 후 다시 시도하세요.", 503); }
  },
};
