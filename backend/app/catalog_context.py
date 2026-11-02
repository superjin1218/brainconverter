"""Request-local catalog selection shared by schema, validation and compilation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class CatalogField:
    id: str
    description: str
    type: str
    dataset: str


@dataclass(frozen=True)
class CatalogSelection:
    fields: Mapping[str, CatalogField]
    operators: frozenset[str]
    catalog_id: str
    generation_budget_microusd: int = 17000
    source_excerpts: tuple[str, ...] = ()


def source_excerpts(strategy):
    if not strategy or len(strategy.encode()) > 1000:
        return ()  # Long input retains exact local evidence validation without a large wire enum.
    sentences = re.split(r"(?<!\d)[.!?。;\n]|[.!?。;\n](?!\d)", strategy)
    clauses = [part for sentence in sentences for part in re.split(
        r"(?<=고)\s+|(?<=며)\s+|(?<=면서)\s+|\s+(?:and|but|while)\s+|,(?!\d)",
        sentence, flags=re.I,
    )]
    # Do not also offer a parent sentence containing several clauses: a model
    # could otherwise cite that same parent for multiple independent metrics.
    return tuple(dict.fromkeys(
        part.strip() for part in clauses
        if 2 <= len(part.strip()) <= 300
    ))


CURRENT_CATALOG: ContextVar[CatalogSelection | None] = ContextVar("brain_catalog", default=None)


@contextmanager
def catalog_context(fields, operators, catalog_id, *, generation_budget_microusd=17000,
                    source_strategy=None):
    selection = CatalogSelection(
        MappingProxyType({field.id: field for field in fields}), frozenset(operators), catalog_id,
        generation_budget_microusd,
        source_excerpts(source_strategy),
    )
    token = CURRENT_CATALOG.set(selection)
    try:
        yield selection
    finally:
        CURRENT_CATALOG.reset(token)


def render_field(name: str) -> str:
    selection = CURRENT_CATALOG.get()
    if selection is None:
        return name  # Low-level syntax tests; application requests always bind a catalog.
    field = selection.fields.get(name)
    if field is None:
        raise ValueError(f"제공된 필드 목록에 없는 이름입니다: {name}")
    if field.type == "VECTOR":
        if "vec_avg" not in selection.operators:
            raise ValueError("이 카탈로그에서 VECTOR 평균 연산을 사용할 수 없습니다.")
        return f"vec_avg({name})"
    if field.type != "MATRIX":
        raise ValueError(f"수치 측정에 사용할 수 없는 필드 자료형입니다: {field.type}")
    return name
