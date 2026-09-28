"""Render an administrator's sanitized provider metadata without client-side scripts."""

from __future__ import annotations

import json
from html import escape


def diagnostic_html(result: dict) -> str:
    report = escape(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>AI 연결 진단</title></head><body>'
        '<main><h1>AI 연결 진단</h1>'
        '<p>이 조회는 AI 변환을 실행하지 않으며 변환 횟수와 예산을 예약하지 않습니다.</p>'
        '<p>modelAvailable은 모델 목록에 Contributor가 포함되는지 표시합니다. '
        '실제 생성 성공을 뜻하지 않습니다.</p>'
        '<p>keyFingerprint는 서버와 로컬에 저장된 키를 비교하는 ID입니다. '
        '키 원문이나 인증에 사용할 수 있는 값은 제공하지 않습니다.</p>'
        f'<pre>{report}</pre>'
        '<p><a href="/">변환 화면으로 돌아가기</a></p></main></body></html>'
    )
