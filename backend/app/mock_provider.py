"""Deterministic offline fixture for development and regression tests only."""

from __future__ import annotations

import re

from .hypotheses import hypothesis_context
from .models import EntryIR, SignalIR, StrategyIR
from .provider_types import ProviderResult


class MockSemanticProvider:
    """Deterministic local provider for UI development and tests; never calls a model."""

    name = "mock"

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult:
        del system_prompt
        context = hypothesis_context(strategy)
        lower = context.normalized.lower()

        signal_field = "returns" if "수익률" in lower or "returns" in lower else "close"
        operation = "raw" if signal_field == "returns" else "delta"
        numbers = [int(item) for item in re.findall(r"(?<!\d)\d+(?!\d)", lower)]
        signal_window = numbers[0] if numbers and operation == "delta" else 1
        downside = any(
            phrase in lower for phrase in ("떨어", "하락", "낮은", "reversal", "drop", "weak")
        )
        if context.uses_period_return:
            signal_field, operation = "close", "return"
            signal_window = context.window
        if context.direction:
            downside = context.direction == "down"
            signal_window = context.window

        entry_enabled = "거래량" in lower or "volume" in lower
        entry_window = 20
        multiplier = 1.0
        comparator = ">="
        if entry_enabled:
            mean_match = re.search(r"(?:최근\s*)?(\d+)일\s*평균", lower)
            multiplier_match = re.search(r"(\d+(?:\.\d+)?)\s*배", strategy)
            if mean_match:
                entry_window = int(mean_match.group(1))
            if multiplier_match:
                multiplier = float(multiplier_match.group(1))
            if "초과" in lower:
                comparator = ">"
            elif "이하" in lower:
                comparator = "<="
            elif "미만" in lower:
                comparator = "<"

        neutralization = "none"
        if "하위산업" in lower or "subindustry" in lower:
            neutralization = "subindustry"
        elif "섹터" in lower or "sector" in lower:
            neutralization = "sector"
        elif "산업" in lower or "industry" in lower:
            neutralization = "industry"

        ir = StrategyIR(
            status="ambiguous"
            if context.conflicting
            or not re.search(
                r"모멘|momentum|반전|reversal|회귀|추세|가격|종가|close|수익률|returns|"
                r"하락|상승|떨어|오른|volume|거래량",
                lower,
            )
            else "ok",
            signal=SignalIR(
                field=signal_field,
                operation=operation,
                window=signal_window,
                direction="down" if downside else "up",
                selection="relative",
            ),
            entry=EntryIR(
                enabled=entry_enabled,
                field="volume",
                reference="ts_mean" if entry_enabled else "none",
                window=entry_window if entry_enabled else 1,
                comparator=comparator if entry_enabled else "none",
                multiplier=multiplier,
            ),
            neutralization=neutralization,
            exit="none",
        )
        return ProviderResult(ir=ir)
