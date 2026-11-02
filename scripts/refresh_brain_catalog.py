"""Refresh WQ metadata and its local index. Never generates or simulates an alpha."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.catalog_context import CatalogField  # noqa: E402
from backend.app.data_fields import is_data_field  # noqa: E402
from backend.app.field_catalog import (  # noqa: E402
    BASIC_FIELDS,
    EMBEDDING_MODEL,
    catalog_directory,
    field_document,
    fields_digest,
    load_encoder,
    scope_key,
)

BASE = "https://api.worldquantbrain.com"


async def refresh(args):
    directory = args.output
    directory.mkdir(parents=True, exist_ok=True)
    embedding_values = dotenv_values(args.openai_env_file, interpolate=False)
    embedding_key = os.getenv("OPENAI_API_KEY") or embedding_values.get("OPENAI_API_KEY")
    if not embedding_key:
        raise RuntimeError("필드 색인에 사용할 OpenAI 키가 필요합니다.")
    encoder_task = asyncio.create_task(asyncio.to_thread(
        load_encoder, api_key=embedding_key,
    ))
    if args.reindex_existing:
        current = json.loads((directory / "current.json").read_text())
        data = json.loads((directory / current["version"] / "catalog.json").read_text())
        if fields_digest(data["fields"]) != data["catalog_id"]:
            raise RuntimeError("필드 목록의 내용 검증에 실패했습니다.")
        await write_catalog(directory, data["fields"], data["scope"], data["operators"],
                            encoder_task, fetched_at=data["fetched_at"])
        return
    values = dotenv_values(args.credentials_file, interpolate=False)
    email, password = values.get("WQ_EMAIL"), values.get("WQ_PASSWORD")
    if not email or not password:
        raise RuntimeError("WQ_EMAIL과 WQ_PASSWORD가 설정된 비공개 파일이 필요합니다.")
    if args.seed_catalog:
        with args.seed_catalog.open(encoding="utf-8-sig") as handle:
            datasets = sorted({r["dataset_id"] for r in csv.DictReader(handle) if r["dataset_id"]})
    elif args.all_datasets:
        datasets = None
    else:
        datasets = sorted(set(args.datasets.split(",")))
    scope = {
        "instrumentType": "EQUITY", "region": "USA",
        "universe": args.universe, "delay": args.delay,
    }
    rows = {}
    if args.include_snapshot:
        previous = json.loads(args.include_snapshot.read_text())
        if (previous["scope"] != scope
                or fields_digest(previous["fields"]) != previous["catalog_id"]):
            raise RuntimeError("필드 스냅샷의 범위 또는 내용 검증에 실패했습니다.")
        rows.update({row["id"]: row for row in previous["fields"]})
    slots = asyncio.Semaphore(4)
    pace = asyncio.Lock()
    next_request = 0
    async with httpx.AsyncClient(base_url=BASE, timeout=40, follow_redirects=False) as client:
        auth = await client.post("/authentication", auth=(email, password))
        if auth.status_code not in (200, 201):
            raise RuntimeError("BRAIN 인증을 완료하지 못했습니다. 계정·추가 인증을 확인하세요.")

        async def get(path, params=None):
            nonlocal next_request
            for _ in range(8):
                async with slots:
                    async with pace:
                        loop = asyncio.get_running_loop()
                        await asyncio.sleep(max(0, next_request - loop.time()))
                        next_request = loop.time() + 1.1
                    response = await client.get(path, params=params)
                if response.status_code != 429:
                    return response
                try:
                    wait = float(response.headers.get("Retry-After", "5"))
                except ValueError:
                    wait = 5
                await asyncio.sleep(min(max(wait, 1), 30))
            raise RuntimeError("BRAIN 메타데이터 요청 속도 제한이 계속되고 있습니다.")

        async def dataset(name):
            offset = 0
            while True:
                params = {**scope, "limit": 50, "offset": offset, "dataset.id": name}
                response = await get("/data-fields", params)
                if response.status_code in {400, 403, 404}:
                    print(f"dataset unavailable: {name}", flush=True)
                    return
                if response.status_code != 200:
                    raise RuntimeError(f"필드 목록 조회 실패: HTTP {response.status_code}")
                body = response.json()
                page = body.get("results")
                if not isinstance(page, list):
                    raise RuntimeError("필드 목록 응답이 올바르지 않습니다.")
                for row in page:
                    fid, kind = row.get("id"), row.get("type")
                    if not is_data_field(fid) or kind not in {"MATRIX", "VECTOR"}:
                        continue
                    record = {
                        "id": fid, "type": kind,
                        "dataset": (row.get("dataset") or {}).get("id", name or ""),
                        "description": str(row.get("description") or fid).strip(),
                    }
                    if fid in rows and rows[fid]["type"] != kind:
                        raise RuntimeError("필드 자료형이 데이터셋 간에 일치하지 않습니다.")
                    rows[fid] = record
                offset += len(page)
                if (not page or offset >= body.get("count", offset)
                        or (args.fields_per_dataset and offset >= args.fields_per_dataset)):
                    break
            print(f"dataset complete: {name}; numeric fields so far: {len(rows)}", flush=True)

        if datasets is None:
            response = await get("/data-sets", scope)
            if response.status_code != 200:
                raise RuntimeError("BRAIN 데이터셋 목록을 확인하지 못했습니다.")
            available = response.json()
            if isinstance(available, dict):
                available = available.get("results", [])
            datasets = sorted({row["id"] for row in available})
        # Paced starts avoid bursts, while independent requests can overlap network latency.
        await asyncio.gather(*(dataset(name) for name in datasets))
        response = await get("/operators")
        if response.status_code != 200:
            raise RuntimeError("연산자 목록을 확인하지 못했습니다.")
        operators = response.json()
        if isinstance(operators, dict):
            operators = operators.get("results", [])
        operators = sorted({row["name"] for row in operators if isinstance(row.get("name"), str)})
    if not rows or not operators:
        raise RuntimeError("사용 가능한 필드 또는 연산자가 없습니다.")
    fields = sorted(rows.values(), key=lambda row: row["id"])
    await write_catalog(directory, fields, scope, operators, encoder_task,
                        discovery={"datasets": len(datasets),
                                   "fields_per_dataset": args.fields_per_dataset,
                                   "included_snapshot": bool(args.include_snapshot)})


async def write_catalog(directory, fields, scope, operators, encoder_task, *, fetched_at=None,
                        discovery=None):
    if (not BASIC_FIELDS <= {row["id"] for row in fields}
            or any(not is_data_field(row["id"]) or row["type"] not in {"MATRIX", "VECTOR"}
                   for row in fields)):
        raise RuntimeError("필드 목록에 기본 데이터가 없거나 잘못된 식별자·자료형이 있습니다.")
    encoder = await encoder_task
    print(f"indexing {len(fields)} fields with {EMBEDDING_MODEL}", flush=True)

    def index():
        documents = [field_document(CatalogField(**row)) for row in fields]
        vectors, tokens = [], 0
        for offset in range(0, len(documents), 64):
            batch, used = encoder.embed(documents[offset:offset + 64])
            vectors.extend(batch)
            tokens += used
            print(f"indexed {len(vectors)}/{len(documents)} fields", flush=True)
        return np.asarray(vectors, dtype=np.float32), tokens

    vectors, index_tokens = await asyncio.to_thread(index)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    now = datetime.now(UTC)
    version = now.strftime("v%Y%m%dT%H%M%S")
    path = directory / version
    path.mkdir(exist_ok=False)
    data = {
        "scope": scope, "fetched_at": fetched_at or now.isoformat(),
        "embedding_model": EMBEDDING_MODEL,
        "index_embedding_input_tokens": index_tokens,
        "discovery": discovery,
        "catalog_id": fields_digest(fields), "operators": operators, "fields": fields,
    }
    np.save(path / "vectors.npy", vectors, allow_pickle=False)
    data["vectors_sha256"] = hashlib.sha256((path / "vectors.npy").read_bytes()).hexdigest()
    (path / "catalog.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary = directory / f"current-{os.getpid()}.tmp"
    scopes = {}
    if (directory / "current.json").is_file():
        previous = json.loads((directory / "current.json").read_text())
        scopes.update(previous.get("scopes", {}))
        if not scopes and previous.get("version"):
            old = json.loads((directory / previous["version"] / "catalog.json").read_text())
            scopes[scope_key(old["scope"])] = previous["version"]
    scopes[scope_key(scope)] = version
    temporary.write_text(json.dumps({"version": version, "scopes": scopes}) + "\n")
    temporary.replace(directory / "current.json")
    print(json.dumps({"ready": True, "fields": len(fields), "scope": scope,
                      "catalog_id": data["catalog_id"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--openai-env-file", type=Path, default=ROOT / ".env.local")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--seed-catalog", type=Path)
    source.add_argument("--datasets")
    source.add_argument("--reindex-existing", action="store_true")
    source.add_argument("--all-datasets", action="store_true")
    parser.add_argument("--fields-per-dataset", type=int, default=0,
                        help="0 reads every page; positive limits round up to 50-row pages")
    parser.add_argument("--include-snapshot", type=Path,
                        help="explicitly include a trusted snapshot from the same account/scope")
    parser.add_argument("--universe", default="TOP3000")
    parser.add_argument("--delay", type=int, choices=(0, 1), default=1)
    parser.add_argument("--output", type=Path, default=catalog_directory())
    args = parser.parse_args()
    if not args.reindex_existing and (not args.credentials_file or not (
        args.seed_catalog or args.datasets or args.all_datasets
    )):
        parser.error("refresh requires --credentials-file and "
                     "--all-datasets/--seed-catalog/--datasets")
    if args.fields_per_dataset < 0:
        parser.error("--fields-per-dataset must be nonnegative")
    try:
        asyncio.run(refresh(args))
    except (httpx.HTTPError, ValueError, OSError, RuntimeError, KeyError) as exc:
        # Upstream messages/exception reprs can contain credential-bearing details.
        print("Catalog refresh failed. Check private credentials, API access and model cache.",
              file=sys.stderr)
        if isinstance(exc, RuntimeError) and str(exc).startswith(("BRAIN", "필드", "연산자")):
            print(str(exc), file=sys.stderr)
        else:
            print(type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
