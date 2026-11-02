from __future__ import annotations

import re
from decimal import Decimal

from .hypotheses import hypothesis_context
from .models import EntryIR, SignalIR, StrategyIR


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def signal_base(signal: SignalIR) -> str:
    if signal.operation == "delta":
        return f"ts_delta({signal.field}, {signal.window})"
    if signal.operation == "return":
        return f"(close / ts_delay(close, {signal.window}) - 1)"
    return signal.field


def compile_signal(signal: SignalIR) -> str:
    expression = signal_base(signal)

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
    return f"{entry.field} {entry.comparator} {multiplier} * ts_mean({entry.field}, {entry.window})"


def compile_fe(ir: StrategyIR) -> str:
    """Compile FE without duplicating BRAIN's simulation neutralization setting."""
    expression = compile_signal(ir.signal)
    entry_condition = compile_entry(ir.entry)
    if entry_condition:
        expression = f"trade_when({entry_condition}, {expression}, -1)"
    return expression


def source_guards(strategy: str, ir: StrategyIR) -> list[str]:
    context = hypothesis_context(strategy)
    lower = context.normalized.lower()
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

    if ("거래량" in lower or "volume" in lower) and not (
        ir.entry.enabled or ir.signal.field == "volume"
    ):
        errors.append("명시한 거래량 필터가 보존되지 않았습니다.")

    downside_phrases = (
        "많이 떨어",
        "가장 많이 떨어",
        "크게 떨어",
        "fell the most",
        "biggest drop",
        "largest drop",
    )
    if not context.family and any(phrase in lower for phrase in downside_phrases):
        if ir.signal.direction != "down" or ir.signal.selection != "relative":
            errors.append("상대적 하락 신호의 방향 또는 선택 방식이 보존되지 않았습니다.")

    if re.search(r"순위|\brank(?:ing)?\b", lower) and ir.signal.selection != "relative":
        errors.append("명시한 상대 순위가 보존되지 않았습니다.")

    comparator_map = {"이상": ">=", "초과": ">", "이하": "<=", "미만": "<"}
    for token, expected in comparator_map.items():
        if token in lower and ir.entry.enabled and ir.entry.comparator != expected:
            errors.append(f"'{token}'은 '{expected}'로 보존되어야 합니다.")

    if re.search(
        r"동일\s*비중|같은\s*비중|가중\s*합|"
        r"손절|익절|청산|이동평균.*교차|미래|내일|equal.weight|stop.loss|take.profit",
        lower,
    ):
        errors.append("현재 지원 범위 밖의 데이터·신호 조합·청산 조건이 있습니다.")
    if re.search(r"보유\s*기간|\d+\s*일(?:간)?\s*보유|hold\s+for", lower):
        errors.append("보유 기간과 자동 청산 규칙은 현재 지원하지 않습니다.")
    if re.search(r"\d+(?:\.\d+)?\s*%|상위\s*\d+|하위\s*\d+", lower):
        errors.append("퍼센트 임계값·상하위 개수 조건은 현재 지원하지 않습니다.")

    # Bind explicit windows to their semantic slot, not a coincidental number in another slot.
    signal_window = re.search(
        r"(?:최근\s*)?(\d+)\s*일\s*(?:동안|간)?\s*(?:가격|종가|하락|상승)", lower
    )
    if signal_window and (
        ir.signal.operation not in ({"return"} if context.uses_period_return else {"delta"})
        or ir.signal.window != int(signal_window.group(1))
    ):
        errors.append("명시한 가격 변화 기간이 보존되지 않았습니다.")
    entry_window = re.search(r"(?:최근\s*)?(\d+)\s*일\s*평균", lower)
    if entry_window and (not ir.entry.enabled or ir.entry.window != int(entry_window.group(1))):
        errors.append("명시한 평균 거래량 기간이 보존되지 않았습니다.")
    if entry_window and ("거래량" in lower or "volume" in lower) and ir.entry.field != "volume":
        errors.append("거래량 조건의 데이터가 보존되지 않았습니다.")
    multiplier = re.search(r"(\d+(?:\.\d+)?)\s*배", lower)
    if multiplier and (
        not ir.entry.enabled or Decimal(str(ir.entry.multiplier)) != Decimal(multiplier.group(1))
    ):
        errors.append("명시한 거래량 배수가 보존되지 않았습니다.")

    signal_text = re.split(r"거래량|volume", lower)[0] if ir.signal.field != "volume" else lower
    if context.conflicting:
        errors.append("모멘텀과 반전 방향이 함께 제시됐습니다. 원하는 방향을 선택해 주세요.")
    if context.family:
        if ir.signal.direction != context.direction or ir.signal.selection != "relative":
            errors.append("가설의 모멘텀·반전 방향 또는 상대 순위가 보존되지 않았습니다.")
        if ir.entry.enabled and not re.search(r"평균|mean|거래량|volume", lower):
            errors.append("입력에 없는 진입 조건이 추가됐습니다.")
    if context.uses_period_return or context.family:
        if ir.signal.window != context.window or any(
            window != ir.signal.window for window in context.windows
        ):
            errors.append("가설의 관찰 기간이 보존되지 않았습니다.")
    if context.uses_period_return:
        if ir.signal.operation != "return" or ir.signal.field != "close":
            errors.append("기간 수익률은 종가 비율로 계산해야 합니다.")
    elif context.family and ir.signal.operation != "delta":
        errors.append("명시한 절대 가격 변화량이 보존되지 않았습니다.")
    if not context.family and re.search(r"하락|떨어|낮은\s*수익률|수익률이\s*낮", signal_text):
        if ir.signal.direction != "down":
            errors.append("명시한 하락 방향이 보존되지 않았습니다.")
    if not context.family and re.search(r"상승|오른|오르|높은\s*수익률|수익률이\s*높", signal_text):
        if ir.signal.direction != "up":
            errors.append("명시한 상승 방향이 보존되지 않았습니다.")
    if "수익률" in signal_text and not context.uses_period_return and ir.signal.field != "returns":
        errors.append("수익률 신호가 다른 데이터로 바뀌었습니다.")
    if re.search(r"(?:가격|종가)", signal_text) and ir.signal.field != "close":
        errors.append("가격 신호가 다른 데이터로 바뀌었습니다.")

    return errors


def validate_compiled_fe(strategy: str, ir: StrategyIR, expression: str) -> list[str]:
    errors: list[str] = []
    if ir.signal.operation in {"delta", "return"}:
        expected = signal_base(ir.signal)
        if expected not in expression:
            errors.append("시계열 변화 신호가 컴파일 결과에서 사라졌습니다.")
    base_signal = signal_base(ir.signal)
    if ir.signal.direction == "down" and f"-{base_signal}" not in expression:
        errors.append("하락 방향이 컴파일 결과에서 사라졌습니다.")
    if ir.signal.selection == "relative" and "rank(" not in expression:
        errors.append("상대 순위가 컴파일 결과에서 사라졌습니다.")
    if ir.entry.enabled and "trade_when(" not in expression:
        errors.append("진입 조건이 컴파일 결과에서 사라졌습니다.")

    return errors + validate_source_numbers(strategy, expression)


def validate_source_numbers(strategy: str, expression: str) -> list[str]:
    errors: list[str] = []

    # 설정 숫자(예: TOP3000, Delay 1)는 FE에 들어가지 않으므로 제외한다.
    strategy_without_settings = re.sub(
        r"(?i)(top\s*\d+|delay\s*[:=]?\s*[01]|딜레이\s*[:=]?\s*[01]|\bD[01]\b|"
        r"(?:decay|디케이)\s*[:=]?\s*\d+|(?:truncation|트런케이션)\s*[:=]?\s*\d+(?:\.\d+)?|"
        r"(?:test\s*period|테스트\s*기간)\s*[:=]?\s*\d+\s*(?:년|y(?:ears?)?)"
        r"(?:\s*\d+\s*(?:개월|m(?:onths?)?))?)",
        "",
        hypothesis_context(strategy).normalized,
    )
    numbers = {Decimal(n) for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", expression)}
    if re.search(r"\breturns\b", expression):
        numbers.add(Decimal(1))  # The returns field already represents a one-day return.
    for number in re.findall(
        r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?![A-Za-z0-9_.])", strategy_without_settings
    ):
        if Decimal(number) not in numbers:
            errors.append(f"전략의 숫자 {number}이 컴파일 결과에서 사라졌습니다.")
    return errors


def intent_mapping(ir: StrategyIR) -> list[dict[str, str]]:
    mapping = [{"requirement": "신호 · 방향 · 상대 순위", "expression": compile_signal(ir.signal)}]
    condition = compile_entry(ir.entry)
    if condition:
        mapping.append({"requirement": "거래량 진입 조건", "expression": condition})
    return mapping
