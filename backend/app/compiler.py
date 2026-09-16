from __future__ import annotations

import re

from .models import EntryIR, SignalIR, StrategyIR


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def compile_signal(signal: SignalIR) -> str:
    if signal.operation == "delta":
        expression = f"ts_delta({signal.field}, {signal.window})"
    else:
        expression = signal.field

    if signal.direction == "down":
        expression = f"-{expression}"

    if signal.selection == "relative":
        expression = f"rank({expression})"

    return expression


def compile_entry(entry: EntryIR) -> str | None:
    if not entry.enabled:
        return None
    if entry.reference != "ts_mean" or entry.comparator == "none":
        raise ValueError("지원하지 않는 진입 조건입니다.")
    multiplier = _format_number(entry.multiplier)
    return (
        f"{entry.field} {entry.comparator} "
        f"{multiplier} * ts_mean({entry.field}, {entry.window})"
    )


def compile_fe(ir: StrategyIR) -> str:
    """Compile FE without duplicating BRAIN's simulation neutralization setting."""
    expression = compile_signal(ir.signal)
    entry_condition = compile_entry(ir.entry)
    if entry_condition:
        expression = f"trade_when({entry_condition}, {expression}, -1)"
    return expression


def source_guards(strategy: str, ir: StrategyIR) -> list[str]:
    lower = strategy.lower()
    errors: list[str] = []

    neutralization_terms = {
        "subindustry": ("하위산업", "subindustry"),
        "sector": ("섹터", "sector"),
        "industry": ("산업", "industry"),
    }
    for expected, terms in neutralization_terms.items():
        if any(term in lower for term in terms):
            if ir.neutralization != expected:
                errors.append(f"명시한 {expected} 중립화가 보존되지 않았습니다.")
            break

    if ("거래량" in lower or "volume" in lower) and not ir.entry.enabled:
        errors.append("명시한 거래량 필터가 보존되지 않았습니다.")

    downside_phrases = (
        "많이 떨어",
        "가장 많이 떨어",
        "크게 떨어",
        "fell the most",
        "biggest drop",
        "largest drop",
    )
    if any(phrase in lower for phrase in downside_phrases):
        if ir.signal.direction != "down" or ir.signal.selection != "relative":
            errors.append("상대적 하락 신호의 방향 또는 선택 방식이 보존되지 않았습니다.")

    comparator_map = {"이상": ">=", "초과": ">", "이하": "<=", "미만": "<"}
    for token, expected in comparator_map.items():
        if token in lower and ir.entry.enabled and ir.entry.comparator != expected:
            errors.append(f"'{token}'은 '{expected}'로 보존되어야 합니다.")

    return errors


def validate_compiled_fe(strategy: str, ir: StrategyIR, expression: str) -> list[str]:
    errors: list[str] = []
    if ir.signal.operation == "delta":
        expected = f"ts_delta({ir.signal.field}, {ir.signal.window})"
        if expected not in expression:
            errors.append("시계열 변화 신호가 컴파일 결과에서 사라졌습니다.")
    if ir.signal.direction == "down" and "-ts_delta(" not in expression:
        errors.append("하락 방향이 컴파일 결과에서 사라졌습니다.")
    if ir.signal.selection == "relative" and "rank(" not in expression:
        errors.append("상대 순위가 컴파일 결과에서 사라졌습니다.")
    if ir.entry.enabled and "trade_when(" not in expression:
        errors.append("진입 조건이 컴파일 결과에서 사라졌습니다.")

    # 설정 숫자(예: TOP3000, Delay 1)는 FE에 들어가지 않으므로 제외한다.
    strategy_without_settings = re.sub(
        r"(?i)(top\s*\d+|delay\s*[:=]?\s*[01]|딜레이\s*[:=]?\s*[01]|"
        r"decay\s*[:=]?\s*\d+|truncation\s*[:=]?\s*0?\.\d+|"
        r"(?:test\s*period|테스트\s*기간)\s*[:=]?\s*\d+\s*(?:년|y(?:ears?)?)"
        r"(?:\s*\d+\s*(?:개월|m(?:onths?)?))?)",
        "",
        strategy,
    )
    for number in re.findall(r"(?<!\w)\d+(?:\.\d+)?", strategy_without_settings):
        normalized = number[:-2] if number.endswith(".0") else number
        if normalized not in expression:
            errors.append(f"전략의 숫자 {number}이 컴파일 결과에서 사라졌습니다.")
    return errors
