"""Source-grounded measurements with explicit preferences; the server builds the score."""

from __future__ import annotations

import ast
import re

from .brain_catalog import get_catalog
from .draft_compiler import GROUPS, DraftCompiler, compile_draft, expression_signature
from .models import DraftIR, IntentIR, IntentMetric

RATIO_CONCEPTS = {
    "총자산": ("assets", "total"),
    "총부채": ("liabilities", "total"),
    "자기자본": ("equity",),
    "매출": ("sales", "revenue"),
    "순이익": ("net", "income"),
}


def _ratio_source_error(metric: IntentMetric) -> str | None:
    if metric.operation != "ratio":
        return None
    terms = "|".join(RATIO_CONCEPTS)
    match = re.search(f"({terms})\\s*대비\\s*({terms})", metric.source)
    if match is None:
        return None

    def matches(identifier, concept):
        description = get_catalog().field(identifier).description.lower()
        words = RATIO_CONCEPTS[concept]
        if concept == "매출":
            return any(word in description for word in words)
        return all(word in description for word in words) and not (
            concept in {"총자산", "총부채"} and "current" in description
        )

    denominator, numerator = match.groups()
    if not matches(metric.field, numerator) or not matches(metric.reference, denominator):
        return "'A 대비 B'는 B/A입니다. 분자·분모의 필드 설명과 요청한 재무 지표가 다릅니다."
    return None


def _field_value(identifier: str, aggregation: str) -> str:
    field = get_catalog().field(identifier)
    if field.type == "VECTOR":
        if aggregation not in {"avg", "sum"}:
            raise ValueError(f"VECTOR 필드는 avg 또는 sum 집계가 필요합니다: {identifier}")
        return f"vec_{aggregation}({identifier})"
    if field.type != "MATRIX" or aggregation != "none":
        raise ValueError(f"필드 자료형과 집계 방법이 맞지 않습니다: {identifier}")
    return identifier


def measurement(metric: IntentMetric) -> str:
    if metric.operation == "expression":
        compiler = DraftCompiler()
        result = compiler.compile(metric.formula)
        if metric.field not in compiler.fields:
            raise ValueError("복합 측정식에 선언한 주 데이터 필드가 없습니다.")
        if compiler.operators & {"rank", "group_rank", "group_neutralize", "trade_when", "if_else"}:
            raise ValueError("복합 측정식 안에 점수 순위·조건부 점수를 숨길 수 없습니다.")
        return result.code
    field = _field_value(metric.field, metric.aggregation)
    days = metric.window
    other = (_field_value(metric.reference, metric.referenceAggregation)
             if metric.reference is not None else None)
    if metric.operation == "raw":
        return field
    if metric.operation == "return":
        return f"({field} / ts_delay({field}, {days}) - 1)"
    if metric.operation in {"delta", "mean", "std_dev"}:
        return f"ts_{metric.operation}({field}, {days})"
    if metric.operation == "relative_mean":
        return f"({field} / ts_mean({field}, {days}) - 1)"
    if metric.operation == "ratio":
        return f"({field} / {other} - 1)"
    if metric.operation == "difference":
        return f"({field} - {other})"
    if metric.operation == "range_position":
        return f"(({field} - low) / (high - low))"
    if metric.operation == "correlation":
        return f"ts_corr({field}, {other}, {days})"
    raise ValueError("지원하지 않는 측정 방법입니다.")


def score_expression(metrics: list[IntentMetric]) -> str:
    terms = []
    for metric in metrics:
        value = measurement(metric)
        ranked = f"rank({value})" if metric.group == "none" else (
            f"group_rank({value}, {metric.group})"
        )
        term = ranked if metric.preference == "higher" else f"(1 - {ranked})"
        if metric.weight != 1:
            term = f"({metric.weight:g} * {term})"
        terms.append(term)
    return " + ".join(terms)


def source_evidence_errors(strategy: str, ir: IntentIR) -> list[str]:
    errors, used = [], []
    for component in [*ir.metrics, *([ir.entry] if ir.entry else [])]:
        quote = component.source.strip()
        if len(quote) < 2:
            errors.append("측정값 또는 거래 조건의 근거 문구가 비어 있거나 너무 짧습니다.")
            continue
        positions = [m.span() for m in re.finditer(re.escape(quote), strategy)]
        available = [p for p in positions if not any(p[0] < b and a < p[1] for a, b in used)]
        if not positions:
            errors.append("측정값 또는 거래 조건의 근거가 원문에 없습니다.")
        elif not available:
            errors.append("같은 원문 근거를 중복 사용해 추가 신호를 만들 수 없습니다.")
        else:
            used.append(available[0])
    signatures = [
        (m.operation, m.field, m.window, m.reference, m.group) for m in ir.metrics
    ]
    if len(set(signatures)) != len(signatures):
        errors.append("같은 측정값을 중복 또는 상반된 방향으로 사용했습니다.")
    if re.search(r"(?:같은|동일한?|동종)\s*(?:업종|산업)|industry.relative", strategy, re.I):
        if not any(m.group != "none" for m in ir.metrics):
            errors.append("명시한 동종업계 비교가 빠졌습니다.")
    for match in re.finditer(
        r"[^.。\n]*(?:뺀|빼고|차이를)[^.。\n]*(?:나눈|나눠|나누어)[^.。\n]*", strategy,
    ):
        # One explicitly chained arithmetic request must not become independent
        # ranked preferences. This reproduces an observed live-model failure.
        components = [m for m in ir.metrics if m.source.strip() in match.group()]
        if len(components) != 1 or components[0].operation != "expression":
            errors.append("차이를 구한 뒤 나누는 계산은 하나의 복합 측정식으로 보존해야 합니다.")
    return errors


def _rank(values: list[float], groups: list[int]) -> list[float]:
    result = []
    for value, group in zip(values, groups, strict=True):
        peers = [v for v, g in zip(values, groups, strict=True) if g == group]
        # Average tie ranks on [0,1]. Only ordering, not BRAIN execution, is tested.
        rank = sum(v < value for v in peers) + (sum(v == value for v in peers) - 1) / 2
        result.append(rank / (len(peers) - 1) if len(peers) > 1 else 0.5)
    return result


def preference_behavior_errors(expression: str, metrics: list[IntentMetric]) -> list[str]:
    """Independent counterfactual interpreter over declared measurement values; no eval.

    Hold other measurements fixed, increase one measurement within each peer group,
    and check the *compiled* score's order. This checks plan-to-code direction,
    not whether an arbitrary natural-language interpretation is correct.
    """
    proxies = [expression_signature(ast.parse(measurement(m), mode="eval").body) for m in metrics]
    tree = ast.parse(expression, mode="eval").body

    def evaluate(node, active):
        signature = expression_signature(node)
        if signature in proxies:
            return [1., 2., 3., 1., 2., 3.] if proxies.index(signature) == active else [2.] * 6
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return [float(node.value)] * 6
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left, active), evaluate(node.right, active)
            if isinstance(node.op, ast.Add):
                return [a + b for a, b in zip(left, right, strict=True)]
            if isinstance(node.op, ast.Sub):
                return [a - b for a, b in zip(left, right, strict=True)]
            if isinstance(node.op, ast.Mult):
                return [a * b for a, b in zip(left, right, strict=True)]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "rank" and len(node.args) == 1:
                return _rank(evaluate(node.args[0], active), [0] * 6)
            if node.func.id == "group_rank" and len(node.args) == 2:
                return _rank(evaluate(node.args[0], active), [0, 0, 0, 1, 1, 1])
        raise ValueError("계획에 없는 점수 연산이 있습니다.")

    errors = []
    for index, metric in enumerate(metrics):
        try:
            scores = evaluate(tree, index)
            expected = scores[0] < scores[1] < scores[2] if metric.preference == "higher" else (
                scores[0] > scores[1] > scores[2]
            )
            if not expected:
                errors.append(f"측정값 {index + 1}의 선호 방향과 코드의 점수 방향이 다릅니다.")
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            errors.append("선호 방향 검사에서 계획에 없는 점수 연산을 발견했습니다.")
    return errors


def compile_intent(strategy: str, ir: IntentIR, settings: dict):
    if ir.status != "ok":
        return None, [ir.reason or "현재 데이터로 가설을 표현하지 못했습니다."], {}
    if not ir.metrics:
        return None, ["가설을 측정할 기준이 없습니다."], {}
    try:
        get_catalog().check_scope(settings)
        for component in ir.metrics:
            compiler = DraftCompiler()
            compiler.compile(measurement(component))
            if error := _ratio_source_error(component):
                raise ValueError(error)
            if re.search(r"뉴스|(?<![a-z])news(?![a-z])", component.source, re.I):
                if not any(get_catalog().field(name).category == "news"
                           or "news" in get_catalog().field(name).description.lower()
                           for name in compiler.fields):
                    raise ValueError(
                        "뉴스 신호를 뉴스 근거가 없는 다른 데이터로 대체할 수 없습니다."
                    )
    except ValueError as exc:
        return None, [str(exc)], {}
    errors = source_evidence_errors(strategy, ir)
    if errors:
        return None, errors, {}
    score = score_expression(ir.metrics)
    errors = preference_behavior_errors(score, ir.metrics)
    if errors:
        return None, errors, {}
    explanation, assumptions, mapping = [], [], []
    for metric in ir.metrics:
        value = measurement(metric)
        meaning = DraftCompiler().compile(value).meaning
        direction = "높을수록" if metric.preference == "higher" else "낮을수록"
        group = "전체 종목" if metric.group == "none" else f"같은 {GROUPS[metric.group]}의 종목"
        explanation.append(f"‘{metric.source}’: {group}끼리 비교해 {meaning} 값이 {direction} "
                           "높은 점수를 줍니다.")
        assumptions.append(f"측정 기준: {meaning}; 상대 가중치 {metric.weight:g}.")
        mapping.append({"requirement": f"{metric.source} → {direction} 선호", "expression": value})
    if ir.entry:
        # Parse the argument on its own so it cannot add calls or score terms.
        try:
            condition = DraftCompiler().compile(ir.entry.condition, expected_kind="condition")
        except ValueError as exc:
            return None, [str(exc)], {}
        expression = f"trade_when({condition.code}, ({score}), -1)"
    else:
        expression = score
    # Reuse the typed expression boundary and explicit source-condition checks.
    render_ir = DraftIR(
        schemaVersion="draft-v2", status="ok", hypothesis="입력에 근거한 전략 초안입니다.",
        expression=expression, assumptions=assumptions,
        improvementSuggestions=ir.improvementSuggestions, refinementOptions=ir.refinementOptions,
        reason="",
    )
    code, errors, guidance = compile_draft(strategy, render_ir, settings)
    if not errors:
        guidance["strategyExplanation"] = (
            "\n".join(explanation) + "\n" + guidance["strategyExplanation"]
        )
        guidance["intentMapping"] = mapping + guidance["intentMapping"]
    return code, errors, guidance
