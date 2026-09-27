import json

import httpx
import pytest

from backend.app.provider import MUSE_MODEL, MuseSparkProvider, build_provider
from backend.app.provider_errors import ProviderError
from backend.tests.test_provider import FAKE_KEY, reply


@pytest.fixture(autouse=True)
def muse_model(monkeypatch):
    monkeypatch.setenv("MUSE_MODEL", MUSE_MODEL)


async def test_fixed_muse_model_meta_only_structured_output_and_single_request():
    calls = []

    def handler(request):
        assert str(request.url) == "https://ai-gateway.vercel.sh/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        data = json.loads(request.content)
        assert data["model"] == MUSE_MODEL
        assert data["response_format"]["json_schema"]["strict"] is True
        assert data["max_completion_tokens"] == 1024
        assert data["reasoning_effort"] == "minimal"
        assert data["providerOptions"] == {"gateway": {"only": ["meta"]}}
        assert "models" not in data
        calls.append(1)
        return httpx.Response(200, json={**reply(), "model": MUSE_MODEL})

    result = await MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
        "rules", "최근 5일 하락 종목"
    )
    assert calls == [1]
    assert result.cost_microusd == 126


@pytest.mark.parametrize("status", [400, 401, 402, 403, 429, 500, 503])
async def test_muse_never_automatically_retries_a_failed_request(status):
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": FAKE_KEY}})

    with pytest.raises(ProviderError) as error:
        await MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "rules", "5일 하락"
        )
    assert calls == [1]
    assert FAKE_KEY not in str(error.value)
    if status == 402:
        assert error.value.code == "credits"


async def test_gateway_cannot_silently_return_a_different_model():
    with pytest.raises(ProviderError, match="모델"):
        await MuseSparkProvider(
            httpx.MockTransport(lambda _: httpx.Response(200, json={**reply(), "model": "gpt-5"})),
            api_key=FAKE_KEY,
        ).interpret("rules", "5일 하락")


def test_other_model_is_blocked_before_any_request(monkeypatch):
    monkeypatch.setenv("MUSE_MODEL", "meta/muse-spark-1.3")
    with pytest.raises(RuntimeError, match="Contributor"):
        MuseSparkProvider(api_key=FAKE_KEY)


def test_openai_credentials_are_never_reused_for_meta_or_vercel(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.setenv("HARNESS_PROVIDER", "muse")
    with pytest.raises(RuntimeError, match="Gateway"):
        build_provider()
