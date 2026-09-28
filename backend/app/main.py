from __future__ import annotations

import hashlib
from collections.abc import Callable
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig
from .conversion import ConversionCoordinator, pending_job
from .local_provider import local_provider_router
from .membership import ACCESS_COOKIE, MembershipService, auth_router
from .models import ConversionResponse, ConvertRequest
from .openai_policy import OPENAI_POLICY
from .openai_provider import OpenAIProvider
from .provider import build_provider
from .provider import provider_status as current_provider_status
from .provider_diagnostics import diagnostic_html, diagnostic_runtime
from .provider_types import SemanticProvider
from .security import BodyLimitMiddleware
from .service import HarnessService

ProviderFactory = Callable[[], SemanticProvider]


def create_app(
    config: AppConfig | None = None,
    provider_factory: ProviderFactory = build_provider,
    membership_transport=None,
) -> FastAPI:
    resolved_config = config or AppConfig.from_environment()
    application = FastAPI(
        title="Natural Language BRAIN Alpha Harness",
        version="1.0.0",
        docs_url=None if resolved_config.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if resolved_config.is_production else "/openapi.json",
        redirect_slashes=False,
    )
    application.state.harness_service = None
    application.state.active_conversions = 0
    membership = MembershipService(resolved_config, membership_transport)
    application.include_router(auth_router(membership))

    if resolved_config.environment == "development":
        application.include_router(local_provider_router(application))

    def harness_service() -> HarnessService:
        if application.state.harness_service is None:
            application.state.harness_service = HarnessService(provider_factory())
        return application.state.harness_service

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/") or resolved_config.environment == "development":
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; img-src 'self' data:; connect-src 'self'"
        )
        return response

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        service = application.state.harness_service
        status = current_provider_status(service.provider if service else None)
        return {
            "status": "ok",
            "provider": status["provider"],
            "model": status["model"],
            "providerRevision": diagnostic_runtime()["providerSourceSha256"],
        }

    @application.get("/api/provider")
    async def provider_status(request: Request):
        if resolved_config.auth_mode == "supabase":
            await membership.identify(request, approved=True)
        elif resolved_config.is_production:
            raise HTTPException(404, "설정을 조회할 수 없습니다.")
        service = application.state.harness_service
        return {
            **current_provider_status(service.provider if service else None),
            "localKeyEntry": resolved_config.environment == "development",
        }

    conversions = ConversionCoordinator(
        resolved_config, membership, application.state, harness_service
    )

    @application.post("/api/convert", response_model=ConversionResponse)
    async def convert(payload: ConvertRequest, request: Request):
        return await conversions.convert(payload, request)

    @application.get("/api/jobs/{job_id}")
    async def job(job_id: UUID, request: Request):
        if resolved_config.auth_mode != "supabase":
            raise HTTPException(404, "요청을 찾을 수 없습니다.")
        member = await membership.identify(request, approved=True)
        result = await membership.rpc(
            "brain_job",
            body={"p_user_id": member["id"], "p_request_id": str(job_id)},
            server=True,
        )
        if result.get("state") in {"running", "queued"}:
            return pending_job(result)
        if result.get("state") == "cached":
            return ConversionResponse.model_validate(result["result"])
        raise HTTPException(
            409, "이전 요청이 실패했거나 만료됐습니다. 새 요청으로 다시 시도하세요."
        )

    @application.get("/api/usage")
    async def usage(request: Request):
        if resolved_config.auth_mode != "supabase":
            raise HTTPException(404)
        await membership.identify(request, approved=True)
        return await membership.rpc("brain_usage", request.cookies[ACCESS_COOKIE])

    @application.get("/api/admin/budget")
    async def budget_status(request: Request):
        if resolved_config.auth_mode != "supabase":
            raise HTTPException(404)
        await membership.identify(request, admin=True)
        body = {"p_allowance_krw": OPENAI_POLICY.budget_allowance_krw}
        return await membership.rpc(
            "brain_budget_status", request.cookies[ACCESS_COOKIE], body=body
        )

    @application.get("/api/admin/provider-check")
    async def provider_check(request: Request):
        if resolved_config.auth_mode != "supabase":
            raise HTTPException(404)
        await membership.identify(request, admin=True)
        try:
            provider = harness_service().provider
        except RuntimeError:
            raise HTTPException(503, "서버의 AI 연결 설정을 확인하세요.") from None
        if not isinstance(provider, OpenAIProvider):
            raise HTTPException(503, "AI 연결 진단을 사용할 수 없습니다.")
        result = await provider.check_connection()
        # A high-entropy API key cannot be recovered from this short comparison ID.
        # It is returned only after the approved-admin check, never in public status or logs.
        result["keyFingerprint"] = hashlib.sha256(provider.api_key.encode()).hexdigest()[:16]
        result["keyVariable"] = provider.key_source
        result["runtime"] = diagnostic_runtime()
        if "text/html" in request.headers.get("accept", "").lower():
            return HTMLResponse(diagnostic_html(result))
        return result

    application.mount(
        "/", StaticFiles(directory=resolved_config.static_directory, html=True), name="static"
    )
    application.add_middleware(BodyLimitMiddleware)
    return application


app = create_app()
