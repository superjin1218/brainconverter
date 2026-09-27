import pytest

from backend.app.compiler import compile_fe, source_guards, validate_compiled_fe
from backend.app.models import ConvertRequest
from backend.app.provider import MockSemanticProvider, ProviderResult
from backend.app.service import HarnessService
from backend.tests.test_compiler import example_ir


def test_raw_return_reversal_is_valid():
    ir = example_ir()
    ir.signal.field = "returns"
    ir.signal.operation = "raw"
    ir.signal.window = 1
    ir.entry.enabled = False
    assert validate_compiled_fe("수익률이 낮은 종목", ir, compile_fe(ir)) == []


def test_number_substring_is_not_preservation():
    ir = example_ir()
    ir.signal.window = 15
    assert validate_compiled_fe("최근 5일 하락 종목", ir, compile_fe(ir))


def test_volume_filter_cannot_use_price_field():
    ir = example_ir()
    ir.entry.field = "close"
    assert source_guards("거래량이 20일 평균의 1.5배 이상", ir)


def test_return_window_cannot_be_hidden_in_volume_window():
    ir = example_ir()
    ir.signal.field = "returns"
    ir.signal.operation = "raw"
    ir.signal.window = 1
    ir.entry.window = 5
    assert source_guards("5일 수익률이 낮고 거래량이 5일 평균의 1.5배 이상", ir)


async def test_single_wrong_interpretation_cannot_drop_explicit_direction():
    class WrongProvider(MockSemanticProvider):
        async def interpret(self, system_prompt, strategy):
            result = await super().interpret(system_prompt, strategy)
            result.ir.signal.direction = "up"
            return result

    result = await HarnessService(WrongProvider()).convert(
        ConvertRequest(strategy="최근 5일 종가 하락 순위 전략")
    )
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert not result.validation.sourceRequirementsPreserved


async def test_single_ambiguous_interpretation_cannot_approve():
    class AmbiguousProvider(MockSemanticProvider):
        async def interpret(self, system_prompt, strategy):
            result = await super().interpret(system_prompt, strategy)
            result.ir.status = "ambiguous"
            return result

    result = await HarnessService(AmbiguousProvider()).convert(
        ConvertRequest(strategy="좋은 종목을 선택한다")
    )
    assert result.status == "REJECTED"
    assert result.fastExpression is None


async def test_unsupported_settings_cannot_pass():
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy="중국 시장에서 최근 5일 하락 종목")
    )
    assert result.status == "REJECTED"


@pytest.mark.parametrize(
    "strategy", ["5일 수익률과 20일 거래량을 같은 비중으로 결합", "PER이 낮은 종목"]
)
async def test_unsupported_strategy_fails_closed(strategy):
    class ConfidentButWrongProvider:
        name = "test"

        async def interpret(self, *_):
            return ProviderResult(ir=example_ir())

    result = await HarnessService(ConfidentButWrongProvider()).convert(
        ConvertRequest(strategy=strategy)
    )
    assert result.status == "REJECTED"
