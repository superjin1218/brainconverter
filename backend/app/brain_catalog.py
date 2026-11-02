"""Ground generation in exported BRAIN metadata, never model-invented field names.

A reference snapshot proves name/type membership, not current account access.
An administrator can replace it with an account/scope-specific export.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .data_fields import DATA_FIELD_PATTERN

DEFAULT_PATH = Path(__file__).parent / "catalogs" / "brain_reference.json"
CORE_FIELDS = ("open", "high", "low", "close", "volume", "returns")

# Search vocabulary expands descriptions, never maps an indicator to a field ID
# or supplies a strategy formula. Matching IDs always come from the catalog.
SEARCH_TERMS = (
    (r"자기자본이익률|(?<![a-z])roe(?![a-z])", "return equity"),
    (r"총자산이익률|(?<![a-z])roa(?![a-z])", "return assets"),
    (r"주당\s*순이익|(?<![a-z])eps(?![a-z])", "earnings share"),
    (r"자기자본|자본총계", "equity"),
    (r"순이익|순익", "net income"),
    (r"영업\s*(?:활동\s*)?현금흐름", "cash flow operations operating"),
    (r"잉여현금흐름|(?<![a-z])fcf(?![a-z])", "free cash flow"),
    (r"현금흐름", "cash flow"),
    (r"총자산|자산", "assets total"),
    (r"총부채", "total liabilities"),
    (r"부채", "debt liabilities"),
    (r"매출", "sales revenue"),
    (r"성장", "growth"),
    (r"영업이익", "operating income"),
    (r"시가총액", "market capitalization"),
    (r"뉴스", "news"),
    (r"감성|심리", "sentiment"),
    (r"애널리스트|컨센서스|추정|전망", "analyst estimates mean"),
    (r"상향|하향|수정", "revision change"),
    (r"내재변동성", "implied volatility"),
    (r"콜\s*(?:옵션)?", "call option"),
    (r"풋\s*(?:옵션)?", "put option"),
    (r"배당", "dividend yield"),
    (r"장부|(?<![a-z])pbr(?![a-z])", "book price"),
    (r"공매도", "short interest"),
    (r"수익성", "profitability return"),
)


@dataclass(frozen=True)
class CatalogField:
    id: str
    type: str
    description: str
    dataset: str = ""
    category: str = ""


@dataclass(frozen=True)
class BrainCatalog:
    fields: dict[str, CatalogField]
    operators: frozenset[str]
    digest: str
    scope: dict | None
    provenance: str

    def check_scope(self, settings: dict) -> None:
        if (os.getenv("BRAIN_REQUIRE_SCOPED_CATALOG", "false").lower() == "true"
                and self.scope is None):
            raise ValueError("현재 BRAIN 계정·환경의 카탈로그를 먼저 연결해야 합니다.")
        if self.scope is not None and any(
            self.scope.get(key) != settings.get(key)
            for key in ("instrumentType", "region", "universe", "delay")
        ):
            raise ValueError("BRAIN 카탈로그의 Region·Universe·Delay가 요청 설정과 다릅니다.")

    def field(self, identifier: str) -> CatalogField:
        field = self.fields.get(identifier)
        if field is None:
            raise ValueError(f"BRAIN 카탈로그에 없는 데이터 필드입니다: {identifier}")
        return field


@dataclass(frozen=True)
class CatalogSelection:
    catalog: BrainCatalog
    ids: tuple[str, ...]

    def prompt(self) -> str:
        rows = [
            [name, self.catalog.fields[name].type, self.catalog.fields[name].category,
             self.catalog.fields[name].description[:120]]
            for name in self.ids
        ]
        return (
            "\nCATALOG (id,type,category,meaning). Select exact IDs ONLY from this list; "
            "never invent aliases. VECTOR requires aggregation=avg or sum before "
            "numeric operations. MATRIX uses aggregation=none. If no candidate "
            "expresses the request, return unsupported; never replace it with price. "
            "Field membership/type is checked, account access and simulation are not.\n"
            + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        )


ACTIVE_CATALOG: ContextVar[CatalogSelection | None] = ContextVar("brain_catalog", default=None)


@lru_cache(maxsize=4)
def _load(path: str, modified: int) -> BrainCatalog:
    del modified  # Part of the cache key, so an atomic snapshot replacement reloads it.
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schemaVersion") != "brain-catalog-v1":
        raise ValueError("BRAIN 카탈로그 버전이 올바르지 않습니다.")
    fields = {}
    for item in data["fields"]:
        field = CatalogField(**item)
        if (not re.fullmatch(DATA_FIELD_PATTERN, field.id)
                or field.type not in {"MATRIX", "VECTOR", "GROUP", "SYMBOL", "UNIVERSE"}
                or field.id in fields
                or not all(isinstance(value, str)
                           for value in (field.description, field.dataset, field.category))):
            raise ValueError("BRAIN 카탈로그 필드가 중복되거나 유효하지 않습니다.")
        fields[field.id] = field
    operators = data["operators"]
    if (not fields or not isinstance(operators, list) or not operators
            or not all(isinstance(op, str) for op in operators)):
        raise ValueError("BRAIN 필드·연산자 카탈로그가 비어 있습니다.")
    scope = data.get("scope")
    if scope is not None and set(scope) != {"instrumentType", "region", "universe", "delay"}:
        raise ValueError("BRAIN 카탈로그 환경 정보가 불완전합니다.")
    return BrainCatalog(fields, frozenset(operators), hashlib.sha256(raw).hexdigest(),
                        scope, data.get("provenance", "export"))


def get_catalog() -> BrainCatalog:
    selection = ACTIVE_CATALOG.get()
    if selection is not None:
        return selection.catalog
    path = Path(os.getenv("BRAIN_CATALOG_PATH", str(DEFAULT_PATH)))
    try:
        return _load(str(path.resolve()), path.stat().st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("BRAIN 카탈로그를 읽지 못했습니다. 설정·파일을 확인하세요.") from exc


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9]*|\d+", text.lower().replace("_", " ")))


def select_fields(strategy: str, settings: dict, *, limit: int = 20) -> CatalogSelection:
    catalog = get_catalog()
    catalog.check_scope(settings)
    expanded = strategy.lower()
    concepts = []
    for pattern, terms in SEARCH_TERMS:
        if re.search(pattern, expanded, re.I):
            expanded += " " + terms
            concepts.append(_tokens(terms))
    query = _tokens(expanded)
    numeric = [f for f in catalog.fields.values() if f.type in {"MATRIX", "VECTOR"}]
    documents = {f.id: _tokens(f.description + " " + f.id) for f in numeric}
    frequency = Counter(token for tokens in documents.values() for token in tokens)
    explicit = set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", strategy)) & documents.keys()
    preferred_category = ("news" if re.search(r"뉴스|(?<![a-z])news(?![a-z])", strategy, re.I)
                          else "socialmedia" if re.search(r"소셜|SNS|social", strategy, re.I)
                          else None)

    def score(field: CatalogField, terms: set[str] = query) -> float:
        overlap = terms & documents[field.id]
        return ((1000 if field.id in explicit else 0)
                + (10 if field.category == preferred_category else 0)) + sum(
            math.log(1 + len(numeric) / (1 + frequency[token])) for token in overlap
        ) / (1 + 0.025 * len(documents[field.id]))

    ranked = sorted(numeric, key=lambda f: (-score(f), len(f.id), f.id))
    chosen = [f.id for f in ranked if score(f) > 0][:limit]
    # Preserve candidates for each requested concept in composite measurements;
    # a long cash-flow description must not crowd every assets/income field out.
    diverse = []
    for concept in concepts:
        candidates = sorted(numeric, key=lambda f: (-score(f, concept), len(f.id), f.id))
        diverse.extend(f.id for f in candidates[:3] if score(f, concept) > 0)
    chosen = list(dict.fromkeys([*diverse, *chosen]))[:limit]
    # Explicit field requests must never be silently truncated out of the context.
    chosen = list(dict.fromkeys([*sorted(explicit), *chosen, *CORE_FIELDS]))
    chosen = [name for name in chosen if name in catalog.fields]
    if not chosen:
        raise ValueError("요청 환경의 카탈로그에 사용할 수 있는 숫자 필드가 없습니다.")
    return CatalogSelection(catalog, tuple(chosen))
