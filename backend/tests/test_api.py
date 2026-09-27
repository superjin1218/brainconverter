import hashlib
import hmac
import json
import os
import time

from fastapi.testclient import TestClient

os.environ["APP_ENV"] = "development"
os.environ["HARNESS_PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "none"  # This file explicitly exercises the unauthenticated mock API.

from backend.app.config import AppConfig  # noqa: E402, I001
from backend.app.main import app, create_app  # noqa: E402, I001
from backend.app.provider import MockSemanticProvider  # noqa: E402, I001


client = TestClient(app)


def test_health_and_dashboard_are_served():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "BRAIN Alpha Harness" in dashboard.text
    assert dashboard.headers["cache-control"] == "no-store"
    assert client.get("/js/provider.js").headers["cache-control"] == "no-store"


def test_convert_endpoint_returns_valid_bundle():
    response = client.post(
        "/api/convert",
        json={"strategy": "최근 5일 동안 많이 떨어진 종목을 매수한다."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PASS"
    assert payload["fastExpression"] == "rank(-ts_delta(close, 5))"
    assert len(payload["simulationSettings"]) == 12


def test_production_convert_requires_valid_gateway_signature():
    production_app = create_app(
        AppConfig(
            environment="production",
            gateway_shared_secret="test-secret",
            allowed_emails=frozenset({"member@example.com"}),
            static_directory=AppConfig.from_environment().static_directory,
        ),
        provider_factory=MockSemanticProvider,
    )
    production_client = TestClient(production_app)
    unsigned = production_client.post("/api/convert", json={"strategy": "최근 5일 하락 종목"})
    assert unsigned.status_code == 401

    body = json.dumps({"strategy": "최근 5일 하락 종목"}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    request_id = "00000000-0000-4000-8000-000000000001"
    prefix = f"{timestamp}\nPOST\n/api/convert\nmember@example.com\n{request_id}\n"
    signature = hmac.new(b"test-secret", prefix.encode() + body, hashlib.sha256).hexdigest()
    signed = production_client.post(
        "/api/convert",
        content=body,
        headers={
            "content-type": "application/json",
            "x-gateway-timestamp": timestamp,
            "x-gateway-signature": signature,
            "x-user-email": "member@example.com",
            "x-request-id": request_id,
        },
    )
    assert signed.status_code == 200
    assert production_client.get("/openapi.json").status_code == 404
    tampered = production_client.post(
        "/api/convert",
        content=body,
        headers={**signed.request.headers, "x-user-email": "intruder@example.com"},
    )
    assert tampered.status_code == 401


def test_oversized_and_blank_input_are_rejected():
    assert client.post("/api/convert", content=b"x" * 17000).status_code == 413
    assert client.post("/api/convert", json={"strategy": "   "}).status_code == 422
