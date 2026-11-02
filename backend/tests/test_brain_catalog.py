"""Regression tests for the actual name/type boundary, not mocked profitability."""

import asyncio
import json
from dataclasses import replace

import pytest

from backend.app.brain_catalog import (
    ACTIVE_CATALOG,
    get_catalog,
    select_fields,
)
from backend.app.draft_compiler import DraftCompiler
from backend.app.models import ConvertRequest, IntentEntry
from backend.app.openai_policy import OPENAI_POLICY
from backend.app.prompts import BASE_SYSTEM_PROMPT
from backend.app.provider_types import ProviderResult
from backend.app.response_schema import strict_schema
from backend.app.service import HarnessService
from backend.app.settings import DEFAULT_SIMULATION_SETTINGS
from backend.tests.test_intent_alignment import convert, metric, plan


async def test_production_roe_failure_is_rejected_and_real_catalog_id_works():
    source = "자기자본이익률(ROE)이 높은 기업"
    for field, expected in [("roe", "REJECTED"), ("return_equity", "PASS")]:
        result = await convert(source, plan([metric(
            source, operation="raw", field=field, window=1, group="industry",
        )]))
        assert result.status == expected, result.warnings
        if expected == "PASS":
            assert result.fastExpression == "group_rank(return_equity, industry)"
            assert result.validation.catalogFieldsChecked is True
            assert result.validation.fieldTypesChecked is True
            assert result.validation.brainExecutionChecked is None
        else:
            assert result.fastExpression is None


@pytest.mark.parametrize("aggregation,expected", [("none", "REJECTED"), ("avg", "PASS"),
                                                 ("sum", "PASS")])
async def test_news_vectors_must_be_reduced_before_numeric_operators(aggregation, expected):
    source = "최근 5일 뉴스 감성이 좋은 기업"
    result = await convert(source, plan([metric(
        source, operation="mean", field="nws18_ber", aggregation=aggregation, window=5,
    )]))
    assert result.status == expected, result.warnings
    if expected == "PASS":
        assert f"ts_mean(vec_{aggregation}(nws18_ber), 5)" in result.fastExpression


async def test_news_intent_cannot_be_replaced_with_social_media_sentiment():
    source = "뉴스 감성이 높은 기업"
    ir = plan([metric(source, operation="raw", field="scl12_sentiment", window=1)])
    result = await convert(source, ir)
    assert result.status == "REJECTED"
    assert any("뉴스" in warning for warning in result.warnings)


@pytest.mark.parametrize("expression", [
    "rank(nws18_ber)", "ts_mean(nws18_ber, 5)", "vec_avg(return_equity)",
    "rank(industry)", "close + nws18_ber", "rank(sales_growth_fake)",
    "ts_std(returns, 20)", "sma(close, 20)", "vec_avg(nws18_ber, 5)",
    "group_rank(return_equity, close)",
])
def test_invalid_brain_fields_types_and_operators_never_compile(expression):
    with pytest.raises(ValueError):
        DraftCompiler().compile(expression)


async def test_compound_financial_measurement_preserves_arithmetic_and_preference():
    source = "영업현금흐름과 순이익의 차이를 총자산으로 나눈 값이 높은 기업"
    formula = "(operating_cashflow_reported_value - fnd6_newa2v1300_ni) / fnd6_mfma1_at"
    result = await convert(source, plan([metric(
        source, operation="expression", field="operating_cashflow_reported_value",
        window=1, formula=formula,
    )]))
    assert result.status == "PASS", result.warnings
    assert "fnd6_mfma1_at" in result.fastExpression
    assert "operating_cashflow_reported_value - fnd6_newa2v1300_ni" in result.fastExpression
    assert result.fastExpression.startswith("rank(")


async def test_live_failure_cannot_split_one_arithmetic_measurement_into_two_scores():
    source = "영업활동현금흐름에서 순이익을 뺀 뒤 총자산으로 나눈 값이 클수록 높은 점수"
    ir = plan([
        metric("영업활동현금흐름", operation="difference", field="fnd6_mfma2_oancf",
               reference="fnd6_newa2v1300_ni", window=1),
        metric("총자산으로 나눈 값", operation="ratio", field="fnd6_mfma2_oancf",
               reference="fnd6_mfma1_at", window=1),
    ])
    result = await convert(source, ir)
    assert result.status == "REJECTED"
    assert result.fastExpression is None
    assert any("복합 측정식" in warning for warning in result.warnings)


async def test_two_explicit_financial_preferences_are_not_mistaken_for_one_chain():
    source = "순이익과 현금흐름의 차이가 작고 부채를 자산으로 나눈 비율이 낮은 기업"
    ir = plan([
        metric("순이익과 현금흐름의 차이가 작고", operation="difference", field="fnd6_newa2v1300_ni",
               reference="operating_cashflow_reported_value", window=1, preference="lower"),
        metric("부채를 자산으로 나눈 비율이 낮은 기업", operation="ratio",
               field="fnd6_cptnewqv1300_ltq", reference="fnd6_mfma1_at", window=1,
               preference="lower"),
    ])
    assert (await convert(source, ir)).status == "PASS"


async def test_live_failure_cannot_invert_total_debt_over_assets_or_use_current_debt():
    source = "총자산 대비 총부채 비율이 낮을수록"
    for numerator, denominator, expected in [
        ("fnd6_mfma1_at", "fnd6_mfmq_dlcq", "REJECTED"),
        ("fnd6_mfmq_dlcq", "fnd6_mfma1_at", "REJECTED"),
        ("fnd6_cptnewqv1300_ltq", "fnd6_mfma1_at", "PASS"),
    ]:
        ir = plan([metric(source, operation="ratio", field=numerator, reference=denominator,
                          preference="lower", window=1)])
        result = await convert(source, ir)
        assert result.status == expected, result.warnings


async def test_old_cached_invented_fields_do_not_bypass_new_validation():
    from backend.app.cached_results import recheck_cached
    result = await convert("ROE가 높은 기업", plan([metric(
        "ROE가 높은 기업", operation="raw", field="return_equity", window=1,
    )]))
    result.fastExpression = "group_rank(roe, industry)"
    result.catalogRevision = None
    checked = recheck_cached(result)
    assert checked.status == "REJECTED"
    assert checked.fastExpression is None
    assert checked.validation.brainExecutionChecked is None
    assert result.fastExpression is not None  # No mutation of the stored object.


async def test_valid_current_cache_is_unchanged_without_new_model_calls():
    from backend.app.cached_results import recheck_cached
    result = await convert("ROE가 높은 기업", plan([metric(
        "ROE가 높은 기업", operation="raw", field="return_equity", window=1,
    )]))
    assert recheck_cached(result).model_dump() == result.model_dump()


async def test_required_account_catalog_blocks_before_any_paid_inference(monkeypatch):
    monkeypatch.setenv("BRAIN_REQUIRE_SCOPED_CATALOG", "true")

    class Provider:
        name = "mock"

        async def interpret(self, *args):
            raise AssertionError("Unverified catalog must not consume an AI call")

    with pytest.raises(RuntimeError, match="카탈로그"):
        await HarnessService(Provider()).convert(ConvertRequest(strategy="ROE가 높은 기업"))


def test_importer_preserves_real_types_and_intersects_supported_account_operators(tmp_path):
    from scripts.import_brain_catalog import build_snapshot
    fields, operators = tmp_path / "fields.json", tmp_path / "operators.json"
    fields.write_text(json.dumps([{
        "id": "example_news", "type": "VECTOR", "description": "news sentiment",
        "dataset": {"id": "news"}, "category": {"id": "news"},
    }]))
    operators.write_text(json.dumps([{"name": "rank"}, {"name": "vec_avg"},
                                     {"name": "not_implemented_operator"}]))
    result = build_snapshot([fields], operators, {"region": "USA"})
    assert result["fields"][0]["type"] == "VECTOR"
    assert result["fields"][0]["category"] == "news"
    assert result["operators"] == ["rank", "vec_avg"]


@pytest.mark.parametrize("payload", [{"count": 2, "results": [{"id": "a"}]},
                                     {"next": "page2", "results": [{"id": "a"}]}])
def test_importer_cannot_mark_partial_metadata_pages_as_a_complete_catalog(tmp_path, payload):
    from scripts.import_brain_catalog import records
    path = tmp_path / "page.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        records(path)


def test_refresh_reads_only_metadata_and_paginates_without_simulating():
    import httpx

    from scripts.refresh_brain_catalog import read_metadata
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        if request.url.path == "/operators":
            return httpx.Response(200, json=[{"name": "rank"}])
        assert request.url.path == "/data-fields"
        offset = request.url.params["offset"]
        return httpx.Response(200, json={"count": 2, "results": [{"id": "a" + offset}]})

    with httpx.Client(base_url="https://api.worldquantbrain.com",
                      transport=httpx.MockTransport(handle)) as client:
        fields, operators = read_metadata(client, {"region": "USA", "delay": 1})
    assert len(fields) == 2 and operators == [{"name": "rank"}]
    assert len(calls) == 3


@pytest.mark.parametrize("formula", [
    "rank(return_equity)", "group_rank(return_equity, industry)",
    "trade_when(volume > 0, return_equity, -1)", "return_equity + made_up_field",
    "return_assets", "vec_avg(return_equity)",
])
async def test_compound_measurement_cannot_bypass_catalog_or_hide_scoring(formula):
    source = "ROE가 높은 기업"
    result = await convert(source, plan([metric(
        source, operation="expression", field="return_equity", formula=formula, window=1,
    )]))
    assert result.status == "REJECTED"


async def test_vector_in_gate_must_also_be_aggregated():
    source = "ROE가 높은 기업. 뉴스 감성이 양수일 때만 갱신"
    ir = plan([metric("ROE가 높은 기업", operation="raw", field="return_equity", window=1)])
    ir.entry = IntentEntry(source="뉴스 감성이 양수일 때만 갱신", condition="nws18_ber > 0")
    assert (await convert(source, ir)).status == "REJECTED"
    ir.entry.condition = "vec_avg(nws18_ber) > 0"
    assert (await convert(source, ir)).status == "PASS"


def test_request_schema_and_prompt_use_exact_retrieved_ids_and_keep_fixed_budget():
    selected = select_fields("ROE가 높은 기업", DEFAULT_SIMULATION_SETTINGS)
    assert "return_equity" in selected.ids
    assert "roe" not in selected.ids
    token = ACTIVE_CATALOG.set(selected)
    try:
        schema = strict_schema()
        assert schema["$defs"]["CatalogField"]["enum"] == list(selected.ids)
        for obj in [schema, *schema["$defs"].values()]:
            if obj.get("type") == "object":
                assert set(obj["required"]) == set(obj["properties"])
        payload = OPENAI_POLICY.payload(BASE_SYSTEM_PROMPT + selected.prompt(), "ROE가 높은 기업")
        assert len(json.dumps(payload, ensure_ascii=False).encode()) <= 16000
    finally:
        ACTIVE_CATALOG.reset(token)


async def test_long_request_packs_catalog_before_one_model_call_without_raising_budget():
    calls = []

    class Provider:
        name = "mock"

        async def interpret(self, system, strategy):
            payload = OPENAI_POLICY.payload(system, strategy)
            calls.append(payload)
            assert len(json.dumps(payload, ensure_ascii=False).encode()) <= 16000
            assert "return_equity" in strict_schema()["$defs"]["CatalogField"]["enum"]
            return ProviderResult(plan([metric(
                "ROE", operation="raw", field="return_equity", window=1,
            )]))

    request = ConvertRequest(strategy="ROE" + "가" * 1997)
    assert (await HarnessService(Provider()).convert(request)).status == "PASS"
    assert len(calls) == 1


@pytest.mark.parametrize("query,required", [
    ("ROE가 높은 기업", ["return_equity"]),
    ("fnd6_newa2v1300_ni가 높은 기업", ["fnd6_newa2v1300_ni"]),
    ("영업현금흐름과 순이익의 차이를 총자산으로 나눠", [
        "operating_cashflow_reported_value", "fnd6_newa2v1300_ni", "fnd6_mfma1_at",
    ]),
])
def test_retrieval_keeps_each_concept_and_explicit_identifier(query, required):
    selected = select_fields(query, DEFAULT_SIMULATION_SETTINGS)
    assert set(required) <= set(selected.ids)


def test_account_export_must_match_exact_simulation_scope():
    catalog = replace(get_catalog(), scope={
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
    })
    catalog.check_scope(DEFAULT_SIMULATION_SETTINGS)
    for change in [{"region": "CHN"}, {"delay": 0}, {"universe": "TOP1000"}]:
        with pytest.raises(ValueError, match="카탈로그"):
            catalog.check_scope({**DEFAULT_SIMULATION_SETTINGS, **change})


def test_configured_bad_catalog_never_falls_back_to_unrestricted_fields(monkeypatch, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schemaVersion":"wrong"}')
    monkeypatch.setenv("BRAIN_CATALOG_PATH", str(path))
    with pytest.raises(ValueError, match="카탈로그"):
        get_catalog()


async def test_request_catalogs_are_isolated_under_concurrency():
    seen = []

    class Provider:
        name = "mock"

        async def interpret(self, system, strategy):
            await asyncio.sleep(0)
            seen.append((strategy, ACTIVE_CATALOG.get().ids, strict_schema()))
            return ProviderResult(plan([metric(
                strategy, operation="raw", field="close", window=1,
            )]))

    service = HarnessService(Provider())
    await asyncio.gather(*[service.convert(ConvertRequest(strategy=s))
                           for s in ["ROE가 높은 기업", "뉴스 감성이 높은 기업"]])
    assert ACTIVE_CATALOG.get() is None
    assert seen[0][1] != seen[1][1]
    for _, ids, schema in seen:
        assert schema["$defs"]["CatalogField"]["enum"] == list(ids)


def test_operator_access_can_be_restricted_by_account_export():
    catalog = replace(get_catalog(), operators=frozenset({"rank"}))
    assert DraftCompiler(catalog).compile("rank(close)").code == "rank(close)"
    with pytest.raises(ValueError, match="연산자"):
        DraftCompiler(catalog).compile("rank(ts_mean(close, 5))")
