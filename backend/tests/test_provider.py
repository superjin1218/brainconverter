import json

import httpx
import pytest

from backend.app.openai_policy import OPENAI_MODEL
from backend.app.openai_provider import OpenAIProvider
from backend.app.provider_errors import MESSAGES, ProviderError
from backend.app.response_schema import strict_schema
from backend.tests.provider_fixtures import FAKE_KEY, intent_ir, reply

PRIVATE_DETAIL = "private-upstream-detail-must-not-be-exposed"
PRIVATE_STRATEGY = "private-user-strategy-must-not-be-exposed"


async def test_structured_request_and_usage():

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == OPENAI_MODEL
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["max_completion_tokens"] == 1024
        assert "temperature" not in body
        return httpx.Response(200, json=reply())

    result = await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
        "JSON", "5일 전략"
    )
    assert result.ir == intent_ir()
    assert result.cost_microusd == 1485


async def test_truncated_response_stops_without_spending_on_a_second_request():
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(200, json=reply(finish="length"))

    with pytest.raises(ProviderError) as exc:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "JSON", "5일 전략"
        )
    assert exc.value.code == "output_limit"
    assert calls == [1]


@pytest.mark.parametrize(
    ("status", "upstream_code", "upstream_type", "expected_code"),
    [
        (401, "invalid_api_key", None, "authentication"),
        (403, None, None, "permission"),
        (403, "ip_not_authorized", None, "ip_restricted"),
        (404, None, None, "not_found"),
        (404, "model_not_found", None, "model_access"),
        (400, "model_not_found", None, "model_access"),
        (400, "unsupported_parameter", None, "invalid_request"),
        (429, "credit_balance_exhausted", None, "credits"),
        (429, "organization_spend_limit_exceeded", None, "spend_limit"),
        (429, "project_spend_limit_exceeded", None, "spend_limit"),
        (429, "organization_usage_limit_exceeded", None, "usage_limit"),
        (429, "insufficient_quota", None, "quota"),
        (429, None, "insufficient_quota", "quota"),
        (429, "rate_limit_exceeded", None, "rate_limit"),
    ],
)
async def test_http_errors_explain_cause_without_retrying_or_leaking(
    status, upstream_code, upstream_type, expected_code, caplog
):
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": upstream_code,
                    "type": upstream_type,
                    "message": f"{PRIVATE_DETAIL} {FAKE_KEY} {PRIVATE_STRATEGY}",
                }
            },
        )

    with pytest.raises(ProviderError) as exc:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "JSON", PRIVATE_STRATEGY
        )
    assert calls == [1]
    assert exc.value.code == expected_code
    assert str(exc.value) == MESSAGES[expected_code]
    assert f"code={expected_code}" in caplog.text
    for private_value in (PRIVATE_DETAIL, FAKE_KEY, PRIVATE_STRATEGY):
        assert private_value not in str(exc.value)
        assert private_value not in caplog.text


@pytest.mark.parametrize(
    ("body", "kind", "shape", "upstream"),
    [
        (None, "not_found", "empty", "none"),
        (
            {"error": {"code": "model_not_found", "message": PRIVATE_DETAIL}},
            "model_access",
            "json_error",
            "model_not_found",
        ),
        (
            {"error": {"code": FAKE_KEY, "message": PRIVATE_STRATEGY}},
            "not_found",
            "json_error",
            "other",
        ),
    ],
)
async def test_not_found_diagnostics_distinguish_model_and_routing_without_leaks(
    body, kind, shape, upstream, caplog
):
    def handler(_):
        return httpx.Response(404, **({"json": body} if body is not None else {"content": b""}))

    with pytest.raises(ProviderError) as exc:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "JSON", PRIVATE_STRATEGY
        )
    assert exc.value.code == kind
    assert f"http_status=404 upstream_code={upstream} response_shape={shape}" in caplog.text
    for value in (FAKE_KEY, PRIVATE_DETAIL, PRIVATE_STRATEGY):
        assert value not in caplog.text


@pytest.mark.parametrize(
    ("failure_type", "expected_code"),
    [
        (httpx.ConnectError, "connection"),
        (httpx.RemoteProtocolError, "connection"),
        (httpx.ConnectTimeout, "timeout"),
        (httpx.ReadTimeout, "timeout"),
    ],
)
async def test_transport_failure_does_not_repeat_a_potentially_billable_request(
    failure_type, expected_code, caplog
):
    calls = []

    def handler(request):
        calls.append(1)
        raise failure_type(f"{FAKE_KEY} {PRIVATE_DETAIL}", request=request)

    with pytest.raises(ProviderError) as exc:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "JSON", PRIVATE_STRATEGY
        )
    assert calls == [1]
    assert exc.value.code == expected_code
    for private_value in (FAKE_KEY, PRIVATE_DETAIL, PRIVATE_STRATEGY):
        assert private_value not in str(exc.value)
        assert private_value not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        [],
        "unexpected response body",
        {},
        {"choices": []},
        {"choices": [None]},
        {"choices": [{"finish_reason": "stop", "message": []}]},
        reply(content="not JSON"),
        reply(content='{"status":"ok"}'),
        reply(finish="content_filter"),
        {**reply(), "usage": None},
        {**reply(), "usage": {"prompt_tokens": -1, "completion_tokens": 100}},
    ],
)
async def test_invalid_response_shape_stops_with_safe_actionable_error(body):
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(
            200, json={"model": OPENAI_MODEL, **body} if isinstance(body, dict) else body,
        )

    with pytest.raises(ProviderError) as exc:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "JSON", "5일 전략"
        )
    assert calls == [1]
    assert exc.value.code == "invalid_response"


async def test_refusal_is_not_retried_or_returned_verbatim(caplog):
    calls = []
    body = reply()
    body["choices"][0]["message"]["refusal"] = f"{PRIVATE_DETAIL} {FAKE_KEY}"

    def handler(_):
        calls.append(1)
        return httpx.Response(200, json=body)

    with pytest.raises(ProviderError) as exc:
        await OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY).interpret(
            "JSON", PRIVATE_STRATEGY
        )
    assert calls == [1]
    assert exc.value.code == "refusal"
    for private_value in (PRIVATE_DETAIL, FAKE_KEY, PRIVATE_STRATEGY):
        assert private_value not in str(exc.value)
        assert private_value not in caplog.text


def test_every_schema_object_forbids_extra_fields():
    schema = strict_schema()
    for obj in [schema, *schema["$defs"].values()]:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
