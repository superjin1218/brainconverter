"""Configure a development server's provider in memory, from its loopback UI only."""

from __future__ import annotations

import ipaddress
import re

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request

from .mock_provider import MockSemanticProvider
from .openai_provider import OpenAIProvider
from .provider import provider_status
from .service import HarnessService


def require_loopback_origin(request: Request) -> None:
    try:
        local_client = bool(
            request.client and ipaddress.ip_address(request.client.host).is_loopback
        )
    except ValueError:
        local_client = False
    local_host = request.url.hostname in {"localhost", "127.0.0.1", "::1"}
    forwarded = any(
        name in request.headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host")
    )
    origin = request.headers.get("origin")
    own_origin = str(request.base_url).rstrip("/")
    if not local_client or not local_host or forwarded or (origin and origin != own_origin):
        raise HTTPException(
            status_code=403, detail="이 컴퓨터의 로컬 화면에서만 설정할 수 있습니다."
        )
    if request.method != "GET" and origin != own_origin:
        raise HTTPException(status_code=403, detail="이 컴퓨터의 로컬 화면에서 요청하세요.")


def require_local_request(request: Request) -> None:
    require_loopback_origin(request)
    if request.method != "GET" and request.headers.get("x-local-setup") != "1":
        raise HTTPException(status_code=403, detail="로컬 화면의 키 연결 버튼을 사용하세요.")


def require_local_conversion(request: Request) -> None:
    require_loopback_origin(request)
    if request.headers.get("x-requested-with") != "brain-site":
        raise HTTPException(status_code=403, detail="로컬 화면의 변환 버튼을 사용하세요.")


def local_provider_router(application: FastAPI) -> APIRouter:
    router = APIRouter(
        prefix="/api/local/provider",
        dependencies=[Depends(require_local_request)],
        include_in_schema=False,
    )

    def status() -> dict:
        service = application.state.harness_service
        return provider_status(service.provider if service else None)

    def require_idle() -> None:
        if application.state.active_conversions:
            raise HTTPException(status_code=409, detail="진행 중인 변환이 끝난 뒤 변경하세요.")

    @router.get("")
    async def get_status() -> dict:
        return status()

    @router.post("")
    async def connect(request: Request) -> dict:
        # Parse manually: validation errors must never echo secret input in a 422 response.
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="키 입력 형식을 확인하세요.") from None
        key = payload.get("apiKey") if isinstance(payload, dict) else None
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.=-]{16,1024}", key.strip()):
            raise HTTPException(
                status_code=400, detail="설정한 AI 서비스의 올바른 키를 입력하세요."
            )
        require_idle()
        try:
            service = HarnessService(OpenAIProvider(api_key=key.strip()))
        except (RuntimeError, ValueError):
            raise HTTPException(status_code=503, detail="로컬 모델 설정을 확인하세요.") from None
        application.state.harness_service = service
        # No file, environment-variable, browser-storage or outbound API writes here.
        return status()

    @router.delete("")
    async def disconnect() -> dict:
        require_idle()
        application.state.harness_service = HarnessService(MockSemanticProvider())
        return status()

    return router
