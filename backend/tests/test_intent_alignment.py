"""Source evidence, constrained measurements and independent scoring-direction checks."""

import json

import httpx
import pytest
from pydantic import ValidationError

from backend.app import intent_compiler
from backend.app.intent_compiler import preference_behavior_errors, score_expression
from backend.app.models import ConversionResponse, ConvertRequest, IntentIR, IntentMetric
from backend.app.openai_policy import OPENAI_POLICY
from backend.app.openai_provider import OpenAIProvider
from backend.app.prompts import BASE_SYSTEM_PROMPT
from backend.app.provider_errors import ProviderError
from backend.app.service import HarnessService
from backend.tests.provider_fixtures import FAKE_KEY, example_ir, intent_ir, reply
from backend.tests.test_drafts import draft

PEERS = "같은 업종 애들은 다 올랐는데 혼자 못 오른 애가 따라갈 것 같아."
INTRADAY = "아침엔 별로였는데 장 끝날 때 힘이 세진 주식이 좋아 보여."


def metric(source, **changes):
    return IntentMetric.model_validate({
        "source": source, "operation": "return", "field": "close", "window": 21,
        "reference": None, "preference": "higher", "group": "none", "weight": 1,
        **changes,
    })


def plan(metrics):
    ir = intent_ir()
    ir.metrics, ir.entry = metrics, None
    return ir


async def convert(strategy, ir):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["schemaVersion"]["const"] == "intent-v3"
        assert "expression" not in schema["properties"]
        assert body["max_completion_tokens"] == 1024
        assert body["reasoning_effort"] == "none"
        return httpx.Response(200, json=reply(content=ir.model_dump_json()))

    provider = OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await HarnessService(provider).convert(ConvertRequest(strategy=strategy))
    assert len(calls) == 1
    return result


async def test_peer_catch_up_compiles_to_lower_return_preference_within_industry():
    ir = plan([metric(PEERS, preference="lower", group="industry")])
    result = await convert(PEERS, ir)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == (
        "(1 - group_rank(((close / ts_delay(close, 21)) - 1), industry))"
    )
    assert "낮을수록 높은 점수" in result.strategyExplanation
    assert "같은 산업" in result.strategyExplanation
    assert result.validation.intentPlanChecked is True
    assert ConversionResponse.model_validate(result.model_dump()) == result


async def test_intraday_recovery_does_not_acquire_unrequested_momentum_or_penalty():
    ir = plan([metric(INTRADAY, operation="ratio", reference="open", window=1)])
    result = await convert(INTRADAY, ir)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == "rank(((close / open) - 1))"
    assert "ts_" not in result.fastExpression
    assert result.validation.intentPlanChecked is True


@pytest.mark.parametrize("preference,group", [
    ("higher", "none"), ("lower", "none"), ("higher", "industry"), ("lower", "industry"),
])
def test_counterfactual_check_detects_reversed_score(preference, group):
    metrics = [metric("수익률", preference=preference, group=group)]
    expression = score_expression(metrics)
    assert preference_behavior_errors(expression, metrics) == []
    reversed_expression = f"1 - ({expression})"
    assert preference_behavior_errors(reversed_expression, metrics)


@pytest.mark.parametrize("bad_expression", [
    "group_rank((close / ts_delay(close, 21) - 1), industry)",
    # Actual pre-fix output: unrequested smoothing and wrong sign.
    "group_neutralize(rank(ts_mean((close / ts_delay(close, 21) - 1), 21)), sector)",
])
async def test_wrong_compiler_output_is_rejected(monkeypatch, bad_expression):
    monkeypatch.setattr(intent_compiler, "score_expression", lambda _: bad_expression)
    result = await convert(PEERS, plan([metric(PEERS, preference="lower", group="industry")]))
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert result.validation.intentPlanChecked is False
    assert not result.refinementOptions


def test_actual_bad_intraday_output_fails_plan_to_code_check():
    bad = (
        "rank((((close / open) - 1) - ts_rank(abs((close / open) - 1), 21))"
        " + ts_rank((close / ts_delay(close, 5) - 1), 21))"
    )
    metrics = [metric(INTRADAY, operation="ratio", reference="open", window=1)]
    assert preference_behavior_errors(bad, metrics)


async def test_distinct_requested_preferences_are_combined_after_direction_and_rank():
    strategy = "덜 출렁이면서 평소보다 사람들이 몰리는 주식이 좋아"
    ir = plan([
        metric("덜 출렁", operation="std_dev", field="returns", preference="lower"),
        metric("평소보다 사람들이 몰리는", operation="relative_mean", field="volume"),
    ])
    result = await convert(strategy, ir)
    assert result.status == "PASS", result.warnings
    assert "1 - rank(ts_std_dev(returns, 21))" in result.fastExpression
    assert "rank(((volume / ts_mean(volume, 21)) - 1))" in result.fastExpression
    assert preference_behavior_errors(score_expression(ir.metrics), ir.metrics) == []


@pytest.mark.parametrize("window,condition,expected", [
    (5, "volume >= 1.5 * ts_mean(volume, 20)", "PASS"),
    (21, "volume >= 1.5 * ts_mean(volume, 20)", "REJECTED"),
    (5, "volume >= 1.5 * ts_mean(volume, 5)", "REJECTED"),
    (5, "volume > 1.5 * ts_mean(volume, 20)", "REJECTED"),
    (5, "volume >= 2 * ts_mean(volume, 20)", "REJECTED"),
])
async def test_explicit_return_and_volume_gate_survive_new_plan(window, condition, expected):
    strategy = (
        "최근 5일 수익률이 높은 종목을 선호해. "
        "거래량이 최근 20일 평균의 1.5배 이상일 때만 거래해줘."
    )
    ir = intent_ir()
    ir.metrics = [metric("최근 5일 수익률이 높은 종목을 선호해", window=window)]
    ir.entry.source = "거래량이 최근 20일 평균의 1.5배 이상일 때만 거래해줘"
    ir.entry.condition = condition
    result = await convert(strategy, ir)
    assert result.status == expected, result.warnings
    if expected == "PASS":
        assert result.fastExpression == (
            "trade_when(volume >= (1.5 * ts_mean(volume, 20)), "
            "rank(((close / ts_delay(close, 5)) - 1)), -1)"
        )
    else:
        assert result.fastExpression is None


@pytest.mark.parametrize("extra_source", [INTRADAY, "장 끝날 때 힘이 세진", "변동성이 낮은"])
async def test_extra_signals_cannot_reuse_a_source_or_invent_evidence(extra_source):
    ir = plan([
        metric(INTRADAY, operation="ratio", reference="open", window=1),
        metric(extra_source, operation="std_dev", field="returns", preference="lower"),
    ])
    result = await convert(INTRADAY, ir)
    assert result.status == "REJECTED"
    assert result.validation.intentPlanChecked is False


async def test_peer_context_cannot_be_dropped():
    result = await convert(PEERS, plan([metric(PEERS, preference="lower")]))
    assert result.status == "REJECTED"
    assert any("동종업계" in warning for warning in result.warnings)


@pytest.mark.parametrize("source", ["   ", "\t\n", "가 "])
async def test_whitespace_cannot_supply_source_evidence(source):
    result = await convert("주가가 오르는 게 좋아", plan([metric(source)]))
    assert result.status == "REJECTED"
    assert result.validation.intentPlanChecked is False


async def test_duplicate_measurement_cannot_cancel_or_hide_an_intent():
    result = await convert("수익률 상승 수익률 하락", plan([
        metric("수익률 상승"), metric("수익률 하락", preference="lower"),
    ]))
    assert result.status == "REJECTED"


@pytest.mark.parametrize("changes", [
    {"weight": -1}, {"weight": 0}, {"field": "-returns"}, {"operation": "rank"},
    {"operation": "ratio", "reference": "open", "window": 21},
    {"operation": "ratio", "reference": "close", "window": 1},
    {"operation": "return", "field": "returns"},
])
def test_measurement_cannot_smuggle_in_a_sign_or_extra_formula(changes):
    with pytest.raises(ValidationError):
        metric("기준", **changes)


@pytest.mark.parametrize("old", [example_ir(), draft("rank(volume)")])
async def test_fresh_openai_reply_cannot_downgrade_to_unchecked_schema(old):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=reply(content=old.model_dump_json()))

    provider = OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    with pytest.raises(ProviderError) as error:
        await provider.interpret(BASE_SYSTEM_PROMPT, "아이디어")
    assert error.value.code == "invalid_response"
    assert len(calls) == 1


def test_plan_disallows_direct_code_and_fits_request_budget():
    ir = plan([metric("수익률")])
    with pytest.raises(ValidationError):
        IntentIR.model_validate({**ir.model_dump(), "expression": "rank(close)"})
    OPENAI_POLICY.payload(BASE_SYSTEM_PROMPT, "가" * 2000)


@pytest.mark.parametrize("operation,field,reference,window", [
    ("raw", "volume", None, 1), ("delta", "close", None, 10),
    ("mean", "returns", None, 21), ("std_dev", "returns", None, 21),
    ("relative_mean", "close", None, 21), ("ratio", "close", "open", 1),
    ("difference", "close", "open", 1), ("range_position", "close", None, 1),
    ("correlation", "returns", "volume", 21),
])
async def test_measurement_primitives_remain_composable(operation, field, reference, window):
    m = metric(
        "관찰한 특징", operation=operation, field=field, reference=reference, window=window,
    )
    # Source grounding and direction do not rely on a named strategy/family.
    result = await convert("관찰한 특징", plan([m]))
    assert result.status == "PASS", result.warnings
