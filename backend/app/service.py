from __future__ import annotations

import asyncio
import os
import uuid

from .catalog_context import catalog_context
from .catalog_embeddings import CatalogEmbeddings, embedding_cost
from .compiler import compile_fe, intent_mapping, source_guards, validate_compiled_fe
from .draft_compiler import DraftCompiler, compile_draft
from .field_catalog import load_catalog, scope_key
from .intent_compiler import compile_intent
from .models import ConversionResponse, ConvertRequest, DraftIR, IntentIR, ValidationSummary
from .openai_policy import OPENAI_POLICY
from .prompts import BASE_SYSTEM_PROMPT, prepare_catalog_prompt
from .provider_types import SemanticProvider
from .settings import resolve_simulation_settings
from .strategy_guidance import strategy_guidance


class HarnessService:
    """One AI interpretation followed by deterministic validation and compilation."""

    def __init__(self, provider: SemanticProvider, *, catalog=None) -> None:
        self.provider = provider
        self.catalog = catalog
        self.job_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_JOBS", "20")))

    async def convert(self, request: ConvertRequest) -> ConversionResponse:
        try:
            await asyncio.wait_for(self.job_semaphore.acquire(), timeout=0.1)
        except TimeoutError as exc:
            raise RuntimeError("요청이 많습니다. 잠시 후 다시 시도하세요.") from exc
        try:
            async with asyncio.timeout(75):
                return await self._convert_with_catalog(request)
        except TimeoutError as exc:
            raise RuntimeError("변환 제한 시간을 초과했습니다. 잠시 후 다시 시도하세요.") from exc
        finally:
            self.job_semaphore.release()

    async def _convert_with_catalog(self, request):
        resolved = resolve_simulation_settings(request.strategy, request.settings)
        catalog = self.validate_catalog(request)
        if catalog is None:
            # Explicit development mock mode stays offline and never contacts OpenAI/WQ.
            return await self._convert(request, BASE_SYSTEM_PROMPT, resolved)
        encoder = CatalogEmbeddings(api_key=getattr(self.provider, "api_key", None))
        selected = await asyncio.to_thread(
            catalog.select, request.strategy, resolved[0], encoder=encoder,
        )
        generation_budget = (OPENAI_POLICY.reserve_microusd
                             - selected.search_max_cost_microusd - embedding_cost(8000))
        prompt, fields = prepare_catalog_prompt(
            request.strategy, selected.fields, catalog.operators, catalog.catalog_id,
            generation_budget=generation_budget,
        )
        with catalog_context(fields, catalog.operators, catalog.catalog_id,
                             generation_budget_microusd=generation_budget,
                             source_strategy=request.strategy):
            result = await self._convert(request, prompt, resolved)
        result.usage["embeddingInputTokens"] = selected.embedding_input_tokens
        result.usage["searchInputTokens"] = selected.search_input_tokens
        result.usage["searchOutputTokens"] = selected.search_output_tokens
        result.usage["inputTokens"] += selected.search_input_tokens
        result.usage["outputTokens"] += selected.search_output_tokens
        result.usage["costMicrousd"] += (embedding_cost(selected.embedding_input_tokens)
                                        + selected.search_cost_microusd)
        return result

    def validate_catalog(self, request):
        from .mock_provider import MockSemanticProvider

        if self.catalog is None and isinstance(self.provider, MockSemanticProvider):
            return None
        settings = resolve_simulation_settings(request.strategy, request.settings)[0]
        catalog = self.catalog if self.catalog is not None else load_catalog(scope_key(settings))
        catalog.ensure_scope(settings)
        return catalog

    async def _convert(self, request, prompt, resolved) -> ConversionResponse:
        result = await self.provider.interpret(prompt, request.strategy)
        ir = result.ir
        settings, sources, warnings, unresolved = resolved
        guidance = {}
        if isinstance(ir, IntentIR):
            try:
                expression, errors, guidance = compile_intent(request.strategy, ir, settings)
            except ValueError as exc:
                expression, errors, guidance = None, [str(exc)], {}
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
                    # Cached/test legacy IR must respect the same catalog boundary.
                    compiled = DraftCompiler().compile(expression)
                    if "vec_avg(" in compiled.code:
                        expression = compiled.code
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
        status = "REJECTED" if errors else "PASS"
        return ConversionResponse(
            requestId=str(uuid.uuid4()),
            status=status,
            fastExpression=expression if status == "PASS" else None,
            simulationSettings=settings,
            settingsSource=sources,
            strategyIR=ir,
            confidence=None,
            validation=ValidationSummary(
                sourceRequirementsPreserved=not bool(source_errors or unresolved),
                compilePassed=not bool(errors),
                intentPlanChecked=not bool(source_errors) if isinstance(ir, IntentIR) else None,
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
