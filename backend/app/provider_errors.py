"""Safe, actionable provider failures without upstream messages or credentials."""

from __future__ import annotations

import httpx

MESSAGES = {
    "authentication": "AI 서비스 인증에 실패했습니다. API 키와 프로젝트 접근 권한을 확인하세요.",
    "permission": "AI 서비스 접근이 거부됐습니다. 키 권한과 프로젝트·지역 접근 설정을 확인하세요.",
    "ip_restricted": (
        "AI 서비스가 현재 IP의 접근을 허용하지 않습니다. 프로젝트 IP 설정을 확인하세요."
    ),
    "model_access": "설정된 모델에 접근할 수 없습니다. 프로젝트의 모델 사용 권한을 확인하세요.",
    "credits": "AI 서비스 API 크레딧이 소진됐습니다. API 결제 페이지에서 잔액을 확인하세요.",
    "spend_limit": "AI 서비스 지출 한도에 도달했습니다. 프로젝트·조직의 한도를 확인하세요.",
    "usage_limit": "AI 서비스 API 사용 한도에 도달했습니다. 계정의 사용 한도를 확인하세요.",
    "quota": "AI 서비스 API 잔액 또는 사용 한도가 부족합니다. API 결제·한도를 확인하세요.",
    "rate_limit": "AI 서비스 요청 속도 한도에 걸렸습니다. 잠시 기다린 뒤 다시 시도하세요.",
    "invalid_request": (
        "AI 서비스가 요청 형식을 거부했습니다. 프로그램의 모델 요청 설정을 점검해야 합니다."
    ),
    "upstream": "AI 서비스가 일시적으로 응답하지 못했습니다. 잠시 후 다시 시도하세요.",
    "connection": "AI 서비스 서버에 연결하지 못했습니다. 네트워크·프록시·인증서 설정을 확인하세요.",
    "timeout": "AI 서비스 응답 대기시간을 초과했습니다. 잠시 후 다시 시도하세요.",
    "output_limit": "AI 응답이 길이 제한으로 잘렸습니다. 전략을 간단하게 나눠 주세요.",
    "refusal": "AI가 이 전략의 해석을 거절했습니다. 전략 내용을 확인해 주세요.",
    "invalid_response": "AI 응답이 코드 변환 형식에 맞지 않았습니다. 전략을 명확하게 적어 주세요.",
}


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code if code in MESSAGES else "invalid_response"
        self.retryable = retryable
        super().__init__(MESSAGES[self.code])


def http_provider_error(response: httpx.Response) -> ProviderError:
    # Only inspect documented codes/types; never expose the raw provider message.
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        if not isinstance(error, dict):
            error = {}
    except ValueError:
        error = {}
    code, error_type = error.get("code"), error.get("type")
    if code in ("credit_balance_exhausted", "insufficient_credits") or response.status_code == 402:
        return ProviderError("credits")
    if code in ("organization_spend_limit_exceeded", "project_spend_limit_exceeded"):
        return ProviderError("spend_limit")
    if code == "organization_usage_limit_exceeded":
        return ProviderError("usage_limit")
    if code == "insufficient_quota" or error_type == "insufficient_quota":
        return ProviderError("quota")
    if code == "ip_not_authorized":
        return ProviderError("ip_restricted")
    if code == "model_not_found" or response.status_code == 404:
        return ProviderError("model_access")
    if response.status_code == 401:
        return ProviderError("authentication")
    if response.status_code == 403:
        return ProviderError("permission")
    if response.status_code == 429:
        # Do not amplify throttling with automatic retries.
        return ProviderError("rate_limit")
    if response.status_code >= 500:
        return ProviderError("upstream", retryable=True)
    return ProviderError("invalid_request")
