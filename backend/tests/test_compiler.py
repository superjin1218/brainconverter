from backend.app.compiler import compile_fe, source_guards, validate_compiled_fe
from backend.app.models import EntryIR, SignalIR, StrategyIR


def example_ir() -> StrategyIR:
    return StrategyIR(
        status="ok",
        signal=SignalIR(
            field="close", operation="delta", window=5, direction="down", selection="relative"
        ),
        entry=EntryIR(
            enabled=True,
            field="volume",
            reference="ts_mean",
            window=20,
            comparator=">=",
            multiplier=1.5,
        ),
        neutralization="industry",
        exit="none",
    )


def test_compile_preserves_strategy_without_double_neutralization():
    ir = example_ir()
    expression = compile_fe(ir)
    assert expression == (
        "trade_when(volume >= 1.5 * ts_mean(volume, 20), "
        "rank(-ts_delta(close, 5)), -1)"
    )
    assert "group_neutralize" not in expression
    assert validate_compiled_fe("최근 5일, 20일 평균 1.5배", ir, expression) == []


def test_source_guard_accepts_industry_requirement():
    assert source_guards("산업별로 중립화하고 거래량이 20일 평균의 1.5배 이상", example_ir()) == []

