"""Shared, explicit conventions for turning short hypotheses into strategy drafts."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HypothesisContext:
    normalized: str
    signal_text: str
    family: str | None
    windows: tuple[int, ...]
    assumptions: tuple[str, ...]
    conflicting: bool = False

    @property
    def window(self) -> int | None:
        if self.windows:
            return self.windows[0]
        return {"momentum": 21, "reversal": 5}.get(self.family)

    @property
    def direction(self) -> str | None:
        return {"momentum": "up", "reversal": "down"}.get(self.family)

    @property
    def uses_period_return(self) -> bool:
        if re.search(r"절대\s*(?:가격|변화)|(?:가격|종가)\s*(?:차이|변화량)", self.signal_text):
            return False
        return bool(self.family) or bool(
            re.search(r"수익률|\breturns?\b", self.signal_text)
            and self.window is not None
            and self.window > 1
        )


def hypothesis_context(strategy: str) -> HypothesisContext:
    # Do not interpret filter windows or Test Period settings as signal lookbacks.
    parts = re.split(
        r"거래량|\bvolume\b|테스트\s*기간|test\s*period|\bdecay\b|디케이",
        strategy.lower(),
        maxsplit=1,
    )
    signal_text = parts[0]
    assumptions: list[str] = []

    def period(match: re.Match) -> str:
        count_text, unit = match.group(1), match.group(2)
        count = (
            int(count_text)
            if count_text.isdigit()
            else {
                "한": 1,
                "일": 1,
                "one": 1,
                "두": 2,
                "세": 3,
            }[count_text]
        )
        days = count * (21 if unit in {"달", "개월", "month", "months"} else 5)
        assumptions.append(f"'{match.group(0)}'을 약 {days}거래일의 관찰 기간으로 해석했습니다.")
        return f"{days}일"

    # Do not turn TOP3000 주식 or 매일 주가 into an invented week count.
    normalized_signal = re.sub(
        r"(?<![\d.])(\d+|한|두|세|일|one)\s*[-]?\s*"
        r"(개월|달|주일|주(?![식가세요문목])|months?\b|weeks?\b)",
        period,
        signal_text,
    )
    normalized_signal = re.sub(r"(\d+)\s*[-]?\s*(?:trading\s+)?days?\b", r"\1일", normalized_signal)
    normalized_signal = re.sub(r"(\d+)\s*거래일", r"\1일", normalized_signal)
    normalized = normalized_signal + strategy[len(signal_text) :]
    windows = tuple(int(m.group(1)) for m in re.finditer(r"(\d+)\s*일", normalized_signal))

    reversal = bool(
        re.search(r"반전|역추세|리버설|평균\s*회귀|reversal|mean[ -]?reversion", signal_text)
    )
    momentum = bool(
        re.search(r"모멘텀|모멘툼|추세\s*추종|momentum|trend[ -]?following", signal_text)
    )
    # Distinguish past winners expected to fall from a preference for past winners.
    winners = r"(?:수익률\s*(?:이|은|가)?\s*높|높은\s*수익률|많이\s*오른)"
    losers = r"(?:수익률\s*이?\s*낮|낮은\s*수익률|많이\s*떨어진)"
    continuation = r"(?:계속|지속|이어|더)"
    higher = r"(?:높(?:을|다|아|겠|게|고)|오르|오를|상승)"
    lower = r"(?:낮(?:을|다|아|겠|게|고)|떨어|하락|내려)"
    # A persistence hypothesis is momentum even when the user never names it.
    momentum |= bool(re.search(winners + r".*" + continuation + r".*" + higher, signal_text))
    momentum |= bool(re.search(losers + r".*" + continuation + r".*" + lower, signal_text))
    reversal |= bool(re.search(winners + r".*(?:떨어|하락|내려|되돌)", signal_text))
    reversal |= bool(re.search(losers + r".*(?:오를|오르|상승|반등)", signal_text))
    family = "reversal" if reversal else "momentum" if momentum else None
    if family and not windows:
        days = 5 if family == "reversal" else 21
        assumptions.append(f"관찰 기간이 없어 초안의 기본값 {days}거래일을 적용했습니다.")
    if family:
        assumptions.append("관찰 기간은 과거 신호 계산 기간이며 보유·청산 기간을 뜻하지 않습니다.")
    return HypothesisContext(
        normalized,
        normalized_signal,
        family,
        windows,
        tuple(assumptions),
        conflicting=reversal and momentum,
    )
