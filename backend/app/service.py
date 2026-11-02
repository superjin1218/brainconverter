from __future__ import annotations

import asyncio
import os
import re
import uuid
from dataclasses import replace

from .brain_catalog import ACTIVE_CATALOG, CORE_FIELDS, select_fields
from .compiler import compile_fe, intent_mapping, source_guards, validate_compiled_fe
from .draft_compiler import DraftCompiler, compile_draft
from .intent_compiler import compile_intent
from .models import ConversionResponse, ConvertRequest, DraftIR, IntentIR, ValidationSummary
from .openai_policy import OPENAI_POLICY
from .prompts import BASE_SYSTEM_PROMPT
from .provider_types import SemanticProvider
from .settings import resolve_simulation_settings
from .strategy_guidance import strategy_guidance


class HarnessService:
    """One AI interpretation followed by deterministic validation and compilation."""

    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.job_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_JOBS", "20")))

    async def convert(self, request: ConvertRequest) -> ConversionResponse:
        settings, sources, warnings, unresolved = resolve_simulation_settings(
            request.strategy, request.settings
        )
        try:
            selection = select_fields(request.strategy, settings)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        while True:
            token = ACTIVE_CATALOG.set(selection)
            try:
                prompt = BASE_SYSTEM_PROMPT + selection.prompt()
                OPENAI_POLICY.payload(prompt, request.strategy)
                break
            except RuntimeError:
                # Reduce context before the one paid call, never increase budget
                # or discard explicitly requested fields to make the request fit.
                explicit = set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", request.strategy))
                removable = [name for name in selection.ids
                             if name not in explicit and name not in CORE_FIELDS]
                if not removable:
                    raise
                selection = replace(selection, ids=tuple(
                    name for name in selection.ids if name != removable[-1]
                ))
            finally:
                ACTIVE_CATALOG.reset(token)
        try:
            await asyncio.wait_for(self.job_semaphore.acquire(), timeout=0.1)
        except TimeoutError as exc:
            raise RuntimeError("요청이 많습니다. 잠시 후 다시 시도하세요.") from exc
        catalog_token = ACTIVE_CATALOG.set(selection)
        try:
            async with asyncio.timeout(42):
                result = await self.provider.interpret(prompt, request.strategy)
        except TimeoutError as exc:
            raise RuntimeError("변환 제한 시간을 초과했습니다. 잠시 후 다시 시도하세요.") from exc
        finally:
            ACTIVE_CATALOG.reset(catalog_token)
            self.job_semaphore.release()

        compile_token = ACTIVE_CATALOG.set(selection)
        try:
            return self._compile_result(request, result, settings, sources, warnings,
                                        unresolved, selection)
        finally:
            ACTIVE_CATALOG.reset(compile_token)

    def _compile_result(self, request, result, settings, sources, warnings, unresolved, selection):
        ir = result.ir
        guidance = {}
        if isinstance(ir, IntentIR):
            expression, errors, guidance = compile_intent(request.strategy, ir, settings)
            source_errors = list(errors)
        elif isinstance(ir, DraftIR):
            expression, errors, guidance = compile_draft(request.strategy, ir, settings)
            source_errors = list(errors)
        else:
            # Legacy test IR remains readable; production requests use IntentIR.
            source_errors = source_guards(request.strategy, ir)
            errors = list(source_errors)
            if ir.status != "ok":
                errors.append(f"전략 해석 상태가 {ir.status}입니다. 전략을 구체화해 주세요.")
            expression = None
            if not errors:
                try:
                    expression = compile_fe(ir)
                    compile_errors = validate_compiled_fe(request.strategy, ir, expression)
                    source_errors.extend(compile_errors)
                    errors.extend(compile_errors)
                except ValueError:
                    errors.append("현재 컴파일러로 표현할 수 없는 전략입니다.")
            if not errors:
                guidance = {
                    "intentMapping": intent_mapping(ir),
                    **strategy_guidance(request.strategy, ir, settings),
                }
        if unresolved:
            errors.append("지원하지 않거나 유효하지 않은 시뮬레이션 설정이 있습니다.")
        # Every route, including legacy fixtures, must cross the same catalog/type
        # boundary. Never let an older IR bypass metadata validation.
        if expression is not None and not errors:
            try:
                DraftCompiler(selection.catalog).compile(expression)
            except ValueError as exc:
                errors.append(str(exc))
        warnings.append(
            "필드 ID·자료형은 BRAIN 메타데이터 카탈로그를 기준으로 검사했습니다. "
            "현재 계정의 접근 권한과 BRAIN 실행 성공은 확인하지 않았습니다."
        )
        status = "REJECTED" if errors else "PASS"
        return ConversionResponse(
            requestId=str(uuid.uuid4()),
            status=status,
            fastExpression=expression if status == "PASS" else None,
            simulationSettings=settings,
            settingsSource=sources,
            strategyIR=ir,
            confidence=None,
            catalogRevision=selection.catalog.digest,
            catalogScope=selection.catalog.scope,
            validation=ValidationSummary(
                sourceRequirementsPreserved=not bool(source_errors or unresolved),
                compilePassed=not bool(errors),
                intentPlanChecked=not bool(source_errors) if isinstance(ir, IntentIR) else None,
                catalogFieldsChecked=not bool(errors) if expression is not None else None,
                fieldTypesChecked=not bool(errors) if expression is not None else None,
            ),
            warnings=[*warnings, *errors],
            unresolvedSettings=unresolved,
            provider=self.provider.name,
            usage={
                "inputTokens": result.input_tokens,
                "outputTokens": result.output_tokens,
                "costMicrousd": result.cost_microusd,
            },
            **(guidance if status == "PASS" else {}),
        )
