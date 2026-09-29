"""Shared single-attempt JSON inference transport, parsing and sanitized errors."""

from __future__ import annotations

import asyncio
import logging

import httpx

from .models import IntentIR
from .provider_errors import ProviderError, http_provider_error
from .provider_types import ProviderResult


class ChatCompletionProvider:

    @property
    def api_provider(self) -> str:
        return self._connection.api_provider

    @property
    def model(self) -> str:
        return self._connection.model

    @property
    def endpoint(self) -> str:
        return self._connection.endpoint

    @property
    def timeout(self) -> float:
        return self._connection.timeout

    @property
    def api_key(self) -> str:
        return self._connection.api_key

    @property
    def key_source(self) -> str | None:
        return self._connection.key_source

    def _parse_response(self, data: dict) -> ProviderResult:
        if not isinstance(data, dict):
            raise ValueError("invalid response shape")
        if not self._model_matches(data.get("model")):
            raise ProviderError("model_access")
        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            raise ValueError("invalid usage shape")
        inputs = outputs = 0
        cost = self.reserve_microusd
        if "prompt_tokens" in usage and "completion_tokens" in usage:
            inputs, outputs = int(usage["prompt_tokens"]), int(usage["completion_tokens"])
            if inputs < 0 or outputs < 0:
                raise ValueError("invalid usage")
            cost = self._estimate_cost(inputs, outputs, usage)
        choice = data["choices"][0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ValueError("invalid choice shape")
        if choice["message"].get("refusal"):
            raise ProviderError("refusal")
        if choice.get("finish_reason") == "length":
            raise ProviderError("output_limit")
        if choice.get("finish_reason") != "stop":
            raise ProviderError("invalid_response")
        # Old versions are readable in cached ConversionResponse objects only.
        # A fresh response cannot bypass intent validation by returning the old schema.
        ir = IntentIR.model_validate_json(choice["message"]["content"])
        return ProviderResult(ir, inputs, outputs, cost)

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult:
        payload = self._payload(system_prompt, strategy)
        failure = ProviderError("invalid_response")
        try:
            async with (
                asyncio.timeout(self.timeout),
                httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client,
            ):
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                return self._parse_response(response.json())
        except httpx.HTTPStatusError as exc:
            failure = http_provider_error(exc.response)
        except ProviderError as exc:
            failure = exc
        except (httpx.TimeoutException, TimeoutError):
            failure = ProviderError("timeout")
        except httpx.HTTPError:
            failure = ProviderError("connection")
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            failure = ProviderError("invalid_response")
        # No retry loop, fallback model, or reflected provider body/strategy/credential.
        logging.getLogger("uvicorn.error").warning(
            "AI request failed code=%s http_status=%s upstream_code=%s response_shape=%s",
            failure.code,
            failure.http_status,
            failure.upstream_code,
            failure.response_shape,
        )
        raise failure from None
