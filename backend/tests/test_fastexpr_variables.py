"""BRAIN-derived variables are declared before use; raw fields come from metadata."""

import pytest

from backend.app.catalog_context import CURRENT_CATALOG, CatalogField, catalog_context
from backend.app.draft_compiler import DraftCompiler
from backend.app.models import IntentEntry
from backend.tests.conftest import TEST_OPERATORS, SuppliedCatalog
from backend.tests.test_drafts import convert, draft
from backend.tests.test_intent_alignment import convert as convert_intent
from backend.tests.test_intent_alignment import metric, plan


@pytest.fixture(autouse=True)
def named_catalog():
    rows = [CatalogField(name, description, kind, "test-dataset") for name, description, kind in [
        ("open", "Open", "MATRIX"), ("high", "High", "MATRIX"),
        ("low", "Low", "MATRIX"), ("close", "Close", "MATRIX"),
        ("volume", "Volume", "MATRIX"), ("returns", "Daily returns", "MATRIX"),
        ("return_equity", "Return on Equity", "MATRIX"),
        ("equity", "Common/Ordinary Equity - Total", "MATRIX"),
        ("sales", "Sales/Turnover (Net)", "MATRIX"),
        ("fnd6_newa2v1300_ni", "Net Income (Loss)", "MATRIX"),
        ("nws18_sse", "News sentiment", "VECTOR"),
    ]]
    with catalog_context(rows, TEST_OPERATORS, "variable-scope-test"):
        yield SuppliedCatalog(rows)


def test_precomputed_roe_field_is_available_without_a_local_declaration():
    assert DraftCompiler().compile("group_rank(return_equity, industry)").kind == "series"


def test_roe_is_undefined_until_calculated_or_assigned_from_a_real_field():
    with pytest.raises(ValueError, match="필드"):
        DraftCompiler().compile("group_rank(roe, industry)")
    result = DraftCompiler().compile("roe = return_equity; group_rank(roe, industry)")
    assert result.code == "roe = return_equity;\ngroup_rank(roe, industry)"
    assert result.expanded_code == "group_rank(return_equity, industry)"


def test_calculated_roe_like_ratio_can_be_declared_from_real_input_fields():
    # This is a current-equity ratio fixture, not a claim about an exact ROE
    # accounting period or the catalog's precomputed Return on Equity definition.
    result = DraftCompiler().compile(
        "profitability = fnd6_newa2v1300_ni / equity; group_rank(profitability, industry)"
    )
    assert result.code.startswith("profitability = (fnd6_newa2v1300_ni / equity);")
    assert result.code.endswith("group_rank(profitability, industry)")
    assert result.expanded_code == "group_rank((fnd6_newa2v1300_ni / equity), industry)"


@pytest.mark.parametrize("program", [
    "roe = missing_income / equity; rank(roe)",
    "roe = roe + equity; rank(roe)",
    "a = b / equity; b = return_equity; rank(a)",
    "a = return_equity; a = return_assets; rank(a)",
    "close = return_equity; rank(close)",
    "rank = return_equity; rank(rank)",
    "industry = return_equity; rank(industry)",
    "roe = return_equity;",
    "roe = return_equity\ngroup_rank(roe, industry)",
    "roe = return_equity; import os; rank(roe)",
    "roe = return_equity; print(roe)",
    "roe = return_equity;; rank(roe)",
    "roe = return_equity; rank(close)",
    "a = close.__class__; rank(a)",
    "a = __import__('os'); rank(a)",
    "roe = return_equity; roe[0]",
])
def test_invalid_or_unsafe_variable_programs_are_rejected(program):
    with pytest.raises(ValueError):
        DraftCompiler().compile(program)


def test_vector_variables_keep_their_type_and_must_be_aggregated():
    compiler = DraftCompiler()
    result = compiler.compile("news = nws18_sse; rank(news)")
    assert result.expanded_code == "rank(vec_avg(nws18_sse))"
    with pytest.raises(ValueError):
        DraftCompiler().compile("news = nws18_sse; rank(vec_avg(news))")


def test_program_expansion_has_a_bound_before_exponentially_growing_aliases():
    source = "a = close; "
    last = "a"
    for i in range(20):
        current = f"v{i}"
        source += f"{current} = {last} + {last}; "
        last = current
    with pytest.raises(ValueError, match="복잡"):
        DraftCompiler().compile(source + f"rank({last})")


@pytest.mark.parametrize("source", ["a = a + close; rank(a)",
                                   "a = b / close; b = close; rank(a)"])
def test_variable_scope_is_enforced_even_in_syntax_only_mode(source):
    token = CURRENT_CATALOG.set(None)
    try:
        with pytest.raises(ValueError, match="정의"):
            DraftCompiler().compile(source)
    finally:
        CURRENT_CATALOG.reset(token)


async def test_declared_return_measurement_preserves_the_source_period():
    result = await convert("최근 5일 누적 수익률이 높을수록", draft(
        "r5 = close / ts_delay(close, 5) - 1; rank(r5)"
    ))
    assert result.status == "PASS", result.warnings
    assert "r5 = " in result.fastExpression
    assert result.fastExpression.endswith("rank(r5)")


async def test_derived_variable_formula_compiles_through_full_intent_path(named_catalog):
    source = "순이익을 자기자본으로 나눈 값을 계산하고 높은 기업을 선호"
    ir = plan([metric(source, operation="expression", field="fnd6_newa2v1300_ni", window=1,
                      formula="roe = fnd6_newa2v1300_ni / equity; roe")])
    result = await convert_intent(source, ir, catalog=named_catalog)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression.startswith("calc_1 = ")
    assert result.fastExpression.endswith("rank(calc_1)")
    assert "fnd6_newa2v1300_ni / equity" in result.fastExpression


async def test_declared_program_is_checked_again_after_variable_expansion(
    monkeypatch, named_catalog,
):
    from backend.app import intent_compiler
    source = "ROE가 높은 기업"
    ir = plan([metric(source, operation="raw", field="return_equity", window=1)])
    monkeypatch.setattr(intent_compiler, "declare_measurements", lambda *args:
                        "roe = return_equity; 1 - rank(roe)")
    result = await convert_intent(source, ir, catalog=named_catalog)
    assert result.status == "REJECTED"
    assert result.validation.intentPlanChecked is False


async def test_distinct_formulas_with_the_same_primary_field_get_distinct_bindings(named_catalog):
    source = "자기자본 대비 순이익이 높고 매출 대비 순이익도 높은 기업"
    ir = plan([
        metric("자기자본 대비 순이익이 높고", operation="expression", field="fnd6_newa2v1300_ni",
               window=1, formula="fnd6_newa2v1300_ni / equity"),
        metric("매출 대비 순이익도 높은 기업", operation="expression", field="fnd6_newa2v1300_ni",
               window=1, formula="fnd6_newa2v1300_ni / sales"),
    ])
    result = await convert_intent(source, ir, catalog=named_catalog)
    assert result.status == "PASS", result.warnings
    assert "calc_1 = " in result.fastExpression and "calc_2 = " in result.fastExpression
    assert result.fastExpression.endswith("rank(calc_1) + rank(calc_2)")


async def test_declared_gate_is_expanded_before_embedding_in_trade_when(named_catalog):
    source = "가격이 높은 기업. 거래량이 최근 20일 평균의 1.5배 이상일 때만"
    ir = plan([metric("가격이 높은 기업", operation="raw", field="close", window=1)])
    ir.entry = IntentEntry(source="거래량이 최근 20일 평균의 1.5배 이상일 때만", condition=(
        "average_volume = ts_mean(volume, 20); volume >= 1.5 * average_volume"
    ))
    result = await convert_intent(source, ir, catalog=named_catalog)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == (
        "trade_when(volume >= (1.5 * ts_mean(volume, 20)), rank(close), -1)"
    )
