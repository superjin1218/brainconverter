from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig
from .models import ConversionResponse, ConvertRequest
from .provider import SemanticProvider, build_provider
from .security import GatewayVerifier
from .service import HarnessService

ProviderFactory = Callable[[], SemanticProvider]


def create_app(
    config: AppConfig | None = None,
    provider_factory: ProviderFactory = build_provider,
) -> FastAPI:
    resolved_config = config or AppConfig.from_environment()
    verifier = GatewayVerifier(resolved_config)
    application = FastAPI(
        title="Natural Language BRAIN Alpha Harness",
        version="1.0.0",
        docs_url=None if resolved_config.is_production else "/api/docs",
        redoc_url=None,
    )
    application.state.harness_service = None

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
    async def convert(payload: ConvertRequest) -> ConversionResponse:
        try:
            return await harness_service().convert(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    application.mount(
        "/", StaticFiles(directory=resolved_config.static_directory, html=True), name="static"
    )
    return application


app = create_app()

