"""Explain validated drafts and offer concrete, editable follow-up experiments."""

from .hypotheses import hypothesis_context
from .models import ImprovementSuggestion, RefinementOption, StrategyIR

FIELD_NAMES = {
    "open": "시가",
    "high": "고가",
    "low": "저가",
    "close": "종가",
    "volume": "거래량",
    "returns": "일간 수익률",
}
COMPARISONS = {">": "초과", ">=": "이상", "<": "미만", "<=": "이하"}


def explain_strategy(ir: StrategyIR, settings: dict) -> str:
    signal = ir.signal
    field = FIELD_NAMES[signal.field]
    if signal.operation == "return":
        basis = (
            f"현재 종가를 {signal.window}거래일 전 종가로 나눈 뒤 1을 빼서 "
            "해당 기간의 가격 수익률을 계산합니다."
        )
        kind = "반전" if signal.direction == "down" else "모멘텀"
        basis = f"{signal.window}거래일 {kind} 전략 초안입니다. {basis}"
    elif signal.operation == "delta":
        basis = f"현재 {field}에서 {signal.window}거래일 전 값을 뺀 절대 변화량을 사용합니다."
    else:
        basis = f"{field} 값을 신호로 사용합니다."
    if signal.direction == "down":
        basis += " 신호의 부호를 뒤집어 원래 값이 낮을수록 높은 점수를 줍니다."
        if signal.operation == "return":
            basis += " 최근 수익률이 높은 종목에는 낮은 점수를 주는 반전 가설입니다."
    else:
        basis += " 신호 값이 높을수록 높은 점수를 줍니다."
    if signal.selection == "relative":
        basis += " rank는 같은 시점의 종목들을 비교해 상대 순위로 바꿉니다."
    if ir.entry.enabled:
        entry = ir.entry
        basis += (
            f" {FIELD_NAMES[entry.field]}이 최근 {entry.window}거래일 평균의 "
            f"{entry.multiplier:g}배 {COMPARISONS[entry.comparator]}일 때 점수를 갱신하고, "
            "조건을 충족하지 않으면 직전 값을 유지합니다."
        )
    basis += (
        f" 실제 포지션은 BRAIN의 중립화({settings['neutralization']}), "
        f"Delay {settings['delay']}, Decay {settings['decay']} 등 설정에도 영향을 받습니다. "
        "관찰 기간 뒤 자동 청산하는 규칙은 포함하지 않습니다."
    )
    return basis


def strategy_sentence(ir: StrategyIR) -> str:
    """A fresh editable description of the selected IR, preserving the entry condition."""
    signal = ir.signal
    field = FIELD_NAMES[signal.field]
    if signal.operation == "return":
        family = "반전" if signal.direction == "down" else "모멘텀"
        sentence = f"최근 {signal.window}일 수익률 기준 {family} 전략."
    else:
        basis = (
            f"최근 {signal.window}일 동안 {field} 변화" if signal.operation == "delta" else field
        )
        direction = "낮은" if signal.direction == "down" else "높은"
        sentence = f"{basis} 값이 {direction} 종목에 높은 점수를 부여한다."
        if signal.selection == "relative":
            sentence += " 종목 간 상대 순위를 사용한다."
        else:
            sentence += " 순위 변환 없이 신호를 사용한다."
    if ir.entry.enabled:
        entry = ir.entry
        sentence += (
            f" {FIELD_NAMES[entry.field]}이 최근 {entry.window}일 평균의 "
            f"{entry.multiplier:g}배 {COMPARISONS[entry.comparator]}일 때만 점수를 갱신한다."
        )
    return sentence


def refinement_options(ir: StrategyIR) -> list[RefinementOption]:
    options = []
    if ir.signal.selection != "relative" or ir.signal.field not in {"close", "returns"}:
        return options
    if ir.entry.enabled and ir.entry.field != "volume":
        return options
    if ir.signal.operation in {"delta", "return"}:
        for days, label in ((5, "1주 관찰"), (21, "1달 관찰"), (63, "3달 관찰")):
            if days == ir.signal.window:
                continue
            changed = ir.model_copy(deep=True)
            changed.signal.window = days
            options.append(
                RefinementOption(
                    label=label,
                    description=f"관찰 기간을 {days}거래일로 바꿉니다. "
                    "진입 조건과 설정은 유지합니다.",
                    strategy=strategy_sentence(changed),
                )
            )
    changed = ir.model_copy(deep=True)
    changed.signal.direction = "up" if ir.signal.direction == "down" else "down"
    direction_label = "높은 값 선호" if changed.signal.direction == "up" else "낮은 값 선호"
    if ir.signal.operation == "return":
        direction_label = "모멘텀 방향" if changed.signal.direction == "up" else "반전 방향"
    options.append(
        RefinementOption(
            label=f"{direction_label}으로 변경",
            description="신호를 선호하는 방향을 바꿉니다. 기간과 진입 조건은 유지합니다.",
            strategy=strategy_sentence(changed),
        )
    )
    return options


def strategy_guidance(strategy: str, ir: StrategyIR, settings: dict) -> dict:
    context = hypothesis_context(strategy)
    assumptions = list(context.assumptions)
    if context.family and ir.signal.operation == "return":
        assumptions.append("종가의 기간 수익률로 종목 간 상대 순위를 매기는 초안입니다.")
    if ir.signal.operation in {"delta", "return"} and not context.windows and not context.family:
        assumptions.append(f"관찰 기간이 없어 {ir.signal.window}거래일을 사용한 초안입니다.")
    suggestions = []
    if ir.signal.operation in {"delta", "return"}:
        days = ir.signal.window
        alternatives = sorted({max(1, days // 2), days, min(1000, days * 2)})
        suggestions.append(
            ImprovementSuggestion(
                title="관찰 기간 비교",
                rationale="특정 기간에서만 좋은 결과가 나오는지 확인합니다.",
                experiment="다른 조건을 고정하고 "
                f"{', '.join(map(str, alternatives))}거래일을 비교하세요.",
            )
        )
    if ir.signal.direction == "down":
        suggestions.append(
            ImprovementSuggestion(
                title="반전이 나타나는 상황 확인",
                rationale="하락이 이어지는 구간에서는 반전 가설이 불리할 수 있습니다.",
                experiment="상승장·하락장과 변동성이 큰 구간을 나누어 "
                "성과와 최대 낙폭을 비교하세요.",
            )
        )
    suggestions.extend(
        [
            ImprovementSuggestion(
                title="거래 빈도와 비용 점검",
                rationale="신호가 자주 바뀌면 거래비용이 성과를 줄일 수 있습니다.",
                experiment=(
                    f"현재 Decay {settings['decay']}를 기준으로 인접 값을 비교하고, "
                    "회전율과 거래비용 반영 후 성과를 함께 확인하세요."
                ),
            ),
            ImprovementSuggestion(
                title="별도 기간에서 재검증",
                rationale="조건을 조정할 때 본 데이터에만 맞춘 결과일 수 있습니다.",
                experiment="조건 선택에 쓰지 않은 기간에서 "
                "Sharpe·최대 낙폭·회전율을 다시 확인하세요.",
            ),
        ]
    )
    return {
        "strategyExplanation": explain_strategy(ir, settings),
        "assumptions": assumptions,
        "improvementSuggestions": suggestions,
        "refinementOptions": refinement_options(ir),
    }
