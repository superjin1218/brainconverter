from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig
from .local_provider import local_provider_router
from .membership import ACCESS_COOKIE, MembershipService, auth_router, same_origin
from .models import ConversionResponse, ConvertRequest
from .provider import SemanticProvider, build_provider
from .security import BodyLimitMiddleware, GatewayVerifier
from .service import HarnessService

ProviderFactory = Callable[[], SemanticProvider]


def create_app(
    config: AppConfig | None = None,
    provider_factory: ProviderFactory = build_provider,
    membership_transport=None,
) -> FastAPI:
    resolved_config = config or AppConfig.from_environment()
    verifier = GatewayVerifier(resolved_config)
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
    async def gateway_and_security_headers(request: Request, call_next):
        if verifier.protects(request.url.path):
            body = await request.body()
            if not verifier.verify(body, request.headers):
                return JSONResponse(
                    {"detail": "유효한 Gateway 서명이 필요합니다."}, status_code=401
                )
            email = request.headers.get("x-user-email", "").lower()
            if not verifier.email_is_allowed(email):
                return JSONResponse({"detail": "허용되지 않은 사용자입니다."}, status_code=403)

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
        return {
            "status": "ok",
            "provider": service.provider.name if service else "not-initialized",
        }

    @application.post("/api/convert", response_model=ConversionResponse)
    async def convert(payload: ConvertRequest, request: Request) -> ConversionResponse:
        started = time.monotonic()
        member = None
        if resolved_config.auth_mode == "supabase":
            same_origin(request, resolved_config.public_url)
            member = await membership.identify(request, approved=True)
        application.state.active_conversions += 1
        job_id = None
        try:
            service = harness_service()
            if service.provider.name == "muse" and not payload.trainingConsent:
                raise HTTPException(400, "Contributor 모델의 학습 활용 안내에 동의해 주세요.")
            expected_provider = request.headers.get("x-expected-provider")
            if (
                resolved_config.environment == "development"
                and expected_provider is not None
                and expected_provider != service.provider.name
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "AI 연결 상태가 변경됐습니다. 설정에서 연결 상태를 확인한 뒤 "
                        "다시 변환하세요. 이번 변환은 실행하지 않았습니다."
                    ),
                )
            if member:
                try:
                    job_id = str(UUID(request.headers.get("idempotency-key", "")))
                except ValueError:
                    raise HTTPException(400, "유효한 요청 ID가 필요합니다.") from None
                reserved = await membership.rpc(
                    "brain_reserve",
                    body={
                        "p_user_id": member["id"],
                        "p_request_id": job_id,
                        "p_request_hash": hashlib.sha256(
                            payload.model_dump_json().encode()
                        ).hexdigest(),
                    },
                    server=True,
                )
                state = reserved.get("state") if isinstance(reserved, dict) else None
                if state == "cached":
                    return ConversionResponse.model_validate(reserved["result"])
                if state == "running":
                    return JSONResponse({"status": "processing"}, status_code=202)
                if state != "reserved":
                    job_id = None
                    raise HTTPException(
                        429 if state == "limited" else 403 if state == "denied" else 409,
                        "이용 한도 또는 이전 요청 상태를 확인하세요. 잠시 후 다시 시도하세요.",
                    )
            result = await service.convert(payload)
            if member and job_id:
                try:
                    saved = await membership.rpc(
                        "brain_finish",
                        body={
                            "p_user_id": member["id"],
                            "p_request_id": job_id,
                            "p_result": result.model_dump(),
                            "p_failed": False,
                        },
                        server=True,
                    )
                    if not isinstance(saved, dict) or saved.get("saved") is not True:
                        raise HTTPException(503, "결과를 보관하지 못했습니다.")
                except HTTPException:
                    logging.getLogger("uvicorn.error").warning("conversion result cache failed")
                    result.warnings.append(
                        "결과 보관에 실패했습니다. 생성된 코드를 지금 복사하세요."
                    )
            logging.getLogger("uvicorn.error").info(
                "conversion id=%s status=%s elapsed_ms=%d "
                "input_tokens=%d output_tokens=%d cost_microusd=%d",
                result.requestId,
                result.status,
                int((time.monotonic() - started) * 1000),
                result.usage["inputTokens"],
                result.usage["outputTokens"],
                result.usage["costMicrousd"],
            )
            return result
        except RuntimeError as exc:
            if member and job_id:
                try:
                    await membership.rpc(
                        "brain_finish",
                        body={
                            "p_user_id": member["id"],
                            "p_request_id": job_id,
                            "p_result": None,
                            "p_failed": True,
                        },
                        server=True,
                    )
                except HTTPException:
                    logging.getLogger("uvicorn.error").warning("conversion ledger finish failed")
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        finally:
            application.state.active_conversions -= 1

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
        if result.get("state") == "running":
            return JSONResponse({"status": "processing"}, status_code=202)
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

    application.mount(
        "/", StaticFiles(directory=resolved_config.static_directory, html=True), name="static"
    )
    application.add_middleware(BodyLimitMiddleware)
    return application


app = create_app()
