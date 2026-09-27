import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import local_provider
from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.app.provider import MockSemanticProvider, MuseSparkProvider
from backend.app.provider_errors import MESSAGES
from backend.tests.test_provider import reply

ORIGIN = "http://127.0.0.1:8080"
HEADERS = {"origin": ORIGIN, "x-local-setup": "1"}
PATH = "/api/local/provider"
FAKE_KEY = "sk-local-test-placeholder-never-a-real-key"


def make_app(environment="development"):
    return create_app(
        AppConfig(
            environment=environment,
            gateway_shared_secret="test-secret",
            allowed_emails=frozenset(),
            static_directory=AppConfig.from_environment().static_directory,
        ),
        provider_factory=MockSemanticProvider,
    )


@pytest.fixture
def local_client(monkeypatch):
    monkeypatch.setenv("HARNESS_PROVIDER", "mock")
    monkeypatch.setenv("MUSE_MODEL", "meta/muse-spark-1.3-contributor")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(make_app(), base_url=ORIGIN, client=("127.0.0.1", 50000)) as client:
        yield client


def test_key_switches_actual_provider_and_disconnects_without_persisting(local_client, monkeypatch):
    calls = []

    def handler(request):
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert json.loads(request.content)["model"] == "meta/muse-spark-1.3-contributor"
        calls.append(request.url.path)
        return httpx.Response(200, json=reply())

    monkeypatch.setattr(
        local_provider,
        "MuseSparkProvider",
        lambda *, api_key: MuseSparkProvider(httpx.MockTransport(handler), api_key=api_key),
    )
    assert local_client.get(PATH).json()["provider"] == "mock"
    # A client-supplied expensive model cannot override the server's budget profile.
    response = local_client.post(
        PATH, json={"apiKey": FAKE_KEY, "model": "gpt-5-pro"}, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json() == {
        "provider": "muse",
        "keyConfigured": True,
        "model": "meta/muse-spark-1.3-contributor",
    }
    assert FAKE_KEY not in response.text
    assert FAKE_KEY not in local_client.get(PATH).text
    assert "no-store" in response.headers["cache-control"]
    assert not calls  # Setting the key does not claim successful OpenAI authentication.
    assert not os.getenv("OPENAI_API_KEY")

    response = local_client.post(
        "/api/convert", json={"strategy": "최근 5일 하락 종목 매수", "trainingConsent": True}
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "muse"
    assert response.json()["usage"]["inputTokens"] > 0
    assert calls == ["/v1/chat/completions"]

    assert local_client.delete(PATH, headers=HEADERS).json()["keyConfigured"] is False
    response = local_client.post(
        "/api/convert", json={"strategy": "최근 5일 하락 종목 매수", "trainingConsent": True}
    )
    assert response.json()["provider"] == "mock"
    assert len(calls) == 1


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_key_configuration_does_not_exist_outside_development(environment):
    with TestClient(make_app(environment), base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
        for method in ("GET", "POST", "DELETE"):
            response = client.request(method, PATH, headers=HEADERS)
            assert response.status_code in {404, 405}
        assert not any(getattr(route, "path", "").startswith(PATH) for route in client.app.routes)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": ORIGIN},
        {"x-local-setup": "1"},
        {**HEADERS, "origin": "https://untrusted.example"},
        {**HEADERS, "origin": "http://127.0.0.1:9000"},
        {**HEADERS, "origin": "null"},
        {**HEADERS, "host": "untrusted.example"},
        {**HEADERS, "x-forwarded-for": "127.0.0.1"},
    ],
)
def test_cross_origin_and_forwarded_key_changes_are_blocked(local_client, headers):
    response = local_client.post(PATH, json={"apiKey": FAKE_KEY}, headers=headers)
    assert response.status_code == 403
    assert FAKE_KEY not in response.text
    assert local_client.get(PATH).json()["provider"] == "mock"


def test_non_loopback_clients_are_blocked():
    with TestClient(make_app(), base_url=ORIGIN, client=("192.0.2.10", 1)) as client:
        assert client.get(PATH).status_code == 403
        assert client.post(PATH, json={"apiKey": FAKE_KEY}, headers=HEADERS).status_code == 403


@pytest.mark.parametrize(
    "content",
    [
        '{"apiKey":"secret-that-must-not-be-reflected!"}',
        '{"apiKey":{"private":"secret-that-must-not-be-reflected"}}',
        '{"apiKey":"secret-that-must-not-be-reflected',
        '["secret-that-must-not-be-reflected"]',
    ],
)
def test_bad_input_never_echoes_key_material(local_client, content):
    response = local_client.post(PATH, content=content, headers=HEADERS)
    assert response.status_code == 400
    assert "secret-that-must-not-be-reflected" not in response.text


def test_changing_key_while_conversion_is_running_is_blocked(local_client):
    local_client.app.state.active_conversions = 1
    assert local_client.post(PATH, json={"apiKey": FAKE_KEY}, headers=HEADERS).status_code == 409
    assert local_client.delete(PATH, headers=HEADERS).status_code == 409


def test_fresh_server_does_not_keep_previously_entered_key(local_client):
    local_client.post(PATH, json={"apiKey": FAKE_KEY}, headers=HEADERS)
    with TestClient(make_app(), base_url=ORIGIN, client=("127.0.0.1", 1)) as fresh_client:
        assert fresh_client.get(PATH).json()["keyConfigured"] is False


@pytest.mark.parametrize(
    ("actual_provider", "expected_provider"), [("mock", "muse"), ("muse", "mock")]
)
def test_changed_provider_blocks_conversion_before_any_model_call(
    local_client, monkeypatch, actual_provider, expected_provider
):
    calls = []

    async def interpret(*args):
        calls.append(1)
        raise AssertionError("A mismatched provider must never run.")

    monkeypatch.setattr(MockSemanticProvider, "interpret", interpret)
    monkeypatch.setattr(MuseSparkProvider, "interpret", interpret)
    if actual_provider == "muse":
        local_client.post(PATH, json={"apiKey": FAKE_KEY}, headers=HEADERS)
    response = local_client.post(
        "/api/convert",
        json={"strategy": "최근 5일 하락 종목 매수", "trainingConsent": True},
        headers={"X-Expected-Provider": expected_provider},
    )
    assert response.status_code == 409
    assert "이번 변환은 실행하지 않았습니다" in response.json()["detail"]
    assert not calls
    assert local_client.app.state.active_conversions == 0


def test_matching_provider_allows_conversion(local_client):
    response = local_client.post(
        "/api/convert",
        json={"strategy": "최근 5일 하락 종목 매수", "trainingConsent": True},
        headers={"X-Expected-Provider": "mock"},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


@pytest.mark.parametrize(
    ("status", "upstream_code", "expected_code"),
    [
        (401, "invalid_api_key", "authentication"),
        (403, None, "permission"),
        (404, "model_not_found", "model_access"),
        (400, "unsupported_parameter", "invalid_request"),
        (429, "credit_balance_exhausted", "credits"),
        (429, "project_spend_limit_exceeded", "spend_limit"),
        (429, "organization_usage_limit_exceeded", "usage_limit"),
        (429, "insufficient_quota", "quota"),
        (429, "rate_limit_exceeded", "rate_limit"),
    ],
)
def test_real_provider_failure_reaches_ui_without_secret_or_extra_requests(
    local_client, monkeypatch, caplog, status, upstream_code, expected_code
):
    calls = []
    private_detail = "private-provider-response-must-not-escape"
    strategy = "최근 5일 하락 종목 매수"

    def handler(_):
        calls.append(1)
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": upstream_code,
                    "message": f"{private_detail} {FAKE_KEY} {strategy}",
                }
            },
        )

    monkeypatch.setattr(
        local_provider,
        "MuseSparkProvider",
        lambda *, api_key: MuseSparkProvider(httpx.MockTransport(handler), api_key=api_key),
    )
    assert local_client.post(PATH, json={"apiKey": FAKE_KEY}, headers=HEADERS).status_code == 200
    assert not calls

    response = local_client.post(
        "/api/convert", json={"strategy": strategy, "trainingConsent": True}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": MESSAGES[expected_code]}
    assert response.headers["cache-control"] == "no-store"
    assert calls == [1]
    assert local_client.app.state.active_conversions == 0
    assert local_client.get(PATH).json()["keyConfigured"] is True
    for private_value in (private_detail, FAKE_KEY, strategy):
        assert private_value not in response.text
        assert private_value not in caplog.text

    # Failure cannot leave the settings dialog locked in an active conversion state.
    assert local_client.delete(PATH, headers=HEADERS).status_code == 200
