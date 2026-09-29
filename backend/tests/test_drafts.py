"""Hypothesis design uses AI; these independent fixtures test the compiler boundary."""

import json

import httpx
import pytest
from pydantic import ValidationError

from backend.app.draft_compiler import DraftCompiler
from backend.app.models import ConversionResponse, ConvertRequest, DraftIR
from backend.app.openai_policy import OPENAI_POLICY
from backend.app.openai_provider import OpenAIProvider
from backend.app.prompts import BASE_SYSTEM_PROMPT
from backend.app.service import HarnessService
from backend.tests.provider_fixtures import FAKE_KEY, reply


def draft(expression):
    return DraftIR(
        schemaVersion="draft-v2", status="ok", hypothesis="관찰한 특징으로 종목에 점수를 줍니다.",
        expression=expression, assumptions=["관찰 기간과 측정 방법은 AI의 초안 가정입니다."],
        improvementSuggestions=[{
            "title": "가정 비교", "rationale": "측정 방법에 따른 차이를 확인합니다.",
            "experiment": "관찰 기간을 달리해 결과를 비교합니다.",
        }],
        refinementOptions=[{
            "label": "관찰 기간 변경", "description": "관찰 기간을 늘려 봅니다.",
            "strategy": "최근 40일 일간 수익률 변동성이 낮은 종목을 선호한다.",
        }], reason="",
    )


async def convert(strategy, ir):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["schemaVersion"]["const"] == "draft-v2"
        assert body["max_completion_tokens"] == 1024
        assert body["reasoning_effort"] == "none"
        return httpx.Response(200, json=reply(content=ir.model_dump_json()))

    provider = OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await HarnessService(provider).convert(ConvertRequest(strategy=strategy))
    assert len(calls) == 1
    return result


@pytest.mark.parametrize("strategy,expression,meaning", [
    ("덜 출렁이는 종목이 좋아", "rank(-ts_std_dev(returns,20))", "표준편차"),
    ("갑자기 사람들이 몰리는 주식이 궁금해", "rank(volume/ts_mean(volume,20))", "거래량"),
    ("평소보다 싸진 주식은 다시 돌아오지 않을까", "rank(-(close/ts_mean(close,20)-1))", "평균"),
    ("잘 오르면서 안정적인 주식이 좋아",
     "rank(close/ts_delay(close,21)-1)-rank(ts_std_dev(returns,20))", "표준편차"),
    ("같은 업종 친구들보다 뒤처진 애들이 따라가지 않을까",
     "group_rank(-(close/ts_delay(close,21)-1),industry)", "산업내 상대 순위"),
    ("가격과 거래량이 같이 움직이는 주식을 찾아줘", "rank(ts_corr(returns,volume,20))", "상관계수"),
])
async def test_unnamed_hypothesis_can_use_composed_measurements(strategy, expression, meaning):
    result = await convert(strategy, draft(expression))
    assert result.status == "PASS", result.warnings
    assert meaning in result.strategyExplanation
    assert result.assumptions and result.refinementOptions and result.improvementSuggestions
    assert result.intentMapping
    assert ConversionResponse.model_validate(result.model_dump()) == result


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo unsafe')", "close.__class__", "close[0]",
    "[close for x in volume]", "lambda: close", "close ** 100000",
    "unknown(close)", "rank(per)", "ts_mean(close,-20)", "ts_delay(close,0)",
    "ts_mean(close,1.5)", "ts_mean(close,1001)", "rank(close,volume)",
    "rank(x=close)", "rank(industry)", "close / 0", "close + True", "rank(1e999)",
    "trade_when(volume>0,rank(close),1)", "trade_when(volume,rank(close),-1)",
    "group_rank(close,returns)", "ts_mean(close,20+1)", "1", "volume>0",
])
def test_expression_allowlist_rejects_invalid_or_executable_code(expression):
    with pytest.raises(ValueError):
        DraftCompiler().compile(expression)


def test_expression_depth_and_size_are_bounded():
    for expression in (
        "rank(" * 20 + "close" + ")" * 20, "+".join(["close"] * 100), "close + " + "9" * 1000,
    ):
        with pytest.raises(ValueError):
            DraftCompiler().compile(expression)


EXPLICIT = (
    "최근 5일 수익률이 높은 종목을 선호해. "
    "거래량이 최근 20일 평균의 1.5배 이상일 때만 거래해줘."
)
EXPRESSION = "trade_when(volume>=1.5*ts_mean(volume,20),rank(close/ts_delay(close,5)-1),-1)"


async def test_explicit_signal_filter_composition_keeps_independent_windows():
    result = await convert(EXPLICIT, draft(EXPRESSION))
    assert result.status == "PASS", result.warnings
    assert "직전 값을 유지" in result.strategyExplanation
    equivalent = EXPRESSION.replace("volume>=1.5*ts_mean(volume,20)",
                                    "ts_mean(volume,20)*1.5<=volume")
    assert (await convert(EXPLICIT, draft(equivalent))).status == "PASS"


@pytest.mark.parametrize("expression", [
    EXPRESSION.replace("ts_delay(close,5)", "ts_delay(close,20)"),
    EXPRESSION.replace("ts_mean(volume,20)", "ts_mean(volume,5)"),
    EXPRESSION.replace(">=", ">"),
    EXPRESSION.replace("1.5", "2"),
    "rank(close/ts_delay(close,5)-1) + rank(volume/ts_mean(volume,20)*1.5)",
])
async def test_explicit_constraints_cannot_move_to_another_slot(expression):
    result = await convert(EXPLICIT, draft(expression))
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert result.refinementOptions == []


async def test_unsupported_data_explains_why_instead_of_silently_substituting():
    ir = draft("")
    ir.status = "unsupported"
    ir.reason = "현재 제공되는 데이터에 기업 이익이 없습니다."
    result = await convert("이익이 늘어나는 회사가 좋아", ir)
    assert result.status == "REJECTED"
    assert ir.reason in result.warnings


async def test_invalid_draft_does_not_expose_ai_guidance_as_a_success():
    result = await convert("덜 출렁이는 종목", draft("rank(unknown_data)"))
    assert result.status == "REJECTED"
    assert result.strategyExplanation is None
    assert result.improvementSuggestions == []


async def test_explicit_return_volatility_is_not_confused_with_cumulative_return():
    result = await convert(
        "최근 20일 수익률 변동성이 낮으면 좋아", draft("rank(-ts_std_dev(returns,20))")
    )
    assert result.status == "PASS", result.warnings


async def test_one_day_return_may_use_the_daily_return_field():
    result = await convert("최근 1일 수익률이 높은 종목", draft("rank(returns)"))
    assert result.status == "PASS", result.warnings


@pytest.mark.parametrize(
    "strategy", ["PER이 낮으면 좋아", "뉴스 감성이 좋은 주식", "매수 후 5일 보유"]
)
async def test_confident_draft_cannot_drop_unavailable_data_or_execution_rules(strategy):
    result = await convert(strategy, draft("rank(ts_mean(returns,5))"))
    assert result.status == "REJECTED"


def test_new_schema_stays_within_fixed_input_budget_and_rejects_unknown_keys():
    OPENAI_POLICY.payload(BASE_SYSTEM_PROMPT, "가" * 2000)
    with pytest.raises(ValidationError):
        DraftIR.model_validate({**draft("rank(volume)").model_dump(), "execute": True})
