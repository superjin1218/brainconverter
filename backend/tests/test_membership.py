import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.app.membership import ACCESS_COOKIE, REFRESH_COOKIE, same_origin
from backend.app.provider import MockSemanticProvider

ORIGIN = "https://brain.example.test"
HEADERS = {"origin": ORIGIN, "x-requested-with": "brain-site"}
USER_ID = "10000000-0000-0000-0000-000000000001"
ACCESS = "fake-session-access-never-a-real-token"
REFRESH = "fake-session-refresh-never-a-real-token"
SECRET = "fake-server-key-never-a-real-key"
PASSWORD = "fake-password-that-must-not-be-reflected"
STRATEGY = "최근 5일 동안 종가가 많이 하락한 종목일수록 높은 순위를 부여한다."


def test_default_development_site_requires_login_before_provider_initialization(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.setenv("APP_PUBLIC_URL", "http://testserver")
    provider_calls = []

    def provider():
        provider_calls.append(True)
        return MockSemanticProvider()

    client = TestClient(create_app(AppConfig.from_environment(), provider_factory=provider))
    assert client.get("/api/auth/config").json()["enabled"] is True
    result = client.post(
        "/api/convert",
        json={"strategy": STRATEGY},
        headers={"origin": "http://testserver", "x-requested-with": "brain-site"},
    )
    assert result.status_code == 401
    assert provider_calls == []


def test_authentication_bypass_requires_explicit_development_setting(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "none")
    client = TestClient(
        create_app(provider_factory=MockSemanticProvider),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
        headers={"origin": "http://127.0.0.1", "x-requested-with": "brain-site"},
    )
    assert client.get("/api/auth/config").json()["enabled"] is False
    assert client.post("/api/convert", json={"strategy": STRATEGY}).status_code == 200


def test_canonical_origin_works_behind_tls_proxy_and_blocks_external_origins():
    from fastapi import HTTPException, Request

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/login",
            "root_path": "",
            "server": ("internal", 80),
            "headers": [
                (b"host", b"internal"),
                (b"origin", ORIGIN.encode()),
                (b"x-requested-with", b"brain-site"),
            ],
        }
    )
    same_origin(request, ORIGIN)
    with pytest.raises(HTTPException):
        same_origin(request, "https://other.example.test")


@pytest.fixture
def site():
    state = {
        "status": "pending",
        "role": "member",
        "confirmed": True,
        "valid": True,
        "calls": [],
        "aiCalls": 0,
        "reservation": "reserved",
        "cached": None,
        "finishFails": False,
        "queuePosition": 3,
        "budget": "reserved",
    }
    config = AppConfig(
        environment="production",
        gateway_shared_secret="",
        allowed_emails=frozenset(),
        static_directory=AppConfig.from_environment().static_directory,
        auth_mode="supabase",
        supabase_url="https://supabase.example.test",
        supabase_publishable_key="fake-publishable-key",
        supabase_secret_key=SECRET,
        public_url=ORIGIN,
    )

    class CountingProvider(MockSemanticProvider):
        name = "muse"

        async def interpret(self, system_prompt, strategy):
            state["aiCalls"] += 1
            return await super().interpret(system_prompt, strategy)

    def handler(request):
        path = request.url.path
        payload = json.loads(request.content) if request.content else None
        state["calls"].append((path, payload))
        if path == "/auth/v1/user":
            if not state["valid"]:
                return httpx.Response(401, json={"message": ACCESS})
            assert request.headers["authorization"] == f"Bearer {ACCESS}"
            return httpx.Response(
                200,
                json={
                    "id": USER_ID,
                    "email": "member@example.test",
                    "email_confirmed_at": "2026-09-27" if state["confirmed"] else None,
                    "user_metadata": {"role": "admin", "status": "approved"},
                },
            )
        if path == "/auth/v1/token":
            if state.get("revoked"):
                return httpx.Response(400, json={"message": "invalid refresh token"})
            return httpx.Response(
                200, json={"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600}
            )
        if path == "/auth/v1/logout":
            if state.get("logoutFails"):
                return httpx.Response(503, json={"message": "unavailable"})
            if request.headers.get("authorization") == "Bearer expired-test-token":
                return httpx.Response(401, json={"message": "expired"})
            state["revoked"] = True
            return httpx.Response(204)
        if path == "/auth/v1/signup":
            return httpx.Response(200, json={"access_token": ACCESS, "user": {"id": USER_ID}})
        if path.endswith("/brain_access"):
            return httpx.Response(
                200,
                json={
                    "status": state["status"],
                    "role": state["role"],
                    "displayName": "테스트 회원",
                },
            )
        if path.endswith(
            ("/brain_reserve", "/brain_finish", "/brain_job", "/brain_budget_reserve")
        ):
            assert request.headers["apikey"] == SECRET
            assert "authorization" not in request.headers
            assert payload["p_user_id"] == USER_ID
            if path.endswith("/brain_budget_reserve"):
                assert len(payload["p_request_hash"]) == 64
                return httpx.Response(200, json={"state": state["budget"]})
            if path.endswith("/brain_reserve"):
                return httpx.Response(
                    200,
                    json={
                        "state": state["reservation"],
                        "result": state["cached"],
                        "queuePosition": state["queuePosition"],
                    },
                )
            if path.endswith("/brain_finish"):
                if state["finishFails"]:
                    return httpx.Response(503, json={"message": SECRET})
                state["cached"] = payload["p_result"]
                return httpx.Response(200, json={"saved": True})
            return httpx.Response(
                200,
                json={
                    "state": state["reservation"],
                    "result": state["cached"],
                    "queuePosition": state["queuePosition"],
                },
            )
        if path.endswith("/brain_members"):
            return httpx.Response(200, json=state.get("members", []))
        if path.endswith("/brain_members_page"):
            if state.get("pageStatus"):
                return httpx.Response(state["pageStatus"], json={"code": state.get("pageCode")})
            return httpx.Response(200, json={"members": [], "nextCursor": None})
        if path.endswith("/brain_budget_status"):
            return httpx.Response(200, json={"limitKrw": 20000, "accountedKrw": 4})
        if path.endswith("/brain_set_member_status"):
            for member in state.get("members", []):
                if member["id"] == payload["p_user_id"]:
                    member["status"] = payload["p_status"]
            return httpx.Response(200, json={"status": payload["p_status"]})
        if path.endswith("/brain_usage"):
            return httpx.Response(
                200,
                json={"monthlyRemaining": 49, "monthlyLimit": 50, "dailyUsed": 1, "dailyLimit": 20},
            )
        raise AssertionError(f"unexpected test request: {path}")

    app = create_app(config, CountingProvider, membership_transport=httpx.MockTransport(handler))
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, state, config


def connect(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "member@example.test", "password": PASSWORD},
        headers=HEADERS,
    )
    assert response.status_code == 200
    return response


def convert(client, *, consent=True, headers=None):
    return client.post(
        "/api/convert",
        json={"strategy": STRATEGY, "trainingConsent": consent},
        headers={**HEADERS, "Idempotency-Key": str(uuid4()), **(headers or {})},
    )


def test_anonymous_and_spoofed_email_cannot_reach_ai(site):
    client, state, _ = site
    response = convert(client, headers={"x-user-email": "admin@example.test"})
    assert response.status_code == 401
    assert not state["calls"]
    assert state["aiCalls"] == 0


def test_provider_status_requires_approval_and_never_exposes_or_calls_key(site, monkeypatch):
    client, state, _ = site
    monkeypatch.setenv("HARNESS_PROVIDER", "muse")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.setenv("AI_API_KEY", "server-only-fake-gateway-key")
    assert client.get("/api/provider").status_code == 401
    connect(client)
    assert client.get("/api/provider").status_code == 403
    state["status"] = "approved"
    response = client.get("/api/provider")
    assert response.status_code == 200
    assert response.json() == {
        "provider": "muse",
        "model": "meta/muse-spark-1.3-contributor",
        "keyConfigured": True,
        "localKeyEntry": False,
    }
    assert "server-only-fake-gateway-key" not in response.text
    assert state["aiCalls"] == 0
    monkeypatch.delenv("AI_API_KEY")
    assert client.get("/api/provider").json()["keyConfigured"] is False


@pytest.mark.parametrize("status", ["pending", "rejected", "suspended"])
def test_unapproved_user_metadata_cannot_grant_access(site, status):
    client, state, _ = site
    state["status"] = status
    connect(client)
    assert client.get("/api/auth/me").json()["status"] == status
    assert convert(client).status_code == 403
    assert state["aiCalls"] == 0
    assert not any(path.endswith("brain_reserve") for path, _ in state["calls"])


def test_approved_member_converts_once_and_uses_database_cache(site):
    client, state, _ = site
    state["status"] = "approved"
    connect(client)
    result = convert(client)
    assert result.status_code == 200
    assert result.json()["fastExpression"] == "rank(-ts_delta(close, 5))"
    assert len(result.json()["simulationSettings"]) == 12
    assert state["aiCalls"] == 1
    assert SECRET not in result.text
    state["reservation"] = "cached"
    cached = convert(client)
    assert cached.json() == result.json()
    assert state["aiCalls"] == 1


@pytest.mark.parametrize(
    "reservation,code",
    [("running", 202), ("queued", 202), ("limited", 429), ("denied", 403), ("conflict", 409)],
)
def test_database_admission_state_prevents_an_extra_ai_request(site, reservation, code):
    client, state, _ = site
    state.update(status="approved", reservation=reservation)
    connect(client)
    assert convert(client).status_code == code
    assert state["aiCalls"] == 0


def test_queued_request_claims_once_and_polling_never_calls_ai(site):
    client, state, _ = site
    state.update(status="approved", reservation="queued")
    connect(client)
    request = str(uuid4())
    result = convert(client, headers={"Idempotency-Key": request})
    assert result.json() == {"status": "queued", "queuePosition": 3}
    assert client.get(f"/api/jobs/{request}").json()["status"] == "queued"
    assert state["aiCalls"] == 0
    state["reservation"] = "reserved"
    assert convert(client, headers={"Idempotency-Key": request}).status_code == 200
    state["reservation"] = "cached"
    assert client.get(f"/api/jobs/{request}").status_code == 200
    assert convert(client, headers={"Idempotency-Key": request}).status_code == 200
    assert state["aiCalls"] == 1


def test_training_acknowledgement_is_required_before_ai_or_quota(site):
    client, state, _ = site
    state["status"] = "approved"
    connect(client)
    assert convert(client, consent=False).status_code == 400
    assert state["aiCalls"] == 0
    assert not any(path.endswith("brain_reserve") for path, _ in state["calls"])


def test_expired_or_unconfirmed_session_cannot_convert(site):
    client, state, _ = site
    state["status"] = "approved"
    connect(client)
    state["valid"] = False
    assert convert(client).status_code == 401
    state.update(valid=True, confirmed=False)
    assert convert(client).status_code == 403
    assert state["aiCalls"] == 0


def test_cross_origin_cookie_request_is_rejected_before_auth_or_ai(site):
    client, state, _ = site
    state["status"] = "approved"
    connect(client)
    state["calls"].clear()
    assert convert(client, headers={"origin": "https://untrusted.example"}).status_code == 403
    assert not state["calls"]
    assert state["aiCalls"] == 0


def test_login_sets_secure_httponly_cookies_without_reflecting_credentials(site):
    client, _, _ = site
    response = connect(client)
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all(
        "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
        for cookie in cookies
    )
    for value in (ACCESS, REFRESH, PASSWORD, SECRET):
        assert value not in response.text
    assert client.cookies.get(ACCESS_COOKIE) == ACCESS
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_signup_passes_only_display_name_and_does_not_return_an_access_token(site):
    client, state, _ = site
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "new@example.test",
            "password": PASSWORD,
            "displayName": "새 회원",
            "role": "admin",
            "status": "approved",
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    payload = next(body for path, body in state["calls"] if path == "/auth/v1/signup")
    assert payload["data"] == {"display_name": "새 회원"}
    assert ACCESS not in response.text
    assert not response.headers.get_list("set-cookie")


@pytest.mark.parametrize("endpoint", ["login", "signup"])
@pytest.mark.parametrize("password", ["1", "123456", "2026012345"])
def test_numeric_passwords_pass_through_to_supabase_without_app_minimum(site, endpoint, password):
    client, state, _ = site
    response = client.post(
        f"/api/auth/{endpoint}",
        json={"email": "member@example.test", "password": password, "displayName": "테스트 회원"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    auth_path = "/auth/v1/token" if endpoint == "login" else "/auth/v1/signup"
    auth_calls = [body for path, body in state["calls"] if path == auth_path]
    assert len(auth_calls) == 1
    assert auth_calls[0]["password"] == password
    assert state["aiCalls"] == 0


@pytest.mark.parametrize("password", ["", None, 123456, "x" * 257])
def test_missing_or_invalid_passwords_are_rejected_without_remote_call(site, password):
    client, state, _ = site
    response = client.post(
        "/api/auth/signup",
        json={"email": "member@example.test", "password": password, "displayName": "테스트 회원"},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert not state["calls"]
    assert state["aiCalls"] == 0


@pytest.mark.parametrize(
    "content", ["[]", '{"email":"x","password":"private-password"}', "not JSON"]
)
def test_invalid_auth_input_never_echoes_password(site, content):
    client, _, _ = site
    response = client.post("/api/auth/login", content=content, headers=HEADERS)
    assert response.status_code == 400
    assert "private-password" not in response.text


def test_members_only_admin_can_read_or_change_approvals(site):
    client, state, _ = site
    state["status"] = "approved"
    connect(client)
    assert client.get("/api/admin/members").status_code == 403
    assert (
        client.post(
            f"/api/admin/members/{USER_ID}", json={"status": "approved"}, headers=HEADERS
        ).status_code
        == 403
    )
    state["role"] = "admin"
    assert client.get("/api/admin/members").status_code == 200
    assert (
        client.post(
            f"/api/admin/members/{USER_ID}", json={"status": "approved"}, headers=HEADERS
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/admin/members/{USER_ID}", json={"status": "admin"}, headers=HEADERS
        ).status_code
        == 400
    )


def test_result_survives_a_cache_write_failure_without_another_model_request(site):
    client, state, _ = site
    state.update(status="approved", finishFails=True)
    connect(client)
    result = convert(client)
    assert result.status_code == 200
    assert result.json()["fastExpression"]
    assert any("보관" in warning for warning in result.json()["warnings"])
    assert state["aiCalls"] == 1


def test_production_auth_cannot_be_disabled(site):
    _, _, config = site
    with pytest.raises(ValueError, match="인증"):
        replace(config, auth_mode="none")


@pytest.mark.parametrize("budget,code", [("budget_exhausted", 402), ("unavailable", 503)])
def test_budget_stop_or_unavailable_ledger_prevents_any_paid_call(site, budget, code):
    client, state, _ = site
    state.update(status="approved", budget=budget)
    connect(client)
    result = convert(client)
    assert result.status_code == code
    assert state["aiCalls"] == 0
    finish = [body for path, body in state["calls"] if path.endswith("brain_finish")]
    assert finish[-1]["p_failed"] is True
    assert SECRET not in result.text


def test_budget_endpoint_requires_admin_and_never_returns_credentials(site):
    client, state, _ = site
    assert client.get("/api/admin/budget").status_code == 401
    connect(client)
    state.update(status="approved")
    assert client.get("/api/admin/budget").status_code == 403
    state["role"] = "admin"
    response = client.get("/api/admin/budget")
    assert response.status_code == 200
    assert response.json()["limitKrw"] == 20000
    assert SECRET not in response.text


def test_vercel_automatically_uses_production_and_rejects_development(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.delenv("APP_ENV", raising=False)
    assert AppConfig.from_environment().is_production
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(ValueError, match="Vercel"):
        AppConfig.from_environment()


@pytest.mark.parametrize("access", [None, "expired-test-token", ACCESS])
def test_logout_revokes_refresh_session_and_clears_cookies(site, access):
    client, state, _ = site
    client.cookies.set(REFRESH_COOKIE, REFRESH)
    if access:
        client.cookies.set(ACCESS_COOKIE, access)
    result = client.post("/api/auth/logout", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["sessionRevoked"] is True
    assert state["revoked"] is True
    assert len(result.headers.get_list("set-cookie")) == 2
    assert all("Max-Age=0" in cookie for cookie in result.headers.get_list("set-cookie"))
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, REFRESH)
    assert client.post("/api/auth/refresh", headers=HEADERS).status_code == 400
    assert state["aiCalls"] == 0


def test_logout_reports_unconfirmed_revocation_without_retaining_local_cookies(site):
    client, state, _ = site
    connect(client)
    state["logoutFails"] = True
    result = client.post("/api/auth/logout", headers=HEADERS)
    assert result.json()["sessionRevoked"] is False
    assert "확인하지 못" in result.json()["message"]
    assert client.cookies.get(ACCESS_COOKIE) is None
    assert client.cookies.get(REFRESH_COOKIE) is None
    for value in (ACCESS, REFRESH, SECRET):
        assert value not in result.text


def test_admin_member_pages_pass_validated_filters_and_cursor(site):
    client, state, _ = site
    connect(client)
    state.update(status="approved", role="admin")
    result = client.get("/api/admin/members", params={
        "status": "approved", "q": "target%_", "before": "2026-09-27T00:00:00.123456Z",
        "before_id": USER_ID,
    })
    assert result.json() == {"members": [], "nextCursor": None}
    path, body = state["calls"][-1]
    assert path.endswith("/brain_members_page")
    assert body == {"p_status": "approved", "p_query": "target%_",
                    "p_before_created_at": "2026-09-27T00:00:00.123456+00:00",
                    "p_before_id": USER_ID}
    for params in ({"before_id": USER_ID}, {"status": "admin"}, {"q": "x" * 121},
                   {"before": "2026-09-27T00:00:00", "before_id": USER_ID}):
        assert client.get("/api/admin/members", params=params).status_code in {400, 422}


def test_existing_database_restores_approved_list_and_suspension_without_new_rpc(site):
    client, state, _ = site
    connect(client)
    state.update(status="approved", role="admin", pageStatus=404, pageCode="PGRST202",
                 members=[{"id": USER_ID, "displayName": "테스트", "email": "member@example.test",
                           "status": "approved", "role": "member", "emailConfirmed": True,
                           "createdAt": "2026-09-27T00:00:00.123456+00:00"}])
    response = client.get("/api/admin/members", params={"status": "approved", "q": "member"})
    assert response.status_code == 200
    assert [member["id"] for member in response.json()["members"]] == [USER_ID]
    assert [path for path, _ in state["calls"]][-2:] == [
        "/rest/v1/rpc/brain_members_page", "/rest/v1/rpc/brain_members"]
    assert client.get("/api/admin/members").json() == state["members"]  # Older open tabs.
    response = client.post(f"/api/admin/members/{USER_ID}", json={"status": "suspended"},
                           headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"
    response = client.get("/api/admin/members", params={"status": "suspended"})
    assert response.json()["members"][0]["status"] == "suspended"
    assert state["aiCalls"] == 0


@pytest.mark.parametrize("status,code", [(401, "42501"), (503, None), (404, "other")])
def test_member_list_does_not_fall_back_on_auth_or_connection_errors(site, status, code):
    client, state, _ = site
    connect(client)
    state.update(status="approved", role="admin", pageStatus=status, pageCode=code)
    response = client.get("/api/admin/members", params={"status": "approved"})
    assert response.status_code == (401 if status == 401 else 503)
    assert not any(path.endswith("/brain_members") for path, _ in state["calls"])


def test_member_list_compatibility_keeps_pagination_and_reports_legacy_limit(site):
    client, state, _ = site
    connect(client)
    state.update(status="approved", role="admin", pageStatus=404, pageCode="PGRST202",
                 members=[{"id": str(uuid4()), "displayName": "합성", "email": None,
                           "status": "approved", "role": "member",
                           "createdAt": "2026-09-27T00:00:00.123456+00:00"} for _ in range(200)])
    seen = []
    params = {"status": "approved", "q": "합성"}
    for _ in range(4):
        page = client.get("/api/admin/members", params=params).json()
        assert page["limited"] is True
        assert len(page["members"]) == 50
        seen.extend(member["id"] for member in page["members"])
        if page["nextCursor"]:
            params.update(before=page["nextCursor"]["createdAt"],
                          before_id=page["nextCursor"]["id"])
    assert len(seen) == len(set(seen)) == 200


def test_member_list_compatibility_remains_admin_only(site):
    client, state, _ = site
    connect(client)
    state.update(status="approved", role="member", pageStatus=404, pageCode="PGRST202")
    assert client.get("/api/admin/members", params={"status": "approved"}).status_code == 403
    assert not any(path.endswith(("/brain_members", "/brain_members_page"))
                   for path, _ in state["calls"])
