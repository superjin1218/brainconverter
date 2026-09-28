"""Deterministic offline fixture for development and regression tests only."""

from __future__ import annotations

import re

from .models import EntryIR, SignalIR, StrategyIR
from .provider_types import ProviderResult


class MockSemanticProvider:
    """Deterministic local provider for UI development and tests; never calls a model."""

    name = "mock"

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult:
        del system_prompt
        lower = strategy.lower()

        signal_field = "returns" if "수익률" in lower or "returns" in lower else "close"
        operation = "raw" if signal_field == "returns" else "delta"
        numbers = [int(item) for item in re.findall(r"(?<!\d)\d+(?!\d)", strategy)]
        signal_window = numbers[0] if numbers and operation == "delta" else 1
        downside = any(
            phrase in lower for phrase in ("떨어", "하락", "낮은", "reversal", "drop", "weak")
        )

        entry_enabled = "거래량" in lower or "volume" in lower
        entry_window = 20
        multiplier = 1.0
        comparator = ">="
        if entry_enabled:
            mean_match = re.search(r"(?:최근\s*)?(\d+)일\s*평균", strategy)
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
            status="ok",
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
