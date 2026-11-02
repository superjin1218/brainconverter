"""Import complete BRAIN metadata exports without receiving account credentials.

Input is saved JSON from authenticated data-fields and operators responses.
Paginated responses must be combined before importing; incomplete pages fail.
No network requests, simulations, key access, or hardcoded indicator mappings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.brain_catalog import DEFAULT_PATH  # noqa: E402


def records(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        rows = value.get("results", value.get("fields"))
        if not isinstance(rows, list) or value.get("next"):
            raise ValueError(
                "전체 메타데이터를 합친 JSON이 필요합니다. 다음 페이지가 남아 있습니다."
            )
        if value.get("count", len(rows)) != len(rows):
            raise ValueError("메타데이터 count와 레코드 수가 다릅니다. 페이지를 모두 합치세요.")
        return rows
    if not isinstance(value, list):
        raise ValueError("BRAIN 메타데이터는 JSON 배열이어야 합니다.")
    return value


def build_snapshot(field_paths: list[Path], operator_path: Path, scope: dict) -> dict:
    fields = {}
    for path in field_paths:
        for item in records(path):
            identifier = item.get("id", item.get("field_id"))
            dataset = item.get("dataset", item.get("dataset_id", ""))
            category = item.get("category", item.get("category_id", ""))
            row = {
                "id": identifier, "type": item["type"],
                "description": item.get("description") or "",
                "dataset": dataset.get("id", "") if isinstance(dataset, dict) else dataset,
                "category": category.get("id", "") if isinstance(category, dict) else category,
            }
            if identifier in fields and fields[identifier] != row:
                raise ValueError(f"BRAIN 필드 메타데이터가 서로 충돌합니다: {identifier}")
            fields[identifier] = row
    supported = set(json.loads(DEFAULT_PATH.read_text())["operators"])
    available = {item.get("name", item.get("id")) for item in records(operator_path)}
    operators = sorted(supported & available)
    if not operators or not fields:
        raise ValueError("사용할 수 있는 BRAIN 필드 또는 구현된 연산자가 없습니다.")
    return {
        "schemaVersion": "brain-catalog-v1", "scope": scope,
        "provenance": "Account-provided BRAIN metadata export; current permissions may change.",
        "sourceSha256": [hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [*field_paths, operator_path]],
        "operators": operators, "fields": sorted(fields.values(), key=lambda row: row["id"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", type=Path, action="append", required=True)
    parser.add_argument("--operators", type=Path, required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--delay", type=int, choices=(0, 1), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(args.fields, args.operators, {
        "instrumentType": "EQUITY", "region": args.region.upper(),
        "universe": args.universe.upper(), "delay": args.delay,
    })
    # Validate through the exact runtime loader before publishing the snapshot.
    from backend.app.brain_catalog import _load
    staging = args.output.with_suffix(".pending.json")
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    _load(str(staging.resolve()), staging.stat().st_mtime_ns)
    staging.replace(args.output)
    print(json.dumps({"fields": len(snapshot["fields"]), "operators": len(snapshot["operators"]),
                      "scope": snapshot["scope"]}))


if __name__ == "__main__":
    main()
