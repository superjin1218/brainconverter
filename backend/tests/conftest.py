"""Unit tests use a supplied catalog; no WQ login or model download occurs."""

import pytest

from backend.app.catalog_context import CatalogField
from backend.app.field_catalog import CatalogCandidates

TEST_OPERATORS = frozenset({
    "rank", "abs", "ts_delay", "ts_delta", "ts_mean", "ts_sum", "ts_std_dev", "ts_min",
    "ts_max", "ts_rank", "ts_corr", "group_rank", "group_neutralize", "trade_when",
    "if_else", "vec_avg",
})


class SuppliedCatalog:
    def __init__(self, fields):
        self.fields = fields
        self.operators = TEST_OPERATORS
        self.catalog_id = "unit-test-supplied-catalog"

    def select(self, strategy, settings, **kwargs):
        return CatalogCandidates(tuple(self.fields))

    def ensure_scope(self, settings):
        pass


def supplied_catalog(names, *, vector_names=()):
    return SuppliedCatalog([
        CatalogField(name, "Supplied test field " + name,
                     "VECTOR" if name in vector_names else "MATRIX", "test-dataset")
        for name in names
    ])


@pytest.fixture(autouse=True)
def offline_catalog(monkeypatch):
    catalog = supplied_catalog(["open", "high", "low", "close", "volume", "returns"])
    monkeypatch.setattr("backend.app.service.load_catalog", lambda *args: catalog)


@pytest.fixture
def synthetic_catalog():
    return supplied_catalog([
        "open", "high", "low", "close", "volume", "returns", "model_profitability_a",
        "model_profitability_b", "model_equity_field", "model_income_field", "model_gate_field",
        "model_score_field", "model_selected_field",
    ])
