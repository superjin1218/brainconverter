"""Model-selected names pass through unchanged; these fixtures are not a BRAIN catalog."""

import pytest
from pydantic import ValidationError

from backend.app.draft_compiler import DraftCompiler
from backend.app.models import EntryIR, IntentEntry, SignalIR
from backend.app.response_schema import strict_schema
from backend.tests.provider_fixtures import example_ir
from backend.tests.test_drafts import convert as convert_draft
from backend.tests.test_drafts import draft
from backend.tests.test_intent_alignment import convert, metric, plan


@pytest.mark.parametrize("field", ["model_profitability_a", "model_profitability_b"])
async def test_same_financial_request_preserves_whichever_field_the_model_selects(field):
    strategy = "ROE가 높은 기업을 선호한다"
    ir = plan([metric(strategy, operation="raw", field=field, window=1)])
    result = await convert(strategy, ir)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == f"rank({field})"
    assert field in result.strategyExplanation
    assert any(field in assumption and "BRAIN" in assumption for assumption in result.assumptions)


@pytest.mark.parametrize("operation,window,reference", [
    ("raw", 1, None), ("mean", 21, None), ("delta", 21, None),
    ("ratio", 1, "model_equity_field"), ("difference", 1, "model_equity_field"),
    ("correlation", 21, "model_equity_field"),
])
async def test_model_selected_fields_work_through_measurements_and_reference(
    operation, window, reference,
):
    strategy = "재무 지표가 높은 회사를 선호한다"
    ir = plan([metric(strategy, operation=operation, field="model_income_field",
                      reference=reference, window=window)])
    result = await convert(strategy, ir)
    assert result.status == "PASS", result.warnings
    assert "model_income_field" in result.fastExpression
    if reference:
        assert reference in result.fastExpression


async def test_entry_and_preference_can_use_independent_new_data_fields():
    strategy = "재무 점수가 높은 회사. 다른 지표가 양수일 때만 거래"
    ir = plan([metric("재무 점수가 높은 회사", operation="raw",
                      field="model_score_field", window=1)])
    ir.entry = IntentEntry(source="다른 지표가 양수일 때만 거래",
                           condition="model_gate_field > 0")
    result = await convert(strategy, ir)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == (
        "trade_when(model_gate_field > 0, rank(model_score_field), -1)"
    )


@pytest.mark.parametrize("strategy", [
    "ROE가 높은 기업", "PER이 낮은 종목", "뉴스 감성이 좋은 주식", "재무 성장 지표가 높은 기업",
])
async def test_draft_has_no_dataset_category_blacklist(strategy):
    result = await convert_draft(strategy, draft("rank(model_selected_field)"))
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == "rank(model_selected_field)"


def test_wire_schema_does_not_enumerate_allowed_data_fields():
    field = strict_schema()["$defs"]["IntentMetric"]["properties"]["field"]
    assert field["type"] == "string"
    assert "enum" not in field
    assert "pattern" in field


def test_legacy_schema_field_types_are_open_too():
    ir = example_ir()
    assert SignalIR.model_validate({**ir.signal.model_dump(), "field": "new_signal"}).field == (
        "new_signal"
    )
    assert EntryIR.model_validate({**ir.entry.model_dump(), "field": "new_entry"}).field == (
        "new_entry"
    )


@pytest.mark.parametrize("name", [
    "field_name", "NewDataset42", "a", "model_financial_field_2026",
])
def test_compiler_preserves_valid_identifiers_verbatim(name):
    assert DraftCompiler().compile(f"rank({name})").code == f"rank({name})"


@pytest.mark.parametrize("field", [
    "x.y", "field[0]", "field + close", "rank(close)", "__import__", "a;import os",
    "한글필드", "1field", "field\n", "industry", "sector", "subindustry", "True", "None",
    "return", "a" * 129, "", None, 123, ["close"], {"field": "close"},
])
def test_open_field_schema_still_rejects_code_and_nonidentifiers(field):
    with pytest.raises(ValidationError):
        metric("재무 지표", operation="raw", field=field, window=1)


@pytest.mark.parametrize("field", ["x.y", "field[0]", "field + close", "rank(close)"])
def test_reference_cannot_smuggle_a_formula(field):
    with pytest.raises(ValidationError):
        metric("재무 지표", operation="ratio", field="custom_data", reference=field, window=1)


@pytest.mark.parametrize("expression", [
    "unknown_function(custom_field)", "custom_field.__class__", "custom_field[0]",
    "__import__('os')", "custom_field + True", "rank(_invalid)",
])
def test_open_fields_do_not_open_functions_or_python_execution(expression):
    with pytest.raises(ValueError):
        DraftCompiler().compile(expression)
