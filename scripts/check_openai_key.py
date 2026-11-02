"""Compare a privately entered key with .env.local and query model metadata only."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-mini"


def check_key(key: str) -> dict:
    if not key or any(c.isspace() for c in key) or not key.isascii():
        return {"authenticated": False, "error": "missing_or_malformed_key"}
    try:
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            response = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": "Bearer " + key},
            )
        data = response.json()
        result = {"http_status": response.status_code, "authenticated": response.is_success}
        if response.is_success:
            result["model_available"] = any(
                model.get("id") == MODEL for model in data.get("data", [])
                if isinstance(model, dict)
            )
        else:
            code = data.get("error", {}).get("code")
            allowed = {
                "invalid_api_key", "insufficient_permissions", "insufficient_quota",
                "model_not_found", "account_deactivated", "organization_deactivated",
            }
            result["error_code"] = code if code in allowed else "unclassified"
        # Never print provider error messages, headers, or key identifiers.
        return result
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {"authenticated": False, "error": "network_or_response_error"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt", action="store_true", help="Enter a key privately; never save it"
    )
    args = parser.parse_args()
    stored = (dotenv_values(ROOT / ".env.local").get("OPENAI_API_KEY") or "").strip()
    report = {"env_file": str(ROOT / ".env.local"), "generation_requested": False,
              "key_written": False}
    if args.prompt:
        if not sys.stdin.isatty():
            print("Run --prompt in your own interactive terminal; input must remain hidden.")
            return 2
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                entered = getpass.getpass("OpenAI API key (hidden, not saved): ").strip()
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
            print("Private input unavailable or canceled. No key saved or printed.")
            return 2
        report["entered_key_matches_env_file"] = bool(entered) and entered == stored
        report["entered_key_check"] = check_key(entered)
        if entered != stored:
            report["stored_key_check"] = check_key(stored)
    else:
        report["stored_key_check"] = check_key(stored)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    result = report.get("entered_key_check", report.get("stored_key_check", {}))
    return 0 if result.get("authenticated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
