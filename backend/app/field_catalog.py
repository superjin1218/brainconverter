"""Scoped WQ metadata and semantic catalog retrieval, without indicator mappings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .catalog_context import CatalogField
from .catalog_embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    CatalogEmbeddings,
    QueryEmbedding,
)
from .data_fields import is_data_field

ROOT = Path(__file__).resolve().parents[2]
BASIC_FIELDS = frozenset({"open", "high", "low", "close", "volume", "returns"})


def catalog_directory() -> Path:
    return Path(os.getenv("BRAIN_CATALOG_DIRECTORY", str(ROOT / "data/brain_catalog")))


def field_document(field: CatalogField) -> str:
    return field.description[:1024]


def load_encoder(*, api_key=None):
    return CatalogEmbeddings(api_key=api_key)


@dataclass(frozen=True)
class CatalogCandidates:
    fields: tuple[CatalogField, ...]
    embedding_input_tokens: int = 0
    search_input_tokens: int = 0
    search_output_tokens: int = 0
    search_cost_microusd: int = 0
    search_max_cost_microusd: int = 0


def fields_digest(fields) -> str:
    content = json.dumps(fields, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(content).hexdigest()


class FieldCatalog:
    def __init__(self, fields, vectors, encoder, *, scope, operators, catalog_id):
        self.fields = tuple(fields)
        self.by_id = {field.id: field for field in self.fields}
        if len(self.by_id) != len(self.fields) or any(
            not is_data_field(field.id) or field.type not in {"MATRIX", "VECTOR"}
            for field in self.fields
        ):
            raise ValueError("카탈로그의 필드 식별자·자료형이 올바르지 않습니다.")
        self.vectors = np.asarray(vectors, dtype=np.float32)
        if self.vectors.ndim != 2 or self.vectors.shape[0] != len(self.fields):
            raise ValueError("필드 목록과 검색 색인이 일치하지 않습니다.")
        if not np.isfinite(self.vectors).all():
            raise ValueError("검색 색인에 유효하지 않은 값이 있습니다.")
        self.encoder, self.scope = encoder, scope
        self.operators, self.catalog_id = frozenset(operators), catalog_id
        self._tokens = [set(re.findall(
            r"[a-z0-9]+", (field.id + " " + field.description).lower()
        )) for field in self.fields]
        self._frequency = Counter(token for tokens in self._tokens for token in tokens)

    def ensure_scope(self, settings):
        if any(settings.get(key) != value for key, value in self.scope.items()):
            raise RuntimeError("선택한 시장·Universe·Delay의 필드 카탈로그를 먼저 갱신하세요.")

    def select(self, strategy, settings, *, limit=12, encoder=None):
        self.ensure_scope(settings)
        # Keep the encoder injectable so unit tests never make paid requests.
        search = (encoder or self.encoder).embed_query(strategy)
        if not isinstance(search, QueryEmbedding):
            raise ValueError("필드 검색 응답이 올바르지 않습니다.")
        queries = np.atleast_2d(np.asarray(search.vectors, dtype=np.float32))
        if (queries.shape[1] != self.vectors.shape[1] or not np.isfinite(queries).all()):
            raise ValueError("필드 검색 벡터가 올바르지 않습니다.")
        queries /= np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
        scores = self.vectors @ queries.T
        words = {word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9]*", strategy)}
        for index in range(len(self.fields)):
            scores[index, :] += min(0.2, sum(
                0.12 * math.log((len(self.fields) + 1) / (self._frequency[word] + 1))
                / math.log(len(self.fields) + 1) for word in words & self._tokens[index]
            ))
        # Interleave concepts so one dense family of near-duplicates cannot crowd
        # another requested concept out of the bounded generation prompt.
        orders = [sorted(range(len(self.fields)),
                         key=lambda i: (-float(scores[i, query]), self.fields[i].id))
                  for query in range(queries.shape[0])]
        order = (index for ranks in zip(*orders, strict=True) for index in ranks)
        chosen, descriptions = [], set()
        for index in order:
            field = self.fields[index]
            signature = (" ".join(field.description.lower().split()), field.type)
            if signature in descriptions:
                continue
            chosen.append(field)
            descriptions.add(signature)
            if len(chosen) >= limit:
                break
        # Basic fields are metadata rows too, needed by price comparisons/entry conditions.
        for name in sorted(BASIC_FIELDS):
            if name in self.by_id and self.by_id[name] not in chosen:
                chosen.append(self.by_id[name])
        return CatalogCandidates(
            tuple(chosen), search.embedding_input_tokens, search.search_input_tokens,
            search.search_output_tokens, search.search_cost_microusd,
            search.search_max_cost_microusd,
        )


def scope_key(settings) -> str:
    return ":".join(str(settings[key]) for key in (
        "instrumentType", "region", "universe", "delay",
    ))


@lru_cache(maxsize=10)
def load_catalog(key="EQUITY:USA:TOP3000:1") -> FieldCatalog:
    directory = catalog_directory()
    try:
        current = json.loads((directory / "current.json").read_text())
        version = current.get("scopes", {}).get(key)
        if version is None:
            if current.get("scopes"):
                raise ValueError()
            version = current["version"]  # Older snapshots are checked by ensure_scope below.
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", version):
            raise ValueError()
        path = directory / version
        data = json.loads((path / "catalog.json").read_text())
        if scope_key(data["scope"]) != key:
            raise ValueError()
        if data["embedding_model"] != EMBEDDING_MODEL:
            raise ValueError()
        if fields_digest(data["fields"]) != data["catalog_id"]:
            raise ValueError()
        vector_digest = hashlib.sha256((path / "vectors.npy").read_bytes()).hexdigest()
        if vector_digest != data["vectors_sha256"]:
            raise ValueError()
        fields = [CatalogField(**row) for row in data["fields"]]
        if not fields or any(row.type not in {"MATRIX", "VECTOR"} for row in fields):
            raise ValueError()
        if not BASIC_FIELDS <= {row.id for row in fields}:
            raise ValueError()
        vectors = np.load(path / "vectors.npy", allow_pickle=False)
        if vectors.shape != (len(fields), EMBEDDING_DIMENSIONS):
            raise ValueError()
        encoder = load_encoder()
        return FieldCatalog(
            fields, vectors, encoder,
            scope=data["scope"], operators=data["operators"], catalog_id=data["catalog_id"],
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise RuntimeError(
            "필드 카탈로그가 준비되지 않았습니다. 운영자가 목록을 갱신해야 합니다."
        ) from exc
