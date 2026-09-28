"""Resolve a single provider connection without exposing or persisting its credentials."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from .openai_policy import OPENAI_MODEL, OPENAI_POLICY


def model_timeout(maximum: int) -> float:
    try:
        timeout = float(os.getenv("MODEL_TIMEOUT_SECONDS", str(maximum)))
    except ValueError:
        raise RuntimeError("MODEL_TIMEOUT_SECONDS는 양수여야 합니다.") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError("MODEL_TIMEOUT_SECONDS는 양수여야 합니다.")
    return min(timeout, maximum)


@dataclass(frozen=True, slots=True)
class OpenAIConnection:
    api_key: str = field(repr=False)
    key_source: str
    timeout: float
    api_provider: str = field(default="openai", init=False)
    model: str = field(default=OPENAI_MODEL, init=False)
    endpoint: str = field(default="https://api.openai.com/v1/chat/completions", init=False)

    @classmethod
    def from_environment(cls, *, api_key: str | None = None) -> OpenAIConnection:
        key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY에 OpenAI 키를 입력하세요.")
        if os.getenv("OPENAI_MODEL", OPENAI_MODEL).strip() != OPENAI_MODEL:
            raise RuntimeError("현재 OpenAI 비용 정책은 gpt-5.4-mini만 지원합니다.")
        return cls(
            key, "explicit" if api_key is not None else "OPENAI_API_KEY",
            model_timeout(OPENAI_POLICY.max_timeout_seconds),
        )
