"""Independent model replies test validation, not the model's interpretation accuracy."""

import json
from pathlib import Path

import pytest

from backend.app.models import ConvertRequest
from backend.app.provider_types import ProviderResult
from backend.app.service import HarnessService
from backend.tests.provider_fixtures import example_ir

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "evals/semantic_composition_cases.json").read_text()
)


def interpreted_ir(index=0):
    ir = example_ir()
    ir.neutralization = "none"
    ir.signal.operation = "return"
    ir.signal.direction = "up"
    if index == 1:
        ir.signal.window = 9
        ir.signal.direction = "down"
        ir.entry.window = 17
        ir.entry.multiplier = 0.8
        ir.entry.comparator = "<"
    elif index == 2:
        ir.signal.field = "volume"
        ir.signal.operation = "raw"
        ir.signal.window = 1
        ir.entry.enabled = False
    return ir


async def convert_once(strategy, ir):
    calls = []

    class LegacyProvider:
        name = "legacy-test"

        async def interpret(self, prompt, received_strategy):
            calls.append(received_strategy)
            assert received_strategy == strategy
            return ProviderResult(ir=ir)

    provider = LegacyProvider()
    result = await HarnessService(provider).convert(ConvertRequest(strategy=strategy))
    assert len(calls) == 1
    return result


@pytest.mark.parametrize("index", range(len(CASES)), ids=[case["id"] for case in CASES])
async def test_interpreted_components_compile_without_a_named_strategy(index):
    case = CASES[index]
    ir = interpreted_ir(index)
    result = await convert_once(case["strategy"], ir)
    assert result.status == case["status"], result.warnings
    assert result.fastExpression == case["expression"]
    assert result.strategyIR == ir
    if ir.entry.enabled:
        assert "직전 값을 유지" in result.strategyExplanation


@pytest.mark.parametrize(
    "slot,field,value",
    [
        ("signal", "window", 20),
        ("signal", "direction", "down"),
        ("signal", "operation", "delta"),
        ("entry", "enabled", False),
        ("entry", "window", 5),
        ("entry", "field", "close"),
        ("entry", "comparator", ">"),
        ("entry", "multiplier", 2.0),
    ],
)
async def test_composition_does_not_allow_silently_changed_requirements(slot, field, value):
    ir = interpreted_ir()
    setattr(getattr(ir, slot), field, value)
    result = await convert_once(CASES[0]["strategy"], ir)
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert not result.validation.sourceRequirementsPreserved


async def test_complete_ir_does_not_override_models_unsupported_status():
    # The real pre-fix reply filled every field correctly but returned unsupported.
    # Fix interpretation instructions; never force that status to ok or retry for approval.
    ir = interpreted_ir()
    ir.status = "unsupported"
    result = await convert_once(CASES[0]["strategy"], ir)
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert any("unsupported" in warning for warning in result.warnings)
