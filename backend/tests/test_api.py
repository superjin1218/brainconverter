import pytest
from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.app.mock_provider import MockSemanticProvider


@pytest.fixture
def client():
    config = AppConfig(
        environment="development",
        auth_mode="none",
        static_directory=AppConfig.from_environment().static_directory,
    )
    with TestClient(
        create_app(config, provider_factory=MockSemanticProvider),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
        headers={"origin": "http://127.0.0.1", "x-requested-with": "brain-site"},
    ) as site:
        yield site


def test_health_and_dashboard_are_served(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "BRAIN Alpha Harness" in dashboard.text
    assert dashboard.headers["cache-control"] == "no-store"
    assert client.get("/js/provider.js").headers["cache-control"] == "no-store"


def test_convert_endpoint_returns_valid_bundle(client):
    response = client.post(
        "/api/convert",
        json={"strategy": "최근 5일 동안 많이 떨어진 종목을 매수한다."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PASS"
    assert payload["fastExpression"] == "rank(-ts_delta(close, 5))"
    assert len(payload["simulationSettings"]) == 12


def test_oversized_and_blank_input_are_rejected(client):
    assert client.post("/api/convert", content=b"x" * 17000).status_code == 413
    assert client.post("/api/convert", json={"strategy": "   "}).status_code == 422


def test_get_and_head_cannot_bypass_body_cap_before_authentication():
    config = AppConfig(
        environment="production",
        static_directory=AppConfig.from_environment().static_directory,
    )
    calls = []

    def provider():
        calls.append(True)
        return MockSemanticProvider()

    with TestClient(create_app(config, provider)) as site:
        for method in ("GET", "HEAD"):
            assert site.request(method, "/api/convert", content=b"x" * 17000).status_code == 413
    assert calls == []


def test_local_unauthenticated_conversion_blocks_external_host_origin_and_remote_peer(client):
    for headers in (
        {"origin": "https://untrusted.example"},
        {"host": "untrusted.example", "origin": "http://untrusted.example"},
        {"x-forwarded-for": "127.0.0.1"},
    ):
        assert (
            client.post(
                "/api/convert", json={"strategy": "최근 5일 하락"}, headers=headers
            ).status_code
            == 403
        )
    with TestClient(
        client.app,
        base_url="http://127.0.0.1",
        client=("192.0.2.10", 1),
        headers={"origin": "http://127.0.0.1", "x-requested-with": "brain-site"},
    ) as remote:
        assert remote.post("/api/convert", json={"strategy": "최근 5일 하락"}).status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [
        ("reasoning_effort", "xhigh"),
        ("model", "gpt-5.4"),
        ("max_completion_tokens", 99999),
    ],
)
def test_conversion_rejects_client_model_policy_overrides(client, field, value):
    assert client.app.state.harness_service is None
    response = client.post("/api/convert", json={"strategy": "최근 5일 하락", field: value})
    assert response.status_code == 422
    assert client.app.state.harness_service is None


@pytest.mark.parametrize("mode", ["gateway", "other"])
def test_obsolete_or_unknown_auth_mode_cannot_disable_membership(mode):
    with pytest.raises(ValueError, match="AUTH_MODE"):
        AppConfig(
            environment="production",
            auth_mode=mode,
            static_directory=AppConfig.from_environment().static_directory,
        )
