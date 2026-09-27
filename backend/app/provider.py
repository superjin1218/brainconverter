from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .models import EntryIR, SignalIR, StrategyIR
from .provider_errors import ProviderError, http_provider_error


@dataclass(frozen=True)
class ProviderResult:
    ir: StrategyIR
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microusd: int = 0


# Budget profile: gpt-5-mini, $0.25 / 1M input, $2 / 1M output.
# Unknown/failed requests retain this conservative allowance in the Gateway ledger.
CONVERSION_RESERVE_MICROUSD = 100_000
MAX_COMPLETION_TOKENS = 1024
MUSE_MODEL = "meta/muse-spark-1.3-contributor"
MUSE_RESERVE_MICROUSD = 2000


def strict_schema() -> dict:
    schema = StrategyIR.model_json_schema()

    def visit(value):
        if isinstance(value, dict):
            # Bounds are enforced again by Pydantic; keep the wire schema portable.
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                value.pop(key, None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


class SemanticProvider(Protocol):
    name: str

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult: ...


class OpenAIChatProvider:
    name = "openai"
    endpoint = "https://api.openai.com/v1/chat/completions"
    max_attempts = 2
    reserve_microusd = CONVERSION_RESERVE_MICROUSD // 12

    def estimate_cost(self, inputs: int, outputs: int) -> int:
        return (inputs + 3) // 4 + outputs * 2

    def routing_options(self) -> dict:
        return {}

    def validate_response_model(self, data: dict) -> None:
        pass

    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, *, api_key: str | None = None
    ) -> None:
        resolved_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        if not resolved_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self.api_key = resolved_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        if self.model != "gpt-5-mini":
            raise RuntimeError("현재 비용 제한 프로필은 gpt-5-mini만 지원합니다.")
        self.timeout = min(float(os.getenv("MODEL_TIMEOUT_SECONDS", "40")), 40)
        self.transport = transport

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": strategy},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "strategy_ir", "strict": True, "schema": strict_schema()},
            },
            "reasoning_effort": "minimal",
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            **self.routing_options(),
        }
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 16000:
            raise RuntimeError("모델 입력 크기 한도를 초과했습니다.")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        cost = input_tokens = output_tokens = 0
        failure = ProviderError("invalid_response")
        try:
            async with (
                asyncio.timeout(self.timeout),
                httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client,
            ):
                for attempt in range(self.max_attempts):
                    attempt_cost = self.reserve_microusd
                    try:
                        response = await client.post(
                            self.endpoint,
                            headers=headers,
                            json=payload,
                        )
                        response.raise_for_status()
                        data = response.json()
                        if not isinstance(data, dict):
                            raise ValueError("invalid response shape")
                        self.validate_response_model(data)
                        usage = data.get("usage", {})
                        if not isinstance(usage, dict):
                            raise ValueError("invalid usage shape")
                        if "prompt_tokens" in usage and "completion_tokens" in usage:
                            inputs, outputs = (
                                int(usage["prompt_tokens"]),
                                int(usage["completion_tokens"]),
                            )
                            if inputs < 0 or outputs < 0:
                                raise ValueError("invalid usage")
                            input_tokens += inputs
                            output_tokens += outputs
                            attempt_cost = self.estimate_cost(inputs, outputs)
                        choice = data["choices"][0]
                        if not isinstance(choice, dict) or not isinstance(
                            choice.get("message"), dict
                        ):
                            raise ValueError("invalid choice shape")
                        if choice["message"].get("refusal"):
                            raise ProviderError("refusal")
                        if choice.get("finish_reason") == "length":
                            raise ProviderError("output_limit")
                        if choice.get("finish_reason") != "stop":
                            raise ProviderError("invalid_response")
                        ir = StrategyIR.model_validate_json(choice["message"]["content"])
                        return ProviderResult(ir, input_tokens, output_tokens, cost + attempt_cost)
                    except httpx.HTTPStatusError as exc:
                        failure = http_provider_error(exc.response)
                    except ProviderError as exc:
                        failure = exc
                    except httpx.TimeoutException:
                        failure = ProviderError("timeout")
                    except httpx.HTTPError:
                        failure = ProviderError("connection")
                    except (KeyError, IndexError, TypeError, ValueError):
                        failure = ProviderError("invalid_response")
                    cost += attempt_cost
                    if not failure.retryable:
                        break
                    if attempt + 1 < self.max_attempts:
                        await asyncio.sleep(0.2)
        except TimeoutError:
            failure = ProviderError("timeout")
        # Never propagate provider bodies, strategy text or credentials to logs/clients.
        logging.getLogger("uvicorn.error").warning("AI request failed code=%s", failure.code)
        raise failure from None


class MuseSparkProvider(OpenAIChatProvider):
    name = "muse"
    endpoint = "https://ai-gateway.vercel.sh/v1/chat/completions"
    max_attempts = 1
    reserve_microusd = MUSE_RESERVE_MICROUSD

    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, *, api_key: str | None = None
    ) -> None:
        key = (
            api_key
            if api_key is not None
            else (os.getenv("AI_GATEWAY_API_KEY") or os.getenv("VERCEL_OIDC_TOKEN", ""))
        )
        if not key.strip():
            raise RuntimeError("Vercel AI Gateway API 키가 필요합니다.")
        self.api_key = key.strip()
        self.model = os.getenv("MUSE_MODEL", MUSE_MODEL)
        if self.model != MUSE_MODEL:
            raise RuntimeError("Muse Spark 1.3 Contributor만 사용할 수 있습니다.")
        self.timeout = min(float(os.getenv("MODEL_TIMEOUT_SECONDS", "35")), 35)
        self.transport = transport

    def estimate_cost(self, inputs: int, outputs: int) -> int:
        # $0.10 input / $0.20 output per million tokens. Round up each component.
        return (inputs + 9) // 10 + (outputs + 4) // 5

    def routing_options(self) -> dict:
        return {"providerOptions": {"gateway": {"only": ["meta"]}}}

    def validate_response_model(self, data: dict) -> None:
        if data.get("model") not in {None, MUSE_MODEL, "muse-spark-1.3-contributor"}:
            raise ProviderError("model_access")


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
            phrase in lower for phrase in ("떨어", "하락", "낮은", "reversal", "drop", "weak")
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
    provider_name = os.getenv("HARNESS_PROVIDER", "muse").strip().lower()
    if provider_name == "mock":
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("운영 환경에는 실제 모델 공급자를 설정해야 합니다.")
        return MockSemanticProvider()
    if provider_name == "muse":
        return MuseSparkProvider()
    raise RuntimeError(f"지원하지 않는 HARNESS_PROVIDER입니다: {provider_name}")
