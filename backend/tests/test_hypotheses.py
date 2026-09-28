"""Short hypotheses, independent provider errors, and refinement round trips."""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from backend.app.compiler import compile_fe, validate_compiled_fe
from backend.app.mock_provider import MockSemanticProvider
from backend.app.models import ConversionResponse, ConvertRequest, StrategyIR
from backend.app.openai_policy import OPENAI_POLICY
from backend.app.openai_provider import OpenAIProvider
from backend.app.prompts import BASE_SYSTEM_PROMPT
from backend.app.provider_diagnostics import diagnostic_runtime
from backend.app.provider_types import ProviderResult
from backend.app.service import HarnessService
from backend.tests.provider_fixtures import FAKE_KEY, example_ir, reply


@pytest.mark.parametrize("filename", ["hypotheses.py", "models.py", "SKILL.md"])
def test_deployment_revision_tracks_interpretation_rules(monkeypatch, filename):
    before = diagnostic_runtime()["providerSourceSha256"]
    read_bytes = Path.read_bytes

    def changed_rule(path):
        content = read_bytes(path)
        return content + b"\nchanged rule" if path.name == filename else content

    monkeypatch.setattr(Path, "read_bytes", changed_rule)
    after = diagnostic_runtime()["providerSourceSha256"]
    assert before and after and before != after


def period_ir(window=21, direction="up"):
    ir = example_ir()
    ir.signal.operation = "return"
    ir.signal.window = window
    ir.signal.direction = direction
    ir.entry.enabled = False
    ir.neutralization = "none"
    return ir


@pytest.mark.parametrize(
    "strategy,window,direction",
    [
        ("1달 기준 모멘텀 전략 만들어줘", 21, "up"),
        ("한 달 모멘텀", 21, "up"),
        ("일주일 반전추세 전략을 만들어줘", 5, "down"),
        ("수익률 높은거가 떨어진다고 생각하는 거야", 5, "down"),
        ("수익률이 낮은 종목이 반등할 것 같아", 5, "down"),
        ("모멘텀 전략", 21, "up"),
        ("수익률 높은게 계속 높을 것 같아", 21, "up"),
        ("수익률이 높은 게 계속 높을 것 같아", 21, "up"),
        ("높은 수익률 종목이 계속 오를 것 같아", 21, "up"),
        ("많이 오른 종목은 더 오를 것 같아", 21, "up"),
        ("수익률 낮은게 계속 낮을 것 같아", 21, "up"),
        ("최근 10일 수익률 높은게 계속 높을 것 같아", 10, "up"),
        ("반전 전략", 5, "down"),
        ("7일 반전 전략", 7, "down"),
        ("2주 모멘텀", 10, "up"),
        ("3개월 모멘텀", 63, "up"),
        ("one month momentum", 21, "up"),
        ("5-day reversal", 5, "down"),
        ("최근 20일 누적 수익률이 높은 종목", 20, "up"),
    ],
)
async def test_short_hypothesis_uses_price_returns_and_has_guidance(strategy, window, direction):
    # Supply the model interpretation independently from the production source parser.
    class Provider:
        name = "test"

        async def interpret(self, *_):
            return ProviderResult(ir=period_ir(window, direction))

    result = await HarnessService(Provider()).convert(ConvertRequest(strategy=strategy))
    assert result.status == "PASS", result.warnings
    sign = "-" if direction == "down" else ""
    assert result.fastExpression == f"rank({sign}(close / ts_delay(close, {window}) - 1))"
    assert f"{window}거래일" in result.strategyExplanation
    assert "rank" in result.strategyExplanation
    assert result.improvementSuggestions
    assert result.refinementOptions
    # The offline demo should also handle these inputs.
    mock = await HarnessService(MockSemanticProvider()).convert(ConvertRequest(strategy=strategy))
    assert mock.fastExpression == result.fastExpression


@pytest.mark.parametrize("change", ["direction", "window", "operation", "entry", "selection"])
async def test_wrong_interpretation_cannot_override_hypothesis(change):
    ir = period_ir()
    if change == "entry":
        ir.entry.enabled = True
    else:
        setattr(
            ir.signal,
            change,
            {
                "direction": "down",
                "window": 5,
                "operation": "delta",
                "selection": "raw",
            }[change],
        )

    class WrongProvider:
        name = "test"

        async def interpret(self, *_):
            return ProviderResult(ir=ir)

    result = await HarnessService(WrongProvider()).convert(
        ConvertRequest(strategy="1달 모멘텀 전략")
    )
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert result.strategyExplanation is None
    assert result.improvementSuggestions == []


async def test_defaults_are_disclosed_and_filter_window_does_not_become_lookback():
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy="반전 전략. 거래량이 최근 20일 평균의 1.5배 이상일 때만 거래한다.")
    )
    assert result.status == "PASS", result.warnings
    assert result.strategyIR.signal.window == 5
    assert result.strategyIR.entry.window == 20
    assert any("기본값 5거래일" in item for item in result.assumptions)
    assert "직전 값을 유지" in result.strategyExplanation


async def test_unnamed_momentum_is_not_confused_with_raw_daily_return_preference():
    service = HarnessService(MockSemanticProvider())
    hypothesis = await service.convert(ConvertRequest(strategy="수익률 높은게 계속 높을 것 같아"))
    assert hypothesis.status == "PASS"
    assert hypothesis.fastExpression == "rank((close / ts_delay(close, 21) - 1))"
    assert any("기본값 21거래일" in item for item in hypothesis.assumptions)
    assert "모멘텀" in hypothesis.strategyExplanation
    assert hypothesis.refinementOptions
    explicit_rule = await service.convert(ConvertRequest(strategy="수익률이 높은 종목에 높은 순위"))
    assert explicit_rule.fastExpression == "rank(returns)"


async def test_explicit_absolute_price_change_is_not_replaced_with_return():
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy="최근 7일 절대 가격 변화량 기준 모멘텀 전략")
    )
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == "rank(ts_delta(close, 7))"
    assert "절대 변화량" in result.strategyExplanation
    assert not any("기간 수익률" in item for item in result.assumptions)


@pytest.mark.parametrize(
    "strategy",
    [
        "1달 모멘텀 전략. 거래량이 최근 20일 평균의 1.5배 이상일 때만 거래한다.",
        "최근 5일 동안 종가가 많이 하락한 종목일수록 높은 순위를 부여한다.",
        "수익률이 낮은 종목을 매수한다.",
    ],
)
async def test_refinements_round_trip_and_preserve_filter_and_settings(strategy):
    service = HarnessService(MockSemanticProvider())
    original = await service.convert(
        ConvertRequest(
            strategy=strategy,
            settings={
                "universe": "TOP500",
                "decay": 8,
                "neutralization": "SECTOR",
                "testPeriod": {"years": 2, "months": 3},
                "nanHandling": "ON",
            },
        )
    )
    assert original.status == "PASS"
    assert original.refinementOptions
    for option in original.refinementOptions:
        refined = await service.convert(
            ConvertRequest(
                strategy=option.strategy,
                settings=original.simulationSettings,
            )
        )
        assert refined.status == "PASS", (option.strategy, refined.warnings)
        assert refined.strategyIR.entry == original.strategyIR.entry
        assert refined.simulationSettings == original.simulationSettings
        assert refined.fastExpression != original.fastExpression


@pytest.mark.parametrize(
    "strategy",
    [
        "1달 모멘텀에 PER 낮은 조건 추가",
        "일주일 반전 후 3% 손절",
        "1달 모멘텀 상위 10개만",
        "1달 모멘텀과 반전 전략",
        "돈 많이 버는 전략",
        "1달 모멘텀, 5일 보유 후 매도",
    ],
)
async def test_unsupported_or_unmeasurable_input_still_rejects(strategy):
    result = await HarnessService(MockSemanticProvider()).convert(ConvertRequest(strategy=strategy))
    assert result.status == "REJECTED"
    assert result.fastExpression is None


def test_return_schema_and_compiler_detect_wrong_formula():
    ir = period_ir()
    assert validate_compiled_fe("1달 모멘텀", ir, compile_fe(ir)) == []
    assert validate_compiled_fe("1달 모멘텀", ir, "rank(ts_delta(close, 21))")
    ir.signal.field = "returns"
    with pytest.raises(ValidationError, match="종가"):
        StrategyIR.model_validate(ir.model_dump())


async def test_openai_wire_contract_stays_one_call_and_accepts_new_operation():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["reasoning_effort"] == "none"
        assert body["max_completion_tokens"] == 1024
        return httpx.Response(200, json=reply(content=period_ir().model_dump_json()))

    provider = OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await HarnessService(provider).convert(
        ConvertRequest(strategy="수익률 높은게 계속 높을 것 같아")
    )
    assert len(calls) == 1
    assert result.status == "PASS"
    assert result.strategyExplanation and result.improvementSuggestions
    OPENAI_POLICY.payload(BASE_SYSTEM_PROMPT, "가" * 2000)


async def test_old_cached_results_without_guidance_remain_readable():
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy="1달 모멘텀")
    )
    old = result.model_dump(
        exclude={
            "strategyExplanation",
            "assumptions",
            "improvementSuggestions",
            "refinementOptions",
        }
    )
    restored = ConversionResponse.model_validate(old)
    assert restored.status == "PASS"
    assert restored.refinementOptions == []
