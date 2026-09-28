import json
from pathlib import Path

import pytest

from backend.app.mock_provider import MockSemanticProvider
from backend.app.models import ConvertRequest
from backend.app.service import HarnessService
from backend.app.settings import DEFAULT_SIMULATION_SETTINGS

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "evals/regression_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
async def test_synthetic_regression_corpus(case):
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy=case["strategy"])
    )
    assert result.status == case["status"]
    assert result.fastExpression == case["expression"]
    assert len(result.simulationSettings) == 12


async def test_simple_reversal_preserves_close_window_direction_rank_and_settings():
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy="최근 5일 동안 종가가 많이 하락한 종목일수록 높은 순위를 부여한다.")
    )
    assert result.status == "PASS"
    assert result.fastExpression == "rank(-ts_delta(close, 5))"
    assert result.validation.sourceRequirementsPreserved
    assert result.validation.compilePassed
    assert result.simulationSettings == DEFAULT_SIMULATION_SETTINGS
    assert len(result.simulationSettings) == 12
    assert set(result.settingsSource.values()) == {"default"}
