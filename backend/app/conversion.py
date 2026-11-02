"""Conversion orchestration and the lifecycle of an owned Supabase job."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .config import AppConfig
from .local_provider import require_local_conversion
from .membership import MembershipService, same_origin
from .models import ConversionResponse, ConvertRequest
from .openai_policy import OPENAI_POLICY
from .service import HarnessService

logger = logging.getLogger("uvicorn.error")


def pending_job(result: dict) -> JSONResponse:
    return JSONResponse(
        {
            "status": "queued" if result["state"] == "queued" else "processing",
            "queuePosition": result.get("queuePosition"),
        },
        status_code=202,
    )


class MemberJob:
    def __init__(
        self, membership: MembershipService, user_id: str, job_id: str, payload: ConvertRequest
    ) -> None:
        self._membership = membership
        self._identity = {"p_user_id": user_id, "p_request_id": job_id}
        self._reservation = {
            **self._identity,
            "p_request_hash": hashlib.sha256(payload.model_dump_json().encode()).hexdigest(),
        }

    async def reserve(self) -> ConversionResponse | JSONResponse | None:
        reserved = await self._membership.rpc(
            "brain_reserve",
            body=self._reservation,
            server=True,
        )
        state = reserved.get("state") if isinstance(reserved, dict) else None
        if state == "cached":
            return ConversionResponse.model_validate(reserved["result"])
        if state in {"running", "queued"}:
            return pending_job(reserved)
        if state != "reserved":
            raise HTTPException(
                429 if state == "limited" else 403 if state == "denied" else 409,
                "이용 한도 또는 이전 요청 상태를 확인하세요. 잠시 후 다시 시도하세요.",
            )
        return None

    async def reserve_budget(self) -> None:
        body = {**self._reservation, "p_allowance_krw": OPENAI_POLICY.budget_allowance_krw}
        budget = await self._membership.rpc(
            "brain_budget_reserve",
            body=body,
            server=True,
        )
        if isinstance(budget, dict) and budget.get("state") == "reserved":
            return
        exhausted = isinstance(budget, dict) and budget.get("state") == "budget_exhausted"
        raise HTTPException(
            402 if exhausted else 503,
            "누적 AI 비용 한도(20,000원)에 도달해 변환이 중지됐습니다."
            if exhausted
            else "AI 비용 한도를 확인하지 못해 변환을 실행하지 않았습니다.",
        )

    async def finish(self, result: ConversionResponse | None) -> None:
        saved = await self._membership.rpc(
            "brain_finish",
            body={
                **self._identity,
                "p_result": result.model_dump() if result is not None else None,
                "p_failed": result is None,
            },
            server=True,
        )
        if result is not None and (not isinstance(saved, dict) or saved.get("saved") is not True):
            raise HTTPException(503, "결과를 보관하지 못했습니다.")


class ConversionCoordinator:
    def __init__(
        self,
        config: AppConfig,
        membership: MembershipService,
        state,
        service: Callable[[], HarnessService],
    ) -> None:
        self._config, self._membership, self._state, self._service = (
            config,
            membership,
            state,
            service,
        )

    async def convert(self, payload: ConvertRequest, request: Request):
        started = time.monotonic()
        member = None
        if self._config.auth_mode == "supabase":
            same_origin(request, self._config.public_url)
            member = await self._membership.identify(request, approved=True)
        elif self._config.auth_mode == "none":
            require_local_conversion(request)
        if not self._config.conversions_enabled:
            raise HTTPException(
                503, "현재 AI 변환은 준비 중입니다. 회원가입과 로그인은 이용할 수 있습니다."
            )
        self._state.active_conversions += 1
        owned_job = None
        try:
            service = self._service()
            expected = request.headers.get("x-expected-provider")
            if (
                self._config.environment == "development"
                and expected is not None
                and expected != service.provider.name
            ):
                raise HTTPException(
                    409,
                    (
                        "AI 연결 상태가 변경됐습니다. 설정에서 연결 상태를 확인한 뒤 "
                        "다시 변환하세요. 이번 변환은 실행하지 않았습니다."
                    ),
                )
            if member:
                try:
                    job_id = str(UUID(request.headers.get("idempotency-key", "")))
                except ValueError:
                    raise HTTPException(400, "유효한 요청 ID가 필요합니다.") from None
                candidate = MemberJob(self._membership, member["id"], job_id, payload)
                existing = await candidate.reserve()
                if existing is not None:
                    return existing
                # Only the request that acquired the slot may finish or fail this job.
                owned_job = candidate
                if service.provider.name == "openai":
                    await owned_job.reserve_budget()
            result = await service.convert(payload)
            if owned_job is not None:
                try:
                    await owned_job.finish(result)
                except HTTPException:
                    logger.warning("conversion result cache failed")
                    result.warnings.append(
                        "결과 보관에 실패했습니다. 생성된 코드를 지금 복사하세요."
                    )
            logger.info(
                "conversion id=%s status=%s elapsed_ms=%d "
                "input_tokens=%d output_tokens=%d cost_microusd=%d",
                result.requestId,
                result.status,
                int((time.monotonic() - started) * 1000),
                result.usage["inputTokens"],
                result.usage["outputTokens"],
                result.usage["costMicrousd"],
            )
            return result
        except (RuntimeError, HTTPException) as exc:
            if owned_job is not None:
                try:
                    await owned_job.finish(None)
                except HTTPException:
                    logger.warning("conversion ledger finish failed")
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        finally:
            self._state.active_conversions -= 1
