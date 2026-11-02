"""Render an administrator's sanitized provider metadata without client-side scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from html import escape
from pathlib import Path

import httpx


def diagnostic_runtime() -> dict:
    """Return comparable runtime facts, never environment values containing secrets."""
    region = os.getenv("VERCEL_REGION", "")
    commit = os.getenv("VERCEL_GIT_COMMIT_SHA", "")
    try:
        digest = hashlib.sha256()
        # Include interpretation and compilation so deployment checks detect rule changes too.
        for name in (
            "provider.py",
            "chat_provider.py",
            "openai_provider.py",
            "openai_policy.py",
            "response_schema.py",
            "provider_config.py",
            "provider_types.py",
            "provider_errors.py",
            "models.py",
            "data_fields.py",
            "catalog_context.py",
            "catalog_embeddings.py",
            "field_catalog.py",
            "hypotheses.py",
            "compiler.py",
            "draft_compiler.py",
            "intent_compiler.py",
            "service.py",
            "strategy_guidance.py",
            "prompts.py",
            "skills/brain-strategy/SKILL.md",
        ):
            digest.update(name.encode() + b"\0")
            digest.update((Path(__file__).parent / name).read_bytes())
        provider_hash = digest.hexdigest()
    except OSError:
        provider_hash = None
    return {
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "httpx": httpx.__version__,
        "region": region if re.fullmatch(r"[a-z]{3}[0-9]", region) else None,
        "commit": commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None,
        "providerSourceSha256": provider_hash,
        "proxyConfigured": any(
            os.getenv(name, "").strip()
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            )
        ),
    }


def diagnostic_html(result: dict) -> str:
    report = escape(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>AI 연결 진단</title></head><body>"
        "<main><h1>AI 연결 진단</h1>"
        "<p>이 조회는 AI 변환을 실행하지 않으며 변환 횟수와 예산을 예약하지 않습니다.</p>"
        "<p>modelAvailable은 선택한 모델에 접근할 수 있는지 표시합니다. "
        "실제 생성 성공을 뜻하지 않습니다.</p>"
        "<p>keyFingerprint는 서버와 로컬에 저장된 키를 비교하는 ID입니다. "
        "키 원문이나 인증에 사용할 수 있는 값은 제공하지 않습니다.</p>"
        f"<pre>{report}</pre>"
        '<p><a href="/">변환 화면으로 돌아가기</a></p></main></body></html>'
    )
