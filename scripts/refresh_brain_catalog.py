"""Read BRAIN account metadata and atomically refresh a scoped catalog.

Reads data-fields/operators only. Never runs simulations or submits alphas.
Credentials are entered with getpass, used only for the official HTTPS endpoint,
and are never stored in the export, logs or command arguments.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import json
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.brain_catalog import _load  # noqa: E402
from scripts.import_brain_catalog import build_snapshot  # noqa: E402

BASE_URL = "https://api.worldquantbrain.com"


def read_metadata(client: httpx.Client, scope: dict) -> tuple[list[dict], list[dict]]:
    fields = []
    count = None
    while count is None or len(fields) < count:
        for attempt in range(3):
            response = client.get("/data-fields", params={
                **scope, "offset": len(fields), "limit": 50,
            })
            if response.status_code != 429:
                break
            delay = response.headers.get("Retry-After", "3")
            time.sleep(min(30, max(1, float(delay) if delay.isdigit() else 3)))
        if response.is_error:
            raise ValueError(f"BRAIN 필드 목록 조회 실패: HTTP {response.status_code}")
        data = response.json()
        page = data.get("results")
        total = data.get("count")
        if (not isinstance(page, list) or not isinstance(total, int) or total <= 0
                or (count is not None and total != count) or not page):
            raise ValueError("BRAIN 필드 페이지가 비어 있거나 조회 도중 목록이 변경됐습니다.")
        fields.extend(page)
        count = total
    if len(fields) != count or len({f["id"] for f in fields}) != count:
        raise ValueError("BRAIN 필드 페이지가 중복되거나 불완전합니다.")
    response = client.get("/operators")
    if response.is_error:
        raise ValueError(f"BRAIN 연산자 목록 조회 실패: HTTP {response.status_code}")
    operators = response.json()
    if isinstance(operators, dict):
        rows = operators.get("results", [])
        if operators.get("next") or operators.get("count", len(rows)) != len(rows):
            raise ValueError("BRAIN 연산자 목록이 불완전합니다.")
        operators = rows
    if not isinstance(operators, list) or not operators:
        raise ValueError("BRAIN 연산자 목록을 읽지 못했습니다.")
    return fields, operators


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="USA")
    parser.add_argument("--universe", default="TOP3000")
    parser.add_argument("--delay", type=int, choices=(0, 1), default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scope = {"instrumentType": "EQUITY", "region": args.region.upper(),
             "universe": args.universe.upper(), "delay": args.delay}
    email = input("BRAIN email (not saved): ").strip()
    password = getpass.getpass("BRAIN password (not saved): ")
    with httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=False) as client:
        response = client.post("/authentication", auth=httpx.BasicAuth(email, password))
        del password
        if response.status_code not in {200, 201}:
            raise SystemExit(
                f"BRAIN 인증을 완료하지 못했습니다 (HTTP {response.status_code}). "
                "추가 인증이 필요하면 플랫폼에서 먼저 완료하세요."
            )
        fields, operators = read_metadata(client, scope)
    with tempfile.TemporaryDirectory(prefix="brain-metadata-") as temp:
        folder = Path(temp)
        field_path, operator_path = folder / "fields.json", folder / "operators.json"
        field_path.write_text(json.dumps(fields))
        operator_path.write_text(json.dumps(operators))
        snapshot = build_snapshot([field_path], operator_path, scope)
    snapshot["capturedAt"] = datetime.datetime.now(datetime.UTC).isoformat()
    staging = args.output.with_suffix(".pending.json")
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    _load(str(staging.resolve()), staging.stat().st_mtime_ns)
    staging.replace(args.output)
    print(json.dumps({"fields": len(snapshot["fields"]), "scope": scope,
                      "simulationsPerformed": False}))


if __name__ == "__main__":
    main()
