"""Recheck stored expressions without paid inference or changing quota history."""

from .brain_catalog import get_catalog
from .draft_compiler import DraftCompiler
from .models import ConversionResponse


def recheck_cached(result: ConversionResponse) -> ConversionResponse:
    if result.status != "PASS":
        return result
    checked = result.model_copy(deep=True)
    try:
        catalog = get_catalog()
        catalog.check_scope(result.simulationSettings)
        DraftCompiler(catalog).compile(result.fastExpression or "")
    except ValueError as exc:
        checked.status, checked.fastExpression = "REJECTED", None
        checked.validation.compilePassed = False
        checked.validation.catalogFieldsChecked = False
        checked.validation.fieldTypesChecked = False
        checked.validation.brainExecutionChecked = None
        checked.warnings.append(f"저장된 결과가 현재 BRAIN 검사에 실패했습니다: {exc}")
        checked.strategyExplanation = None
        checked.refinementOptions, checked.improvementSuggestions = [], []
        checked.intentMapping, checked.assumptions = [], []
        return checked
    checked.validation.catalogFieldsChecked = True
    checked.validation.fieldTypesChecked = True
    checked.validation.brainExecutionChecked = None
    if checked.catalogRevision != catalog.digest:
        checked.warnings.append("저장된 표현식을 현재 BRAIN 카탈로그로 다시 검사했습니다.")
        checked.validation.intentPlanChecked = None
    checked.catalogRevision, checked.catalogScope = catalog.digest, catalog.scope
    return checked
