"""Read-only deployment checks. Never signs up, logs in, reserves jobs, or calls AI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "https://brainconverter.qlabcommunity.org"
STRATEGY = "최근 5일 동안 종가가 하락한 종목의 순위를 계산한다."


def site_check(base: str, secrets: list[str], expected_ai_enabled: bool = False) -> dict:
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)

    def safe(response):
        # Only return booleans/hashes, never bodies, cookies, or remote error messages.
        check("no_secrets_in_responses", checks.get("no_secrets_in_responses", True)
              and not any(value in response.text for value in secrets))
        return response

    with httpx.Client(base_url=base, timeout=20, follow_redirects=False) as client:
        home = safe(client.get("/"))
        check("homepage", home.status_code == 200 and 'id="auth-form"' in home.text
              and 'id="auth-signup-tab"' in home.text)
        check("password_minimum_6", 'minlength="6"' in home.text)
        check("admin_identity_warning", 'id="members-identity-warning"' in home.text
              and "별도 경로로 본인을 확인" in home.text)
        check("homepage_no_store", home.headers.get("cache-control") == "no-store")
        check("nosniff", home.headers.get("x-content-type-options") == "nosniff")
        check("frame_denied", home.headers.get("x-frame-options") == "DENY")
        check("no_referrer", home.headers.get("referrer-policy") == "no-referrer")
        check("csp", "script-src 'self'" in home.headers.get("content-security-policy", "")
              and "base-uri 'none'" in home.headers.get("content-security-policy", ""))
        check("hsts", home.headers.get("strict-transport-security") == "max-age=31536000")
        check("head", client.head("/").status_code == 200)
        if base.startswith("https://"):
            insecure = client.get(base.replace("https://", "http://", 1) + "/auth/callback?probe=1")
            check("http_redirect_https", insecure.status_code == 308 and (
                insecure.headers.get("location") == base + "/auth/callback?probe=1"
            ))
        hashes = {"/": hashlib.sha256(home.content).hexdigest()}
        for path, mime in [("/js/app.js", "javascript"), ("/js/auth-callback.js", "javascript"),
                           ("/js/membership.js", "javascript"), ("/app.css", "text/css")]:
            response = safe(client.get(path))
            check(path, response.status_code == 200
                  and mime in response.headers.get("content-type", "")
                  and response.headers.get("cache-control") == "no-store")
            hashes[path] = hashlib.sha256(response.content).hexdigest()
        callback = safe(client.get("/auth/callback"))
        check("legacy_callback_page",
              callback.status_code == 200 and callback.content == home.content)
        retired = safe(client.post("/api/auth/confirmation", json={}))
        check("confirmation_api_retired", retired.status_code in {404, 405})
        config = safe(client.get("/api/auth/config"))
        check("auth_config", config.status_code == 200
              and config.json() == {"enabled": True, "configured": True})
        health = safe(client.get("/api/health"))
        check("configured_ai_state", health.status_code == 200
              and health.json().get("conversionsEnabled") is expected_ai_enabled
              and health.json().get("provider") == "openai")
        for path in ["/api/auth/me", "/api/provider", "/api/usage", "/api/admin/members",
                     "/api/admin/budget", "/api/admin/provider-check",
                     "/api/jobs/00000000-0000-0000-0000-000000000000"]:
            check("anonymous " + path, safe(client.get(path)).status_code == 401)
        headers = {"Origin": PUBLIC, "X-Requested-With": "brain-site"}
        check("anonymous_convert", safe(client.post(
            "/api/convert", json={"strategy": STRATEGY}, headers=headers
        )).status_code == 401)
        check("anonymous_admin_update", safe(client.post(
            "/api/admin/members/00000000-0000-0000-0000-000000000000",
            json={"status": "approved"}, headers=headers,
        )).status_code == 401)
        for path in ["/api/auth/signup", "/api/auth/login", "/api/auth/refresh",
                     "/api/auth/logout", "/api/convert"]:
            payload = {"strategy": STRATEGY} if path == "/api/convert" else {}
            check("csrf " + path, safe(client.post(path, json=payload, headers={
                "Origin": "https://untrusted.example", "X-Requested-With": "brain-site",
            })).status_code == 403)
        check("missing_csrf_header", client.post(
            "/api/auth/login", json={}, headers={"Origin": PUBLIC}
        ).status_code == 403)
        for endpoint in ["signup", "login"]:
            invalid = safe(client.post("/api/auth/" + endpoint, json={
                "email": "policy-probe@example.invalid", "password": "12345",
                "displayName": "Policy probe",
            }, headers=headers))
            check("short_password_denied " + endpoint, invalid.status_code == 400)
        check("invalid_jwt", safe(client.get("/api/auth/me", headers={
            "Cookie": "brain_access=invalid-jwt-deployment-probe",
        })).status_code == 401)
        logout = safe(client.post("/api/auth/logout", json={}, headers=headers))
        expired_cookies = logout.headers.get_list("set-cookie")
        check("logout_cookie_cleanup", logout.status_code == 200 and len(expired_cookies) == 2
              and all("Secure" in cookie and "Max-Age=0" in cookie for cookie in expired_cookies))
        for path in ["/.env.local", "/.git/config", "/api/docs", "/openapi.json",
                     "/api/local/provider"]:
            check("hidden " + path, safe(client.get(path)).status_code == 404)
        check("host_validation", client.get("/", headers={"Host": "untrusted.example"}
              ).status_code in {400, 403})
        return {"base": base, "passed": all(checks.values()), "checks": checks,
                "content_sha256": hashes, "health": health.json(),
                "cloudflare_ray_present": "cf-ray" in home.headers,
                "cloudflare_cache_status": home.headers.get("cf-cache-status")}


def supabase_check(env: dict) -> dict:
    checks = {}
    url = env["SUPABASE_URL"].rstrip("/")
    public_headers = {"apikey": env["SUPABASE_PUBLISHABLE_KEY"]}
    server_headers = {"apikey": env["SUPABASE_SECRET_KEY"]}
    with httpx.Client(timeout=20) as client:
        checks["auth_health"] = client.get(url + "/auth/v1/health", headers=public_headers
                                           ).status_code == 200
        settings = client.get(url + "/auth/v1/settings", headers=public_headers)
        data = settings.json()
        checks["signup_enabled"] = (
            settings.status_code == 200 and data.get("disable_signup") is False
        )
        checks["email_confirmation_disabled"] = data.get("mailer_autoconfirm") is True
        checks["email_provider"] = data.get("external", {}).get("email") is True
        checks["anonymous_disabled"] = data.get("external", {}).get("anonymous_users") is False
        schema = client.get(url + "/rest/v1/", headers={
            **server_headers, "Accept": "application/openapi+json",
        })
        paths = schema.json().get("paths", {})
        expected = [
            "brain_access", "brain_members", "brain_members_page", "brain_set_member_status",
            "brain_usage", "brain_reserve", "brain_job", "brain_finish", "brain_budget_reserve",
            "brain_budget_status", "brain_openai_budget_ready", "brain_auth_policy_ready",
        ]
        checks["server_rpc_registration"] = schema.status_code == 200 and all(
            "/rpc/" + name in paths for name in expected
        )
        # This SQL STABLE function only reads budget metadata; it never reserves money.
        ready = client.get(url + "/rest/v1/rpc/brain_openai_budget_ready", headers=server_headers)
        checks["openai_budget_policy"] = ready.status_code == 200 and (
            ready.json().get("ready") is True and ready.json().get("allowanceKrw") == 34
        )
        policy = client.get(url + "/rest/v1/rpc/brain_auth_policy_ready", headers=server_headers)
        checks["password_only_database_policy"] = policy.status_code == 200 and policy.json() == {
            "policy": "password_only_approval_v1", "ready": True,
        }
        for table in ["brain_members", "brain_approval_audit", "brain_jobs",
                      "brain_ai_budget", "brain_ai_charges"]:
            response = client.get(url + "/rest/v1/" + table, params={"select": "*", "limit": 0},
                                  headers={**public_headers, "Accept-Profile": "private"})
            checks["private_schema_hidden " + table] = response.status_code == 406 and (
                response.json().get("code") == "PGRST106"
            )
        for name in ["brain_access", "brain_members", "brain_members_page", "brain_usage",
                     "brain_budget_status", "brain_openai_budget_ready", "brain_auth_policy_ready"]:
            response = client.get(url + "/rest/v1/rpc/" + name, headers=public_headers)
            checks["anonymous_read_denied " + name] = response.status_code == 401 and (
                response.json().get("code") == "42501"
            )
    return {"passed": all(checks.values()), "checks": checks,
            "full_catalog_audit": "not executed; requires DB or SQL Editor access",
            "smtp_delivery": "not required for password signup/login; no emails sent",
            "dashboard_only_checks": (
                "Minimum password length 6, password character requirements empty, "
                "Custom SMTP OFF: verify in dashboard; public settings do not expose these"
            )}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", default="http://127.0.0.1:3000")
    parser.add_argument("--skip-public", action="store_true")
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    env = dotenv_values(ROOT / ".env.local", interpolate=False)
    expected_ai_enabled = env.get("CONVERSIONS_ENABLED", "true").strip().lower() == "true"
    secrets = [v for k, v in env.items() if v and ("KEY" in k or "PASSWORD" in k or "TOKEN" in k)]
    result = {}
    targets = [("local", lambda: site_check(args.local, secrets, expected_ai_enabled))]
    if not args.skip_public:
        targets.append(("public", lambda: site_check(PUBLIC, secrets, expected_ai_enabled)))
    if not args.skip_supabase:
        targets.append(("supabase", lambda: supabase_check(env)))
    for name, run in targets:
        try:
            result[name] = run()
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # Exception reprs can contain request URLs or credentials. Never print them.
            result[name] = {"passed": False, "error": "Connection or response validation failed"}
    if (
        "public" in result and "content_sha256" in result["public"]
        and "content_sha256" in result["local"]
    ):
        result["public_matches_local"] = (
            result["public"]["content_sha256"] == result["local"]["content_sha256"]
            and result["public"]["health"] == result["local"]["health"]
        )
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    return 0 if all(v.get("passed", False) if isinstance(v, dict) else v
                    for v in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
