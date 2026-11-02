"""Offline transport checks for catalog search and the aggregate 34-KRW bound."""

import json

import httpx
import pytest

from backend.app.catalog_context import catalog_context
from backend.app.catalog_embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    CatalogEmbeddings,
    embedding_cost,
    search_payload,
)
from backend.app.openai_policy import OPENAI_POLICY
from backend.app.prompts import prepare_catalog_prompt
from backend.app.provider_errors import ProviderError
from backend.tests.conftest import TEST_OPERATORS, supplied_catalog
from backend.tests.provider_fixtures import FAKE_KEY, reply


def test_search_queries_are_concepts_then_catalog_embeddings_not_field_answers():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(request.url.path)
        assert request.headers['authorization'] == f'Bearer {FAKE_KEY}'
        if request.url.path == '/v1/chat/completions':
            assert body['model'] == OPENAI_POLICY.model
            assert body['max_completion_tokens'] == 128
            assert 'field identifiers' in body['messages'][0]['content']
            answer = reply(content=json.dumps({
                'queries': ['return on equity', 'positive news sentiment'],
            }))
            answer['usage'].update(prompt_tokens=100, completion_tokens=20)
            return httpx.Response(200, json=answer)
        assert request.url.path == '/v1/embeddings'
        assert body['model'] == EMBEDDING_MODEL
        assert body['input'] == ['return on equity', 'positive news sentiment']
        return httpx.Response(200, json={
            'model': EMBEDDING_MODEL, 'usage': {'total_tokens': 12},
            'data': [{'index': i, 'embedding': [1.0] * EMBEDDING_DIMENSIONS}
                     for i in [1, 0]],
        })

    encoder = CatalogEmbeddings(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
    search = encoder.embed_query('자기자본이익률과 긍정적인 뉴스가 높은 기업')
    assert calls == ['/v1/chat/completions', '/v1/embeddings']
    assert search.vectors.shape == (2, EMBEDDING_DIMENSIONS)
    assert search.embedding_input_tokens == 12
    assert search.search_cost_microusd == OPENAI_POLICY.estimate_cost(100, 20)
    assert search.search_cost_microusd < search.search_max_cost_microusd


@pytest.mark.parametrize('queries', [[], ['a'] * 4, ['x' * 161], [42], 'field_id'])
def test_invalid_search_output_stops_before_embedding_without_retry(queries):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=reply(content=json.dumps({'queries': queries})))

    with pytest.raises(ProviderError):
        encoder = CatalogEmbeddings(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
        encoder.embed_query('전략')
    assert calls == ['/v1/chat/completions']


@pytest.mark.parametrize('failure', ['shape', 'nan', 'index', 'usage'])
def test_invalid_embedding_response_is_rejected(failure):
    data = {
        'model': EMBEDDING_MODEL, 'usage': {'total_tokens': 1},
        'data': [{'index': 0, 'embedding': [1.0] * EMBEDDING_DIMENSIONS}],
    }
    if failure == 'shape':
        data['data'][0]['embedding'] = [1.0]
    if failure == 'nan':
        data['data'][0]['embedding'][0] = float('nan')
    if failure == 'index':
        data['data'][0]['index'] = 1
    if failure == 'usage':
        data['usage']['total_tokens'] = 999999

    def handler(request):
        # httpx's json= refuses non-finite values; exercise malformed upstream bytes.
        return httpx.Response(200, content=json.dumps(data).encode())

    with pytest.raises(ProviderError):
        CatalogEmbeddings(api_key=FAKE_KEY, transport=httpx.MockTransport(handler)).embed(['test'])


@pytest.mark.parametrize('strategy', ['자기자본이익률(ROE)이 높은 기업', '가' * 2000])
def test_all_three_stages_share_unchanged_reserve_even_for_long_input(strategy):
    _, maximum = search_payload(strategy)
    remaining = OPENAI_POLICY.reserve_microusd - maximum - embedding_cost(8000)
    catalog = supplied_catalog([f'listed_field_{i}' for i in range(40)])
    prompt, fields = prepare_catalog_prompt(
        strategy, catalog.fields, TEST_OPERATORS, 'test', generation_budget=remaining,
    )
    with catalog_context(fields, TEST_OPERATORS, 'test', generation_budget_microusd=remaining):
        body = OPENAI_POLICY.payload(prompt, strategy)
    size = len(json.dumps(body, ensure_ascii=False).encode())
    assert 256 <= body['max_completion_tokens'] <= 1024
    upper = OPENAI_POLICY.estimate_cost(size, body['max_completion_tokens'])
    assert upper + maximum + embedding_cost(8000) <= OPENAI_POLICY.reserve_microusd
    assert OPENAI_POLICY.budget_allowance_krw == 34


def test_incomplete_or_tampered_snapshot_fails_before_paid_search(tmp_path, monkeypatch):
    import hashlib

    import numpy as np

    from backend.app.field_catalog import fields_digest, load_catalog

    monkeypatch.setenv('BRAIN_CATALOG_DIRECTORY', str(tmp_path))
    version = tmp_path / 'v_test'
    version.mkdir()
    np.save(version / 'vectors.npy', np.ones((1, EMBEDDING_DIMENSIONS)))
    fields = [{'id': 'catalog_score', 'type': 'MATRIX', 'description': 'Score', 'dataset': 'test'}]
    data = {
        'fields': fields, 'catalog_id': fields_digest(fields),
        'embedding_model': EMBEDDING_MODEL,
        'vectors_sha256': hashlib.sha256((version / 'vectors.npy').read_bytes()).hexdigest(),
        'scope': {'instrumentType': 'EQUITY', 'region': 'USA', 'universe': 'TOP3000', 'delay': 1},
        'operators': ['rank'],
    }
    (version / 'catalog.json').write_text(json.dumps(data))
    (tmp_path / 'current.json').write_text(json.dumps({'version': 'v_test'}))
    load_catalog.cache_clear()
    try:
        with pytest.raises(RuntimeError, match='카탈로그'):
            load_catalog()
        data['fields'][0]['id'] = 'tampered_score'
        (version / 'catalog.json').write_text(json.dumps(data))
        with pytest.raises(RuntimeError, match='카탈로그'):
            load_catalog()
    finally:
        load_catalog.cache_clear()
