"""Offline regression by default; --live explicitly enables paid OpenAI calls."""

import argparse
import ast
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.mock_provider import MockSemanticProvider  # noqa: E402
from backend.app.draft_compiler import expression_signature  # noqa: E402
from backend.app.models import ConvertRequest  # noqa: E402
from backend.app.openai_provider import OpenAIProvider  # noqa: E402
from backend.app.service import HarnessService  # noqa: E402


def expressions_match(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    try:
        return expression_signature(ast.parse(actual, mode="eval")) == expression_signature(
            ast.parse(expected, mode="eval")
        )
    except (SyntaxError, ValueError):
        return False


async def evaluate(args):
    if args.live:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env.local", interpolate=False)
    limit = args.limit if args.limit is not None else 1 if args.live else None
    cases = json.loads(args.cases.read_text())[:limit]
    service = HarnessService(OpenAIProvider() if args.live else MockSemanticProvider())
    rows = []
    for case in cases:
        started = time.monotonic()
        try:
            result = await service.convert(ConvertRequest(strategy=case["strategy"]))
            matched = (
                result.status == case["status"]
                and expressions_match(result.fastExpression, case["expression"])
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
        "--live",
        action="store_true",
        help="Make paid OpenAI calls using OPENAI_API_KEY",
    )
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/regression_cases.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/evaluation.json")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit는 1 이상이어야 합니다.")
    raise SystemExit(asyncio.run(evaluate(args)))
