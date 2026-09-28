"""OpenAI's fixed low-cost profile; request text and environment cannot raise effort."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from .response_schema import strict_schema

OPENAI_MODEL = "gpt-5.4-mini"
# Standard tier USD per 1M tokens, expressed as integer microdollars.
INPUT_PRICE_MICROUSD = 750_000       # $0.75
CACHED_INPUT_PRICE_MICROUSD = 75_000  # $0.075
OUTPUT_PRICE_MICROUSD = 4_500_000     # $4.50


@dataclass(frozen=True, slots=True)
class OpenAIModelPolicy:
    model: str = field(default=OPENAI_MODEL, init=False)
    reasoning_effort: Literal["none"] = field(default="none", init=False)
    max_completion_tokens: int = field(default=1024, init=False)
    max_request_bytes: int = field(default=16000, init=False)
    max_timeout_seconds: int = field(default=35, init=False)
    # Standard input $0.75/M, cached input $0.075/M, output $4.50/M.
    # <=16KB serialized request and <=1024 output tokens: <=$0.016608.
    # Round the reserve up to $0.017; internal budget conversion is 2,000 KRW/USD.
    reserve_microusd: int = field(default=17000, init=False)
    budget_allowance_krw: int = field(default=34, init=False)

    def payload(self, system_prompt: str, strategy: str) -> dict:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": strategy},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "strategy_ir", "strict": True, "schema": strict_schema()},
            },
            "reasoning_effort": self.reasoning_effort,
            "max_completion_tokens": self.max_completion_tokens,
            "store": False,
            "service_tier": "default",
        }
        if len(json.dumps(body, ensure_ascii=False).encode()) > self.max_request_bytes:
            raise RuntimeError("모델 입력 크기 한도를 초과했습니다.")
        return body

    def estimate_cost(self, inputs: int, outputs: int, cached: int = 0) -> int:
        if not 0 <= cached <= inputs or outputs < 0:
            raise ValueError("invalid usage")
        # Each component rounds to one micro-dollar, never to one dollar.
        return (
            ((inputs - cached) * INPUT_PRICE_MICROUSD + 999_999) // 1_000_000
            + (cached * CACHED_INPUT_PRICE_MICROUSD + 999_999) // 1_000_000
            + (outputs * OUTPUT_PRICE_MICROUSD + 999_999) // 1_000_000
        )


OPENAI_POLICY = OpenAIModelPolicy()
