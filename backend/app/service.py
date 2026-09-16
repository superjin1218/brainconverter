from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import Counter
from typing import Any

from .compiler import compile_fe, source_guards, validate_compiled_fe
from .models import (
    ConversionResponse,
    ConvertRequest,
    StrategyIR,
    ValidationSummary,
)
from .prompts import AGENTS, BASE_SYSTEM_PROMPT
from .provider import SemanticProvider
from .settings import resolve_simulation_settings

IMPORTANT_PATHS = [
    "signal.field",
    "signal.operation",
    "signal.window",
    "signal.direction",
    "signal.selection",
    "entry.enabled",
    "entry.field",
    "entry.reference",
    "entry.window",
    "entry.comparator",
    "entry.multiplier",
    "neutralization",
]


def _flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten(value, path))
        else:
            flattened[path] = value
    return flattened


def _set_nested(obj: dict[str, Any], path: str, value: Any) -> None:
    current = obj
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def consensus_ir(results: list[StrategyIR]) -> tuple[StrategyIR, dict[str, float]]:
    if not results:
        raise RuntimeError("모든 semantic agent가 실패했습니다.")
    flattened = [_flatten(item.model_dump()) for item in results]
    consensus: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    paths = set().union(*(item.keys() for item in flattened))
    for path in sorted(paths):
        values = [item[path] for item in flattened if path in item]
        serialized = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in values]
        winner_serialized, votes = Counter(serialized).most_common(1)[0]
        _set_nested(consensus, path, json.loads(winner_serialized))
        confidence[path] = votes / len(values)
    return StrategyIR.model_validate(consensus), confidence


def _overall_confidence(confidence: dict[str, float]) -> float:
    values = [confidence[path] for path in IMPORTANT_PATHS if path in confidence]
    return sum(values) / len(values) if values else 0.0


class HarnessService:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.job_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_JOBS", "2")))

    async def _run_agent(self, name: str, instruction: str, strategy: str) -> StrategyIR:
        prompt = f"{BASE_SYSTEM_PROMPT}\n\nSPECIAL ROLE ({name}):\n{instruction}"
        result = await self.provider.interpret(prompt, strategy)
        return result.ir

    async def convert(self, request: ConvertRequest) -> ConversionResponse:
        request_id = str(uuid.uuid4())
        async with self.job_semaphore:
            outcomes = await asyncio.gather(
                *(
                    self._run_agent(name, instruction, request.strategy)
                    for name, instruction in AGENTS
                ),
                return_exceptions=True,
            )

        successful = [outcome for outcome in outcomes if isinstance(outcome, StrategyIR)]
        if not successful:
            raise RuntimeError("모든 semantic agent가 실패했습니다.")

        ir, field_confidence = consensus_ir(successful)
        confidence = _overall_confidence(field_confidence)
        errors = source_guards(request.strategy, ir)
        if ir.status != "ok":
            errors.append(f"Strategy IR 상태가 {ir.status}입니다.")
        for path in IMPORTANT_PATHS:
            if field_confidence.get(path, 0) < 0.5:
                errors.append(f"합의 신뢰도가 낮습니다: {path}")

        expression: str | None = None
        if not errors:
            expression = compile_fe(ir)
            errors.extend(validate_compiled_fe(request.strategy, ir, expression))

        settings, settings_source, warnings, unresolved = resolve_simulation_settings(
            request.strategy, request.settings
        )
        if ir.neutralization != "none" and settings_source["neutralization"] == "default":
            settings["neutralization"] = ir.neutralization.upper()
            settings_source["neutralization"] = "user"

        failed_agents = len(outcomes) - len(successful)
        if failed_agents:
            warnings.append(
                f"semantic agent {failed_agents}개가 실패했지만 유효한 합의로 계속했습니다."
            )

        status = "REJECTED" if errors else "PASS"
        warnings.extend(errors)
        validation = ValidationSummary(
            jsonValid=True,
            schemaValid=True,
            consensusPassed=confidence >= 0.5,
            sourceRequirementsPreserved=not bool(source_guards(request.strategy, ir)),
            compilePassed=not bool(errors),
        )
        return ConversionResponse(
            requestId=request_id,
            status=status,
            fastExpression=expression if status == "PASS" else None,
            simulationSettings=settings,
            settingsSource=settings_source,
            strategyIR=ir,
            confidence=round(confidence, 3),
            validation=validation,
            warnings=warnings,
            unresolvedSettings=unresolved,
            provider=self.provider.name,
        )
