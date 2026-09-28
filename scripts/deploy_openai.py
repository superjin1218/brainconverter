"""Preflight, migrate when authorized credentials exist, and deploy this checkout.

Secrets go through HTTPS headers or subprocess stdin; never shell arguments/logs.
--check performs no remote mutations or paid inference.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.openai_policy import OPENAI_MODEL  # noqa: E402
from backend.app.openai_provider import OpenAIProvider  # noqa: E402
from backend.app.provider_diagnostics import diagnostic_runtime  # noqa: E402

PROJECT = "natural-language-brain-alpha-harness"
SCOPE = "ksj12"
SUPABASE_REF = "sogpsiheygdwmhdlizvy"
PUBLIC_URL = f"https://{PROJECT}.vercel.app"
CLI = ["npx", "--yes", "vercel@60.1.3"]
MIGRATION = ROOT / "supabase/migrations/202609280005_gpt_usage_reset.sql"


def run(args: list[str], *, value: str | None = None, timeout: int = 60) -> str:
    # No raw CLI output is reflected: upstream errors may contain credentials.
    result = subprocess.run(
        args, cwd=ROOT, input=value, text=True, capture_output=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError("명령 실행 실패: " + " ".join(args[:4]))
    return result.stdout


def environment() -> dict[str, str]:
    path = ROOT / ".env.local"
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("프로젝트의 일반 파일 .env.local을 준비하세요.")
    run(["git", "check-ignore", "-q", ".env.local"])
    # Disable dotenv interpolation so a key containing '$' stays literal.
    values = {k: v for k, v in dotenv_values(path, interpolate=False).items() if v is not None}
    for key in (
        "OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_PUBLISHABLE_KEY",
    ):
        if not values.get(key, "").strip():
            raise RuntimeError(f".env.local의 {key}에 값을 입력하세요.")
    if values.get("OPENAI_MODEL", OPENAI_MODEL) != OPENAI_MODEL:
        raise RuntimeError("지원 모델: gpt-5.4-mini. 모델 변경은 비용 정책 수정이 필요합니다.")
    if values.get("SUPABASE_URL", "").rstrip("/") != f"https://{SUPABASE_REF}.supabase.co":
        raise RuntimeError("기존 운영 Supabase 프로젝트와 URL이 다릅니다. 배포하지 않았습니다.")
    return values


def budget_ready(values: dict[str, str]) -> bool:
    response = httpx.post(
        f"https://{SUPABASE_REF}.supabase.co/rest/v1/rpc/brain_openai_budget_ready",
        headers={"apikey": values["SUPABASE_SECRET_KEY"]}, json={}, timeout=10,
    )
    if response.status_code == 404:
        return False
    if response.is_error:
        raise RuntimeError("Supabase 예산 설정 조회 실패. 인증 또는 DB 상태를 확인하세요.")
    try:
        data = response.json()
        return isinstance(data, dict) and data == {
            "migration": "202609280005", "allowanceKrw": 34, "limitKrw": 20000, "ready": True,
        }
    except ValueError:
        raise RuntimeError("Supabase 예산 설정 응답이 올바르지 않습니다.") from None


def migrate(values: dict[str, str]) -> None:
    token = os.getenv("SUPABASE_ACCESS_TOKEN") or values.get("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError(
            "DB 업그레이드가 필요합니다. Supabase SQL Editor에서 "
            "supabase/migrations/202609280005_gpt_usage_reset.sql을 1회 실행하거나, "
            "SUPABASE_ACCESS_TOKEN을 .env.local에 설정하세요. 배포하지 않았습니다."
        )
    response = httpx.post(
        f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/database/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": MIGRATION.read_text()}, timeout=30,
    )
    if response.is_error:
        raise RuntimeError("Supabase DB 업그레이드 실패. 배포하지 않았습니다.")
    if not budget_ready(values):
        raise RuntimeError("DB 업그레이드 후 예산 정책을 확인하지 못했습니다. 다시 실행하세요.")
    print("GPT 비용 집계 적용 완료 (최초 1회 초기화, 과거 기록 보존).", flush=True)


def vercel(*args: str, value: str | None = None, timeout: int = 60) -> str:
    return run([*CLI, *args, "--scope", SCOPE], value=value, timeout=timeout)


def check_link(*, required: bool = False) -> None:
    path = ROOT / ".vercel/project.json"
    if required and not path.is_file():
        raise RuntimeError("Vercel 프로젝트 연결 파일을 확인하지 못했습니다.")
    if path.is_file():
        data = json.loads(path.read_text())
        if data.get("projectName") != PROJECT:
            raise RuntimeError(".vercel/project.json이 다른 프로젝트를 가리킵니다.")


def deploy(values: dict[str, str]) -> None:
    check_link()
    vercel("link", "--yes", "--project", PROJECT)
    check_link(required=True)
    settings = {
        "APP_ENV": "production", "AUTH_MODE": "supabase", "HARNESS_PROVIDER": "openai",
        "OPENAI_MODEL": OPENAI_MODEL, "OPENAI_API_KEY": values["OPENAI_API_KEY"].strip(),
        "MODEL_TIMEOUT_SECONDS": "35", "MAX_CONCURRENT_JOBS": "20",
        "APP_PUBLIC_URL": PUBLIC_URL, "SUPABASE_URL": values["SUPABASE_URL"].rstrip("/"),
        "SUPABASE_PUBLISHABLE_KEY": values["SUPABASE_PUBLISHABLE_KEY"],
        "SUPABASE_SECRET_KEY": values["SUPABASE_SECRET_KEY"],
    }
    for name, value in settings.items():
        secret = name in {"OPENAI_API_KEY", "SUPABASE_SECRET_KEY"}
        vercel(
            "env", "add", name, "production", "--force", "--yes",
            "--sensitive" if secret else "--no-sensitive", value=value,
        )
    print("운영 환경변수 등록 완료. Vercel 배포 중…", flush=True)
    vercel("deploy", "--prod", "--yes", timeout=600)
    response = httpx.get(f"{PUBLIC_URL}/api/health", timeout=30)
    response.raise_for_status()
    data = response.json()
    if (
        data.get("provider") != "openai" or data.get("model") != OPENAI_MODEL
        or data.get("providerRevision") != diagnostic_runtime()["providerSourceSha256"]
    ):
        raise RuntimeError("배포 후 OpenAI 설정을 확인하지 못했습니다. 운영 상태를 확인하세요.")
    print(f"배포 완료: {PUBLIC_URL}", flush=True)
    print("관리자 연결 진단: /api/admin/provider-check (유료 생성 없음)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="조회만 수행; 배포/DB 변경 없음")
    args = parser.parse_args()
    values = environment()
    # Isolated provider setup; only the OpenAI-specific key is passed to the adapter.
    report = asyncio.run(OpenAIProvider(api_key=values["OPENAI_API_KEY"]).check_connection())
    if report["status"] != "ok":
        raise RuntimeError("OpenAI 키/모델 조회 실패: " + report.get("errorCode", "unknown"))
    print("OpenAI 키·모델 접근 확인 완료 (유료 생성 없음).", flush=True)
    ready = budget_ready(values)
    if args.check:
        print("DB 예산 정책: " + ("준비됨" if ready else "업그레이드 필요"), flush=True)
        check_link()
        return
    # Validate code before changing any production environment or database.
    run([sys.executable, "-m", "ruff", "check", "backend", "scripts/deploy_openai.py"])
    run([sys.executable, "-m", "pytest", "-q"], timeout=120)
    run(["node", "--test", "backend/tests/frontend_state.test.mjs"])
    check_link()
    try:
        vercel("whoami")
        vercel("project", "inspect", PROJECT)
    except RuntimeError:
        raise RuntimeError(
            "Vercel CLI 로그인이 필요합니다: npx --yes vercel@60.1.3 login"
        ) from None
    if not ready:
        migrate(values)
    deploy(values)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, httpx.HTTPError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        # Do not echo response bodies, subprocess output, key-bearing URLs or OS details.
        message = (
            str(exc) if isinstance(exc, RuntimeError)
            else "연결 또는 실행 실패. 설정을 확인하세요."
        )
        print(message, file=sys.stderr)
        sys.exit(1)
