"""Supabase password auth and database-owned approval, using HttpOnly sessions."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from .config import AppConfig

ACCESS_COOKIE = "brain_access"
REFRESH_COOKIE = "brain_refresh"


class MemberPageUnavailable(HTTPException):
    def __init__(self):
        super().__init__(503, "회원 목록의 새 조회 기능을 아직 사용할 수 없습니다.")


def same_origin(request: Request, public_url: str = "") -> None:
    # A configured canonical URL also works behind a TLS-terminating reverse proxy.
    expected = public_url.rstrip("/") or str(request.base_url).rstrip("/")
    if request.headers.get("origin") != expected:
        raise HTTPException(403, "이 웹사이트의 화면에서 요청하세요.")
    if request.headers.get("x-requested-with") != "brain-site":
        raise HTTPException(403, "이 웹사이트의 화면에서 요청하세요.")


class MembershipService:
    def __init__(self, config: AppConfig, transport=None) -> None:
        self.config, self.transport = config, transport

    @property
    def configured(self) -> bool:
        return self.config.supabase_url.startswith("https://") and bool(
            self.config.supabase_publishable_key
        )

    async def request(self, method, path, *, token=None, body=None, params=None, server=False):
        if not self.configured:
            raise HTTPException(503, "회원 시스템 설정이 아직 완료되지 않았습니다.")
        key = self.config.supabase_secret_key if server else self.config.supabase_publishable_key
        if not key:
            raise HTTPException(503, "회원 사용량 시스템의 서버 키 설정이 필요합니다.")
        headers = {"apikey": key}
        if token and not server:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=5, transport=self.transport) as client:
                response = await client.request(
                    method,
                    self.config.supabase_url + path,
                    headers=headers,
                    json=body,
                    params=params,
                )
            if response.status_code >= 400:
                if response.status_code == 404 and path == "/rest/v1/rpc/brain_members_page":
                    error = response.json()
                    if isinstance(error, dict) and error.get("code") == "PGRST202":
                        raise MemberPageUnavailable()
                if response.status_code in {401, 403}:
                    raise HTTPException(401, "로그인 정보가 만료됐습니다. 다시 로그인하세요.")
                if response.status_code == 429:
                    raise HTTPException(429, "요청이 많습니다. 잠시 후 다시 시도하세요.")
                if path.startswith("/auth/") and response.status_code in {400, 422}:
                    raise HTTPException(400, "이메일·비밀번호와 이메일 인증 여부를 확인하세요.")
                if path.endswith("/brain_set_member_status") and response.status_code == 400:
                    raise HTTPException(400, "회원의 이메일 인증과 승인 상태를 확인하세요.")
                raise HTTPException(503, "회원 시스템에 연결할 수 없습니다. 운영자에게 문의하세요.")
            return response.json() if response.content else {}
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "회원 시스템에 연결할 수 없습니다.") from None

    async def rpc(self, name, token=None, body=None, *, server=False):
        return await self.request(
            "POST", f"/rest/v1/rpc/{name}", token=token, body=body or {}, server=server
        )

    async def member_page(self, token, *, status, query, before, before_id):
        try:
            return await self.rpc("brain_members_page", token, {
                "p_status": status, "p_query": query,
                "p_before_created_at": before.isoformat() if before else None,
                "p_before_id": str(before_id) if before_id else None,
            })
        except MemberPageUnavailable:
            # Existing deployments retain their approved-admin RPC and grants.
            rows = await self.rpc("brain_members", token)
            if not isinstance(rows, list):
                raise HTTPException(503, "회원 목록을 확인하지 못했습니다.") from None
            limited = len(rows) >= 200
            try:
                def order(member):
                    created = datetime.fromisoformat(member["createdAt"].replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        raise ValueError()
                    return created, UUID(member["id"])

                rows = sorted(rows, key=order, reverse=True)
                query = query.lower()
                rows = [member for member in rows
                        if (not status or member["status"] == status)
                        and (not query or query in member["displayName"].lower()
                             or query in (member["email"] or "").lower())
                        and (before is None or order(member) < (before, before_id))]
            except (KeyError, TypeError, AttributeError, ValueError):
                raise HTTPException(503, "회원 목록을 확인하지 못했습니다.") from None
            page = rows[:50]
            cursor = {"createdAt": page[-1]["createdAt"], "id": page[-1]["id"]} \
                if len(rows) > 50 else None
            return {"members": page, "nextCursor": cursor, "limited": limited}

    async def identify(self, request: Request, *, approved=False, admin=False):
        token = request.cookies.get(ACCESS_COOKIE)
        if not token:
            raise HTTPException(401, "로그인한 뒤 이용하세요.")
        user = await self.request("GET", "/auth/v1/user", token=token)
        try:
            UUID(user["id"])
        except (TypeError, KeyError, ValueError):
            raise HTTPException(401, "다시 로그인하세요.") from None
        if not user.get("email_confirmed_at"):
            raise HTTPException(403, "이메일 인증을 완료한 뒤 로그인하세요.")
        access = await self.rpc("brain_access", token)
        if not isinstance(access, dict):
            raise HTTPException(503, "회원 승인 정보를 확인하지 못했습니다.")
        status, role = access.get("status", "pending"), access.get("role", "member")
        if approved and status != "approved":
            raise HTTPException(403, "운영자 승인을 받은 회원만 이용할 수 있습니다.")
        if admin and (status != "approved" or role != "admin"):
            raise HTTPException(403, "운영자만 회원 승인을 관리할 수 있습니다.")
        return {
            "id": user["id"],
            "email": user.get("email", ""),
            "displayName": access.get("displayName", ""),
            "status": status,
            "role": role,
        }


def auth_router(service: MembershipService) -> APIRouter:
    router = APIRouter()
    config = service.config
    enabled = config.auth_mode == "supabase"

    def require_enabled():
        if not enabled:
            raise HTTPException(404, "회원 시스템을 사용하지 않는 로컬 모드입니다.")

    def set_session(response: Response, data):
        try:
            access, refresh = data["access_token"], data["refresh_token"]
            lifetime = min(max(int(data.get("expires_in", 3600)), 60), 3600)
            if not isinstance(access, str) or not isinstance(refresh, str):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise HTTPException(503, "로그인 세션을 설정하지 못했습니다.") from None
        response.set_cookie(
            ACCESS_COOKIE,
            access,
            max_age=lifetime,
            httponly=True,
            secure=config.is_production,
            samesite="lax",
            path="/api",
        )
        response.set_cookie(
            REFRESH_COOKIE,
            refresh,
            max_age=30 * 86400,
            httponly=True,
            secure=config.is_production,
            samesite="lax",
            path="/api/auth",
        )

    async def credentials(request):
        same_origin(request, config.public_url)
        require_enabled()
        try:
            data = await request.json()
            email, password = data.get("email"), data.get("password")
            if not isinstance(email, str) or not re.fullmatch(r"[^\s@]{1,64}@[^\s@]{1,250}", email):
                raise ValueError()
            if not isinstance(password, str) or not password or len(password) > 256:
                raise ValueError()
            return {"email": email.strip().lower(), "password": password}, data
        except (ValueError, AttributeError):
            # Never reflect a password through Pydantic validation errors.
            raise HTTPException(400, "올바른 이메일과 비밀번호를 입력하세요.") from None

    @router.get("/api/auth/config")
    async def auth_config():
        return {"enabled": enabled, "configured": service.configured if enabled else True}

    @router.post("/api/auth/signup")
    async def signup(request: Request):
        payload, data = await credentials(request)
        name = data.get("displayName", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise HTTPException(400, "이름을 1~80자로 입력하세요.")
        payload["data"] = {"display_name": name.strip()}
        await service.request(
            "POST",
            "/auth/v1/signup",
            body=payload,
            params={"redirect_to": config.public_url} if config.public_url else None,
        )
        # Always require a separate login after email verification; do not leak sessions.
        return {"message": "인증 메일을 확인한 뒤 로그인하세요. 운영자 승인 후 이용할 수 있습니다."}

    @router.post("/api/auth/login")
    async def login(request: Request, response: Response):
        payload, _ = await credentials(request)
        data = await service.request(
            "POST", "/auth/v1/token", body=payload, params={"grant_type": "password"}
        )
        set_session(response, data)
        return {"message": "로그인했습니다."}

    @router.post("/api/auth/refresh")
    async def refresh(request: Request, response: Response):
        same_origin(request, config.public_url)
        require_enabled()
        token = request.cookies.get(REFRESH_COOKIE)
        if not token:
            raise HTTPException(401, "다시 로그인하세요.")
        data = await service.request(
            "POST",
            "/auth/v1/token",
            body={"refresh_token": token},
            params={"grant_type": "refresh_token"},
        )
        set_session(response, data)
        return {"message": "로그인을 갱신했습니다."}

    @router.get("/api/auth/me")
    async def me(request: Request):
        require_enabled()
        return await service.identify(request)

    @router.post("/api/auth/logout")
    async def logout(request: Request, response: Response):
        same_origin(request, config.public_url)
        require_enabled()
        token = request.cookies.get(ACCESS_COOKIE)
        refresh_token = request.cookies.get(REFRESH_COOKIE)
        revoked = not (token or refresh_token)
        try:
            if token:
                try:
                    await service.request("POST", "/auth/v1/logout", token=token)
                    revoked = True
                except HTTPException as error:
                    if error.status_code != 401:
                        raise
            if not revoked and refresh_token:
                data = await service.request(
                    "POST", "/auth/v1/token", body={"refresh_token": refresh_token},
                    params={"grant_type": "refresh_token"},
                )
                token = data.get("access_token") if isinstance(data, dict) else None
                if not isinstance(token, str) or not token:
                    raise HTTPException(503, "로그인 세션을 확인하지 못했습니다.")
                await service.request("POST", "/auth/v1/logout", token=token)
                revoked = True
        except HTTPException:
            revoked = False
        response.delete_cookie(ACCESS_COOKIE, path="/api", secure=config.is_production)
        response.delete_cookie(REFRESH_COOKIE, path="/api/auth", secure=config.is_production)
        return {
            "sessionRevoked": revoked,
            "message": "로그아웃했습니다." if revoked else (
                "이 브라우저에서 로그아웃했습니다. 서버 세션 종료는 확인하지 못했습니다. "
                "공유 기기라면 운영자에게 세션 종료를 요청하세요."
            ),
        }

    @router.get("/api/admin/members")
    async def members(
        request: Request,
        status: str = Query("", pattern="^(|pending|approved|rejected|suspended)$"),
        q: str = Query("", max_length=120),
        before: datetime | None = None,
        before_id: UUID | None = None,
    ):
        require_enabled()
        await service.identify(request, admin=True)
        if not request.query_params:
            # Tabs opened before the frontend upgrade expect the original array.
            return await service.rpc("brain_members", request.cookies[ACCESS_COOKIE])
        if (before is None) != (before_id is None) or (before and before.tzinfo is None):
            raise HTTPException(400, "회원 목록의 페이지 정보를 확인하세요.")
        return await service.member_page(
            request.cookies[ACCESS_COOKIE], status=status, query=q.strip(),
            before=before, before_id=before_id,
        )

    @router.post("/api/admin/members/{user_id}")
    async def update_member(user_id: UUID, request: Request):
        require_enabled()
        same_origin(request, config.public_url)
        await service.identify(request, admin=True)
        try:
            status = (await request.json()).get("status")
        except (ValueError, AttributeError):
            status = None
        if status not in {"approved", "rejected", "suspended"}:
            raise HTTPException(400, "승인 상태를 확인하세요.")
        return await service.rpc(
            "brain_set_member_status",
            request.cookies[ACCESS_COOKIE],
            {"p_user_id": str(user_id), "p_status": status},
        )

    return router
