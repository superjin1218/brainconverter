"""OpenAI direct API adapter with a fixed model and one request per conversion."""

from __future__ import annotations

import re

import httpx

from .chat_provider import ChatCompletionProvider
from .openai_policy import OPENAI_POLICY
from .provider_config import OpenAIConnection
from .provider_errors import ProviderError, diagnostic_failure, http_provider_error


class OpenAIProvider(ChatCompletionProvider):
    name = "openai"
    reserve_microusd = OPENAI_POLICY.reserve_microusd
    budget_allowance_krw = OPENAI_POLICY.budget_allowance_krw

    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, *, api_key: str | None = None
    ) -> None:
        self._connection = OpenAIConnection.from_environment(api_key=api_key)
        self._transport = transport

    def _model_matches(self, model) -> bool:
        return isinstance(model, str) and bool(
            re.fullmatch(re.escape(self.model) + r"(?:-\d{4}-\d{2}-\d{2})?", model)
        )

    def _payload(self, system_prompt: str, strategy: str) -> dict:
        return OPENAI_POLICY.payload(system_prompt, strategy)

    def _estimate_cost(self, inputs: int, outputs: int, usage: dict) -> int:
        details = usage.get("prompt_tokens_details") or {}
        if not isinstance(details, dict):
            raise ValueError("invalid usage")
        cached = int(details.get("cached_tokens", 0))
        return OPENAI_POLICY.estimate_cost(inputs, outputs, cached)

    async def check_connection(self) -> dict:
        report = {
            "apiProvider": "openai", "model": self.model,
            "reasoningEffort": OPENAI_POLICY.reasoning_effort, "inferencePerformed": False,
        }
        try:
            async with httpx.AsyncClient(timeout=5, transport=self._transport) as client:
                response = await client.get(
                    f"https://api.openai.com/v1/models/{self.model}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if response.is_error:
                raise http_provider_error(response)
            data = response.json()
            if not isinstance(data, dict) or data.get("id") != self.model:
                raise ProviderError("invalid_response")
            return {**report, "status": "ok", "httpStatus": 200, "modelAvailable": True}
        except (ProviderError, httpx.HTTPError, ValueError) as exc:
            failure = ProviderError("invalid_response") if isinstance(exc, ValueError) else exc
            return {**report, **diagnostic_failure(failure, None)}
