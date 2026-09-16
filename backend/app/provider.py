from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .models import EntryIR, SignalIR, StrategyIR


@dataclass(frozen=True)
class ProviderResult:
    ir: StrategyIR
    input_tokens: int = 0
    output_tokens: int = 0


class SemanticProvider(Protocol):
    name: str

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult: ...


class OpenAIChatProvider:
    name = "openai"

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self.api_key = api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        self.timeout = float(os.getenv("MODEL_TIMEOUT_SECONDS", "40"))

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": strategy},
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 256,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for _attempt in range(2):
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    raw = json.loads(content)
                    usage = data.get("usage", {})
                    return ProviderResult(
                        ir=StrategyIR.model_validate(raw),
                        input_tokens=int(usage.get("prompt_tokens", 0)),
                        output_tokens=int(usage.get("completion_tokens", 0)),
                    )
                except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValueError) as exc:
                    last_error = exc
        raise RuntimeError(f"모델 응답을 해석하지 못했습니다: {last_error}")


class MockSemanticProvider:
    """Deterministic local provider for UI development and tests; never calls a model."""

    name = "mock"

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult:
        del system_prompt
        lower = strategy.lower()

        signal_field = "returns" if "수익률" in lower or "returns" in lower else "close"
        operation = "raw" if signal_field == "returns" else "delta"
        numbers = [int(item) for item in re.findall(r"(?<!\d)\d+(?!\d)", strategy)]
        signal_window = numbers[0] if numbers and operation == "delta" else 1
        downside = any(
            phrase in lower
            for phrase in ("떨어", "하락", "낮은", "reversal", "drop", "weak")
        )

        entry_enabled = "거래량" in lower or "volume" in lower
        entry_window = 20
        multiplier = 1.0
        comparator = ">="
        if entry_enabled:
            mean_match = re.search(r"(?:최근\s*)?(\d+)일\s*평균", strategy)
            multiplier_match = re.search(r"(\d+(?:\.\d+)?)\s*배", strategy)
            if mean_match:
                entry_window = int(mean_match.group(1))
            if multiplier_match:
                multiplier = float(multiplier_match.group(1))
            if "초과" in lower:
                comparator = ">"
            elif "이하" in lower:
                comparator = "<="
            elif "미만" in lower:
                comparator = "<"

        neutralization = "none"
        if "하위산업" in lower or "subindustry" in lower:
            neutralization = "subindustry"
        elif "섹터" in lower or "sector" in lower:
            neutralization = "sector"
        elif "산업" in lower or "industry" in lower:
            neutralization = "industry"

        ir = StrategyIR(
            status="ok",
            signal=SignalIR(
                field=signal_field,
                operation=operation,
                window=signal_window,
                direction="down" if downside else "up",
                selection="relative",
            ),
            entry=EntryIR(
                enabled=entry_enabled,
                field="volume",
                reference="ts_mean" if entry_enabled else "none",
                window=entry_window if entry_enabled else 1,
                comparator=comparator if entry_enabled else "none",
                multiplier=multiplier,
            ),
            neutralization=neutralization,
            exit="none",
        )
        return ProviderResult(ir=ir)


def build_provider() -> SemanticProvider:
    provider_name = os.getenv("HARNESS_PROVIDER", "openai").strip().lower()
    if provider_name == "mock":
        return MockSemanticProvider()
    if provider_name == "openai":
        return OpenAIChatProvider()
    raise RuntimeError(f"지원하지 않는 HARNESS_PROVIDER입니다: {provider_name}")
