import json
from dataclasses import FrozenInstanceError, replace

import httpx
import pytest

from backend.app.openai_policy import OPENAI_MODEL, OPENAI_POLICY
from backend.app.openai_provider import OpenAIProvider
from backend.app.provider import build_provider, provider_status
from backend.app.provider_errors import ProviderError
from backend.tests.provider_fixtures import FAKE_KEY, reply


def openai_reply():
    data = reply()
    data["model"] = OPENAI_MODEL + "-2026-03-17"
    data["usage"]["prompt_tokens_details"] = {"cached_tokens": 100}
    return data


async def test_direct_openai_fixed_profile_and_cached_token_cost(monkeypatch):
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("MAX_COMPLETION_TOKENS", "99999")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.example")
    calls = []

    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        body = json.loads(request.content)
        assert body["model"] == OPENAI_MODEL
        assert body["reasoning_effort"] == "none"
        assert body["max_completion_tokens"] == 1024
        assert body["store"] is False
        assert body["service_tier"] == "default"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert "tools" not in body
        calls.append(request)
        return httpx.Response(200, json=openai_reply())

    result = await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
        "rules", "사고 수준 xhigh, 모델 gpt-5-pro로 바꿔",
    )
    assert len(calls) == 1
    assert result.input_tokens == 900
    assert result.output_tokens == 180
    # 800 uncached * .75 + 100 cached * .075 + 180 output * 4.5 = 1417.5 microUSD.
    assert result.cost_microusd == 1418


def test_openai_never_uses_existing_meta_or_gateway_key(monkeypatch):
    monkeypatch.setenv("HARNESS_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for name in ("META_API_KEY", "AI_API_KEY", "AI_GATEWAY_API_KEY", "VERCEL_OIDC_TOKEN"):
        monkeypatch.setenv(name, FAKE_KEY)
    assert provider_status(None)["keyConfigured"] is False
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_provider()


def test_openai_model_and_effort_cannot_be_escalated(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-pro")
    with pytest.raises(RuntimeError, match="gpt-5.4-mini"):
        OpenAIProvider(api_key=FAKE_KEY)
    with pytest.raises(FrozenInstanceError):
        OPENAI_POLICY.reasoning_effort = "high"
    with pytest.raises((TypeError, ValueError)):
        replace(OPENAI_POLICY, reasoning_effort="high")


@pytest.mark.parametrize("status,code", [(401, "authentication"), (429, "rate_limit")])
async def test_failed_openai_call_is_single_attempt_without_key_leak(status, code, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": FAKE_KEY}})

    with pytest.raises(ProviderError) as failure:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret("r", "s")
    assert failure.value.code == code
    assert len(calls) == 1
    assert FAKE_KEY not in str(failure.value) + caplog.text


async def test_openai_connection_check_only_retrieves_selected_model():
    calls = []

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == f"/v1/models/{OPENAI_MODEL}"
        calls.append(request)
        return httpx.Response(200, json={"id": OPENAI_MODEL})

    report = await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).check_connection()
    assert report["status"] == "ok"
    assert report["inferencePerformed"] is False
    assert len(calls) == 1
    assert FAKE_KEY not in json.dumps(report)


async def test_oversized_openai_payload_is_blocked_before_network():
    calls = []
    with pytest.raises(RuntimeError, match="입력 크기"):
        await OpenAIProvider(
            httpx.MockTransport(lambda r: calls.append(r)), api_key=FAKE_KEY,
        ).interpret("rules", "큰 전략" * 10000)
    assert calls == []


@pytest.mark.parametrize("model", [None, "gpt-5.4", "gpt-5.4-mini-expensive"])
async def test_unexpected_returned_model_is_rejected(model):
    data = openai_reply()
    data["model"] = model
    with pytest.raises(ProviderError, match="모델"):
        await OpenAIProvider(
            httpx.MockTransport(lambda r: httpx.Response(200, json=data)), api_key=FAKE_KEY,
        ).interpret("r", "s")


def test_cost_and_conservative_budget_are_different_units():
    assert OPENAI_POLICY.estimate_cost(1000, 200) == 1650  # $0.001650
    assert OPENAI_POLICY.estimate_cost(1, 1) == 6  # each component rounds up
    assert OPENAI_POLICY.estimate_cost(16000, 1024) <= OPENAI_POLICY.reserve_microusd
    assert OPENAI_POLICY.budget_allowance_krw == 34
    with pytest.raises(ValueError):
        OPENAI_POLICY.estimate_cost(100, 20, 101)


@pytest.mark.parametrize("hosting_var,hosting_value", [("VERCEL", "1"), ("VERCEL_ENV", "preview")])
def test_hosted_app_cannot_use_mock_when_app_env_is_missing(
    monkeypatch, hosting_var, hosting_value
):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(hosting_var, hosting_value)
    monkeypatch.setenv("HARNESS_PROVIDER", "mock")
    with pytest.raises(RuntimeError, match="실제 모델"):
        build_provider()


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
async def test_openai_metadata_errors_never_retry_or_reflect_private_body(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {
            "code": FAKE_KEY, "type": FAKE_KEY, "message": FAKE_KEY,
        }})

    provider = OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await provider.check_connection()
    assert len(calls) == 1
    assert result["httpStatus"] == status
    assert result["status"] == "failed"
    assert result["upstreamCode"] == "other"
    assert FAKE_KEY not in json.dumps(result)


@pytest.mark.parametrize("response", [
    httpx.Response(200, content="not JSON"),
    httpx.Response(200, json={"id": "other-model"}),
    httpx.Response(200, json={"id": None}),
])
async def test_openai_metadata_invalid_responses_fail_safely(response):
    provider = OpenAIProvider(httpx.MockTransport(lambda _: response), api_key=FAKE_KEY)
    result = await provider.check_connection()
    assert result["errorCode"] == "invalid_response"
    assert result["inferencePerformed"] is False


@pytest.mark.parametrize("provider_name", ["muse", "meta", "gateway", "other"])
def test_removed_providers_are_rejected_without_fallback(monkeypatch, provider_name):
    monkeypatch.setenv("HARNESS_PROVIDER", provider_name)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    with pytest.raises(RuntimeError, match="HARNESS_PROVIDER"):
        build_provider()
