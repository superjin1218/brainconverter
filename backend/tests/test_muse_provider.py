import json

import httpx
import pytest

from backend.app.provider import META_MUSE_MODEL, MUSE_MODEL, MuseSparkProvider, build_provider
from backend.app.provider_errors import ProviderError
from backend.tests.test_provider import FAKE_KEY, reply


@pytest.fixture(autouse=True)
def muse_model(monkeypatch):
    monkeypatch.setenv("MUSE_MODEL", MUSE_MODEL)
    monkeypatch.delenv("MUSE_API_PROVIDER", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)


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


@pytest.mark.parametrize("api_provider", ["gateway", "meta"])
@pytest.mark.parametrize("status", [400, 401, 402, 403, 429, 500, 503])
async def test_muse_never_automatically_retries_a_failed_request(
    status, api_provider, monkeypatch
):
    monkeypatch.setenv("MUSE_API_PROVIDER", api_provider)
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


async def test_meta_direct_uses_only_contributor_and_meta_endpoint(monkeypatch):
    monkeypatch.setenv("MUSE_API_PROVIDER", "meta")
    calls = []

    def handler(request):
        assert str(request.url) == "https://api.meta.ai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        data = json.loads(request.content)
        assert data["model"] == META_MUSE_MODEL
        assert data["max_completion_tokens"] == 1024
        assert data["reasoning_effort"] == "minimal"
        assert data["response_format"]["json_schema"]["strict"] is True
        assert "providerOptions" not in data
        calls.append(request)
        return httpx.Response(200, json={**reply(), "model": META_MUSE_MODEL})

    result = await MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
        "rules", "최근 5일 하락 종목"
    )
    assert len(calls) == 1
    assert result.cost_microusd == 126


def test_meta_credentials_do_not_fall_back_to_gateway_or_oidc(monkeypatch):
    monkeypatch.setenv("MUSE_API_PROVIDER", "meta")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "fake-gateway-only")
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "fake-vercel-only")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Meta API"):
        MuseSparkProvider()
    monkeypatch.setenv("AI_API_KEY", FAKE_KEY)
    assert MuseSparkProvider().api_key == FAKE_KEY
    monkeypatch.setenv("META_API_KEY", "fake-meta-preferred")
    assert MuseSparkProvider().api_key == "fake-meta-preferred"


@pytest.mark.parametrize("api_provider", ["https://untrusted.example", "openrouter", ""])
def test_arbitrary_provider_destinations_are_rejected(monkeypatch, api_provider):
    monkeypatch.setenv("MUSE_API_PROVIDER", api_provider)
    with pytest.raises(RuntimeError, match="MUSE_API_PROVIDER"):
        MuseSparkProvider(api_key=FAKE_KEY)


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
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.setenv("HARNESS_PROVIDER", "muse")
    with pytest.raises(RuntimeError, match="Gateway"):
        build_provider()


def test_vercel_saved_ai_api_key_alias_is_used_without_extra_calls(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    monkeypatch.setenv("AI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("HARNESS_PROVIDER", "muse")
    assert build_provider().api_key == FAKE_KEY
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "  preferred-fake-gateway-key  ")
    assert build_provider().api_key == "preferred-fake-gateway-key"
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "   ")
    assert build_provider().api_key == FAKE_KEY


@pytest.mark.parametrize("hosting_var,hosting_value", [("VERCEL", "1"), ("VERCEL_ENV", "preview")])
def test_hosted_app_cannot_use_mock_when_app_env_is_missing(
    monkeypatch, hosting_var, hosting_value
):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(hosting_var, hosting_value)
    monkeypatch.setenv("HARNESS_PROVIDER", "mock")
    with pytest.raises(RuntimeError, match="실제 모델"):
        build_provider()


@pytest.mark.parametrize("available", [True, False])
async def test_meta_connection_check_reads_catalog_once_without_inference(monkeypatch, available):
    monkeypatch.setenv("MUSE_API_PROVIDER", "meta")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://api.meta.ai/v1/models"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert not request.content
        return httpx.Response(200, json={"data": [
            {"id": META_MUSE_MODEL if available else "muse-spark-1.3"},
        ]})

    provider = MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await provider.check_connection()
    assert len(calls) == 1
    assert result["inferencePerformed"] is False
    assert result["modelAvailable"] is available
    assert result["status"] == ("ok" if available else "failed")
    assert FAKE_KEY not in json.dumps(result)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
async def test_meta_catalog_errors_never_retry_or_reflect_private_body(monkeypatch, status):
    monkeypatch.setenv("MUSE_API_PROVIDER", "meta")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {
            "code": FAKE_KEY, "type": FAKE_KEY, "message": FAKE_KEY,
        }})

    provider = MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await provider.check_connection()
    assert len(calls) == 1
    assert result["httpStatus"] == status
    assert result["status"] == "failed"
    assert result["upstreamCode"] == "other"
    assert FAKE_KEY not in json.dumps(result)


@pytest.mark.parametrize("response", [
    httpx.Response(200, content="not JSON"),
    httpx.Response(200, json={"data": "invalid"}),
    httpx.Response(200, json={"data": [{"id": None}]}),
])
async def test_meta_catalog_invalid_responses_fail_safely(monkeypatch, response):
    monkeypatch.setenv("MUSE_API_PROVIDER", "meta")
    provider = MuseSparkProvider(httpx.MockTransport(lambda _: response), api_key=FAKE_KEY)
    result = await provider.check_connection()
    assert result["errorCode"] == "invalid_response"
    assert result["inferencePerformed"] is False


async def test_gateway_catalog_check_never_switches_provider_or_calls_ai():
    calls = []
    provider = MuseSparkProvider(httpx.MockTransport(lambda request: calls.append(request)),
                                api_key=FAKE_KEY)
    assert (await provider.check_connection())["status"] == "unavailable"
    assert calls == []
