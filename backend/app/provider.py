"""Assemble the OpenAI provider or the explicit development-only mock."""

from __future__ import annotations

import os

from .openai_policy import OPENAI_MODEL
from .openai_provider import OpenAIProvider
from .provider_types import SemanticProvider


def provider_status(provider: SemanticProvider | None) -> dict:
    name = (
        provider.name if provider is not None
        else os.getenv("HARNESS_PROVIDER", "openai").strip().lower()
    )
    return {
        "provider": name,
        "model": OPENAI_MODEL,
        "keyConfigured": name == "openai" and (
            provider is not None or bool(os.getenv("OPENAI_API_KEY", "").strip())
        ),
    }


def build_provider() -> SemanticProvider:
    provider_name = os.getenv("HARNESS_PROVIDER", "openai").strip().lower()
    if provider_name == "mock":
        if (
            os.getenv("APP_ENV") == "production"
            or os.getenv("VERCEL") == "1"
            or os.getenv("VERCEL_ENV") in {"production", "preview"}
        ):
            raise RuntimeError("운영 환경에는 실제 모델 공급자를 설정해야 합니다.")
        from .mock_provider import MockSemanticProvider

        return MockSemanticProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    raise RuntimeError(f"지원하지 않는 HARNESS_PROVIDER입니다: {provider_name}")
