"""Offline regression by default; --live explicitly enables paid MuseSpark calls."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models import ConvertRequest  # noqa: E402
from backend.app.provider import MockSemanticProvider, MuseSparkProvider  # noqa: E402
from backend.app.service import HarnessService  # noqa: E402


async def evaluate(args):
    limit = args.limit if args.limit is not None else 1 if args.live else 100
    cases = json.loads(args.cases.read_text())[:limit]
    service = HarnessService(MuseSparkProvider() if args.live else MockSemanticProvider())
    rows = []
    for case in cases:
        started = time.monotonic()
        try:
            result = await service.convert(ConvertRequest(strategy=case["strategy"]))
            matched = (
                result.status == case["status"] and result.fastExpression == case["expression"]
            )
            rows.append(
                {
                    "id": case["id"],
                    "matched": matched,
                    "status": result.status,
                    "elapsedMs": round((time.monotonic() - started) * 1000),
                    "usage": result.usage,
                }
            )
        except RuntimeError:
            rows.append({"id": case["id"], "matched": False, "status": "ERROR"})
    report = {
        "provider": service.provider.name,
        "dataset": args.cases.name,
        "cases": len(rows),
        "matched": sum(row["matched"] for row in rows),
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{report['provider']}: {report['matched']}/{len(rows)} matched; {args.output}")
    return 0 if report["matched"] == len(rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Make paid calls with AI_GATEWAY_API_KEY"
    )
    parser.add_argument("--accept-contributor-terms", action="store_true")
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/regression_cases.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/evaluation.json")
    args = parser.parse_args()
    if args.live and not args.accept_contributor_terms:
        parser.error("실제 평가에는 Contributor의 Meta 학습 활용 조건 동의가 필요합니다.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit는 1 이상이어야 합니다.")
    raise SystemExit(asyncio.run(evaluate(args)))
