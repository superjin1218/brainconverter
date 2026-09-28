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
    "not_found": "AI API 경로 또는 리소스를 찾을 수 없습니다. 서버 연결 설정을 확인하세요.",
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

# Do not log arbitrary upstream strings: they may contain prompts or credentials.
SAFE_UPSTREAM_CODES = frozenset({
    "invalid_api_key", "billing_not_configured", "model_not_found", "file_not_found",
    "credit_balance_exhausted", "insufficient_credits", "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded", "organization_usage_limit_exceeded", "insufficient_quota",
    "ip_not_authorized", "rate_limit_exceeded", "server_shutting_down", "service_overloaded",
    "backend_unavailable", "payload_too_large", "gateway_timeout", "unsupported_parameter",
})


class ProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code if code in MESSAGES else "invalid_response"
        self.http_status: int | None = None
        self.upstream_code = "none"
        self.response_shape = "none"
        super().__init__(MESSAGES[self.code])


def diagnostic_failure(exc: Exception, http_status: int | None) -> dict:
    if isinstance(exc, ProviderError):
        failure = exc
    elif isinstance(exc, httpx.TimeoutException):
        failure = ProviderError("timeout")
    else:
        failure = ProviderError("connection")
    return {
        "status": "failed",
        "httpStatus": failure.http_status or http_status,
        "errorCode": failure.code,
        "upstreamCode": failure.upstream_code,
        "responseShape": failure.response_shape,
    }



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

    def failure(kind: str) -> ProviderError:
        result = ProviderError(kind)
        result.http_status = response.status_code
        result.upstream_code = (
            code if isinstance(code, str) and code in SAFE_UPSTREAM_CODES
            else "none" if code is None else "other"
        )
        result.response_shape = (
            "empty" if not response.content else "json_error" if error else "other"
        )
        return result

    if code in ("credit_balance_exhausted", "insufficient_credits") or response.status_code == 402:
        return failure("credits")
    if code in ("organization_spend_limit_exceeded", "project_spend_limit_exceeded"):
        return failure("spend_limit")
    if code == "organization_usage_limit_exceeded":
        return failure("usage_limit")
    if code == "insufficient_quota" or error_type == "insufficient_quota":
        return failure("quota")
    if code == "ip_not_authorized":
        return failure("ip_restricted")
    if code == "model_not_found":
        return failure("model_access")
    if response.status_code == 404:
        return failure("not_found")
    if response.status_code == 401:
        return failure("authentication")
    if response.status_code == 403:
        return failure("permission")
    if response.status_code == 429:
        # Do not amplify throttling with automatic retries.
        return failure("rate_limit")
    if response.status_code >= 500:
        return failure("upstream")
    return failure("invalid_request")
