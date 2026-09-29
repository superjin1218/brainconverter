"""Provider contract shared by real inference, offline development, and compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import DraftIR, IntentIR, StrategyIR


@dataclass(frozen=True)
class ProviderResult:
    ir: IntentIR | DraftIR | StrategyIR
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microusd: int = 0


class SemanticProvider(Protocol):
    name: str

    async def interpret(self, system_prompt: str, strategy: str) -> ProviderResult: ...
