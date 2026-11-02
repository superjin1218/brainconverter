"""Catalog selection, typed compilation and actual experiment failure regressions."""

import asyncio
import json

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.catalog_context import CURRENT_CATALOG, CatalogField, catalog_context
from backend.app.catalog_embeddings import QueryEmbedding
from backend.app.field_catalog import FieldCatalog
from backend.app.intent_compiler import source_evidence_errors, source_spans
from backend.app.models import ConvertRequest, IntentEntry
from backend.app.openai_policy import OPENAI_POLICY
from backend.app.openai_provider import OpenAIProvider
from backend.app.prompts import prepare_catalog_prompt
from backend.app.provider_errors import ProviderError
from backend.app.provider_types import ProviderResult
from backend.app.response_schema import strict_schema
from backend.app.service import HarnessService
from backend.tests.conftest import TEST_OPERATORS, supplied_catalog
from backend.tests.provider_fixtures import FAKE_KEY, reply
from backend.tests.test_intent_alignment import convert, metric, plan


def test_bound_schema_and_pydantic_reject_unlisted_field_and_reference():
    catalog = supplied_catalog(["listed_score", "listed_reference"])
    with catalog_context(catalog.fields, catalog.operators, catalog.catalog_id):
        properties = strict_schema()["$defs"]["IntentMetric"]["properties"]
        assert properties["field"]["enum"] == ["listed_reference", "listed_score"]
        assert properties["reference"]["anyOf"][0]["enum"] == properties["field"]["enum"]
        with pytest.raises(ValidationError):
            metric("이익률", operation="raw", field="roe", window=1)
        with pytest.raises(ValidationError):
            metric("이익률", operation="ratio", field="listed_score", window=1,
                   reference="invented_denominator")
    assert CURRENT_CATALOG.get() is None


async def test_openai_request_contains_actual_candidate_list_and_enum():
    strategy = "이익률이 높은 기업"
    catalog = supplied_catalog(["supplied_profitability"])
    ir = plan([metric(strategy, operation="raw", field="supplied_profitability", window=1)])

    def handler(request):
        body = json.loads(request.content)
        assert "FIELD CANDIDATES" in body["messages"][0]["content"]
        field = body["response_format"]["json_schema"]["schema"]["$defs"]["IntentMetric"]
        assert field["properties"]["field"]["enum"] == ["supplied_profitability"]
        assert strategy in field["properties"]["source"]["enum"]
        assert all(source in strategy for source in field["properties"]["source"]["enum"])
        assert "Supplied test field supplied_profitability" not in (
            field["properties"]["source"]["enum"]
        )
        return httpx.Response(200, json=reply(content=ir.model_dump_json()))

    provider = OpenAIProvider(httpx.MockTransport(handler), api_key=FAKE_KEY)
    result = await HarnessService(provider, catalog=catalog).convert(
        ConvertRequest(strategy=strategy)
    )
    assert result.fastExpression == "rank(supplied_profitability)"


async def test_even_a_provider_ignoring_enum_cannot_output_unknown_field():
    strategy = "이익률이 높은 기업"
    ir = plan([metric(strategy, operation="raw", field="roe", window=1)])
    catalog = supplied_catalog(["supplied_profitability"])
    with pytest.raises(ProviderError, match="형식"):
        await convert(strategy, ir, catalog=catalog)


@pytest.mark.parametrize("operation,reference,expected", [
    ("raw", None, "rank(vec_avg(event_score))"),
    ("mean", None, "rank(ts_mean(vec_avg(event_score), 21))"),
    ("ratio", "matrix_price", "rank((vec_avg(event_score) / matrix_price))"),
    ("ratio", "vector_reference", "rank((vec_avg(event_score) / vec_avg(vector_reference)))"),
])
async def test_vector_reduction_precedes_matrix_operations(operation, reference, expected):
    catalog = supplied_catalog(
        ["event_score", "matrix_price", "vector_reference"],
        vector_names=["event_score", "vector_reference"],
    )
    strategy = "관찰한 지표가 높은 종목"
    ir = plan([metric(strategy, field="event_score", operation=operation, reference=reference,
                      window=21 if operation == "mean" else 1)])
    result = await convert(strategy, ir, catalog=catalog)
    assert result.status == "PASS", result.warnings
    assert result.fastExpression == expected
    assert "vec_avg(vec_avg" not in result.fastExpression


async def test_vector_fields_in_an_entry_condition_are_reduced_too():
    catalog = supplied_catalog(["matrix_score", "event_gate"], vector_names=["event_gate"])
    strategy = "지표가 높은 종목. 이벤트가 양수일 때"
    ir = plan([metric("지표가 높은 종목", operation="raw", field="matrix_score", window=1)])
    ir.entry = IntentEntry(source="이벤트가 양수일 때", condition="event_gate > 0")
    result = await convert(strategy, ir, catalog=catalog)
    assert result.fastExpression == (
        "trade_when(vec_avg(event_gate) > 0, rank(matrix_score), -1)"
    )


async def test_missing_vector_operator_is_not_silently_used():
    catalog = supplied_catalog(["event_score"], vector_names=["event_score"])
    catalog.operators = TEST_OPERATORS - {"vec_avg"}
    strategy = "관찰한 지표가 높은 종목"
    result = await convert(strategy, plan([
        metric(strategy, operation="raw", field="event_score", window=1),
    ]), catalog=catalog)
    assert result.status == "REJECTED"
    assert result.fastExpression is None


def test_parentheses_and_whitespace_preserve_actual_source_spans():
    strategy = "주가수익비율(PER)이 낮은 기업을 선호한다."
    spans = source_spans(strategy, "PER이 낮은")
    assert len(spans) == 1
    assert strategy[slice(*spans[0])] == "PER)이 낮은"
    ir = plan([metric("PER이 낮은", operation="raw", field="listed_price_multiple", window=1)])
    assert source_evidence_errors(strategy, ir) == []
    assert source_spans(strategy, "PER 이  낮은") == spans
    assert source_spans(strategy, "“PER이 낮은”") == spans
    assert source_spans(strategy, '"PER이 낮은"') == spans
    assert source_spans(strategy, "“PER이 높은”") == []
    assert source_spans(strategy, "PER이 높은") == []


def test_normalized_quotes_cannot_reuse_overlapping_original_spans():
    ir = plan([
        metric("PER이 낮은", operation="raw", field="one", window=1),
        metric("PER", operation="raw", field="two", window=1),
    ])
    assert any("중복" in error for error in source_evidence_errors("(PER)이 낮은 기업", ir))


async def test_explicit_return_volatility_cannot_use_price_volatility():
    strategy = "최근 20일 일간 수익률 변동성이 낮은 종목"
    ir = plan([metric(strategy, operation="std_dev", field="close", window=20,
                      preference="lower")])
    result = await convert(strategy, ir)
    assert result.status == "REJECTED"
    assert any("일간 수익률" in warning for warning in result.warnings)
    ir.metrics[0].field = "returns"
    assert (await convert(strategy, ir)).status == "PASS"


async def test_concurrent_conversions_keep_independent_schema_candidates():
    observed = {}
    template = plan([metric("기준", operation="raw", field="field_a", window=1)])

    class Provider:
        name = "test"

        async def interpret(self, prompt, strategy):
            await asyncio.sleep(0)
            ids = strict_schema()["$defs"]["IntentMetric"]["properties"]["field"]["enum"]
            observed[strategy] = ids
            return ProviderResult(ir=template.model_copy(update={"metrics": [
                metric(strategy, operation="raw", field=ids[0], window=1),
            ]}))

    a = HarnessService(Provider(), catalog=supplied_catalog(["field_a"]))
    b = HarnessService(Provider(), catalog=supplied_catalog(["field_b"]))
    results = await asyncio.gather(
        a.convert(ConvertRequest(strategy="첫 번째 지표")),
        b.convert(ConvertRequest(strategy="두 번째 지표")),
    )
    assert observed == {"첫 번째 지표": ["field_a"], "두 번째 지표": ["field_b"]}
    assert [result.fastExpression for result in results] == ["rank(field_a)", "rank(field_b)"]
    assert CURRENT_CATALOG.get() is None


def test_candidate_context_respects_the_existing_request_and_cost_limit():
    fields = [CatalogField(f"listed_field_{i}", "설명 " * 100, "MATRIX", "test")
              for i in range(100)]
    strategy = "가" * 2000
    prompt, chosen = prepare_catalog_prompt(strategy, fields, TEST_OPERATORS, "test")
    with catalog_context(chosen, TEST_OPERATORS, "test"):
        body = OPENAI_POLICY.payload(prompt, strategy)
        assert len(json.dumps(body, ensure_ascii=False).encode()) <= 16000
    assert 8 <= len(chosen) < 100
    assert OPENAI_POLICY.budget_allowance_krw == 34


def test_scope_mismatch_prevents_unverified_candidates():
    class Encoder:
        def embed_query(self, text):
            raise AssertionError("wrong scopes must fail before embedding")

    catalog = FieldCatalog(
        [CatalogField("listed", "Known field", "MATRIX", "test")], [[1, 0]], Encoder(),
        scope={"region": "USA", "universe": "TOP3000", "delay": 1},
        operators=TEST_OPERATORS, catalog_id="test",
    )
    with pytest.raises(RuntimeError, match="카탈로그"):
        catalog.select("지표", {"region": "USA", "universe": "TOP500", "delay": 1})


def test_retrieval_uses_metadata_and_returns_existing_rows_only():
    class Encoder:
        def embed_query(self, text):
            return QueryEmbedding(np.array([1, 0]))

    fields = [CatalogField("listed_a", "field A", "MATRIX", "test"),
              CatalogField("listed_b", "field B", "VECTOR", "test")]
    catalog = FieldCatalog(fields, [[0, 1], [1, 0]], Encoder(), scope={},
                           operators=TEST_OPERATORS, catalog_id="test")
    selected = catalog.select("요청한 관측값", {}, limit=1)
    assert selected.fields == (fields[1],)
    assert selected.embedding_input_tokens == 0


def test_multiconcept_retrieval_interleaves_different_concepts():
    class Encoder:
        def embed_query(self, text):
            return QueryEmbedding(np.array([[1, 0], [0, 1]]))

    fields = [CatalogField(f'family_a_{i}', f'First concept {i}', 'MATRIX', 'test')
              for i in range(20)]
    fields.append(CatalogField('family_b', 'Second concept', 'VECTOR', 'test'))
    catalog = FieldCatalog(
        fields, [[1, 0]] * 20 + [[0, 1]], Encoder(), scope={},
        operators=TEST_OPERATORS, catalog_id='test',
    )
    assert catalog.select('두 개념', {}, limit=2).fields[1].id == 'family_b'


async def test_explicit_mock_mode_never_loads_or_queries_a_catalog(monkeypatch):
    from backend.app.mock_provider import MockSemanticProvider

    def forbidden(*args):
        raise AssertionError('mock mode must remain offline')

    monkeypatch.setattr('backend.app.service.load_catalog', forbidden)
    result = await HarnessService(MockSemanticProvider()).convert(
        ConvertRequest(strategy='최근 5일 수익률이 낮은 종목'),
    )
    assert result.status == 'PASS'
    assert result.usage['costMicrousd'] == 0


async def test_search_and_embedding_usage_are_counted_with_generation(synthetic_catalog):
    from backend.app.field_catalog import CatalogCandidates

    original = synthetic_catalog.select

    def select(*args, **kwargs):
        return CatalogCandidates(original(*args, **kwargs).fields, 10, 100, 20, 165, 1500)

    synthetic_catalog.select = select
    strategy = '지표가 높은 종목'
    result = await convert(strategy, plan([
        metric(strategy, operation='raw', field='model_selected_field', window=1),
    ]), catalog=synthetic_catalog)
    # The fixture's inference has nonzero usage; the search usage is additional.
    assert result.usage['searchInputTokens'] == 100
    assert result.usage['searchOutputTokens'] == 20
    assert result.usage['embeddingInputTokens'] == 10
    assert result.usage['inputTokens'] == 1000
    assert result.usage['outputTokens'] == 200
    assert result.usage['costMicrousd'] == 1651


def test_multiple_preferences_offer_disjoint_user_clauses_not_a_shared_parent():
    strategy = '자기자본이익률(ROE)이 높고 주가수익비율(PER)이 낮은 기업을 선호한다.'
    catalog = supplied_catalog(['first_measure', 'second_measure'])
    with catalog_context(catalog.fields, catalog.operators, 'test', source_strategy=strategy):
        source = strict_schema()['$defs']['IntentMetric']['properties']['source']['enum']
    assert source == ['자기자본이익률(ROE)이 높고', '주가수익비율(PER)이 낮은 기업을 선호한다']
    spans = [source_spans(strategy, excerpt)[0] for excerpt in source]
    assert spans[0][1] <= spans[1][0]
    assert strategy not in source


def test_ratio_offset_removal_preserves_scores_with_ties_and_peer_groups():
    from backend.app.intent_compiler import _rank

    ratios = [0.5, 1.0, 1.5, 1.5, -0.5, 2.0]
    for groups in [[0] * 6, [0, 0, 0, 1, 1, 1]]:
        before = _rank([value - 1 for value in ratios], groups)
        after = _rank(ratios, groups)
        assert before == after
        assert [1 - value for value in before] == [1 - value for value in after]
