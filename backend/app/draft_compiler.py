"""Compile an AI-designed expression through a small, typed allowlist. Never eval it."""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .brain_catalog import BrainCatalog, get_catalog
from .compiler import validate_source_numbers
from .models import DraftIR

FIELDS = {
    "open": "시가", "high": "고가", "low": "저가", "close": "종가",
    "volume": "거래량", "returns": "일간 수익률",
}
GROUPS = {"industry": "산업", "sector": "섹터", "subindustry": "하위 산업"}
TIME_FUNCTIONS = {
    "ts_delay": "이전 값", "ts_delta": "변화량", "ts_mean": "평균",
    "ts_sum": "합계", "ts_std_dev": "표준편차(변동성)",
    "ts_min": "최솟값", "ts_max": "최댓값", "ts_rank": "기간 내 순위",
    "ts_backfill": "결측값 이전 관측치 채우기",
}
BINARY = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
COMPARISONS = {ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<="}


@dataclass(frozen=True)
class CompiledNode:
    code: str
    meaning: str
    kind: str  # number, series, condition or group


def _numeric(node: CompiledNode) -> bool:
    return node.kind in {"number", "series"}


def expression_signature(node: ast.AST):
    """Equivalence for parentheses, scalar formatting and commutative operands only."""
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return ("number", str(Decimal(str(node.value)).normalize()))
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        args = sorted((expression_signature(node.left), expression_signature(node.right)), key=str)
        return (type(node.op).__name__, *args)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = expression_signature(node.left), expression_signature(node.comparators[0])
        op = type(node.ops[0]).__name__
        if op in {"Lt", "LtE"}:
            left, right, op = right, left, {"Lt": "Gt", "LtE": "GtE"}[op]
        return (op, left, right)
    return (type(node).__name__, *(
        (key, tuple(expression_signature(v) if isinstance(v, ast.AST) else v for v in value))
        if isinstance(value, list) else
        (key, expression_signature(value) if isinstance(value, ast.AST) else value)
        for key, value in ast.iter_fields(node)
    ))


class DraftCompiler:
    def __init__(self, catalog: BrainCatalog | None = None):
        self.catalog = catalog if catalog is not None else get_catalog()
        self.steps: list[dict[str, str]] = []
        self.windows: set[int] = set()
        self.fields: set[str] = set()
        self.operators: set[str] = set()
        self.tree: ast.Expression | None = None

    def compile(
        self, expression: str, *, expected_kind: Literal["series", "condition"] = "series"
    ) -> CompiledNode:
        try:
            self.tree = ast.parse(expression.strip(), mode="eval")
            if sum(1 for _ in ast.walk(self.tree)) > 180:
                raise ValueError("전략 식이 너무 복잡합니다.")
            result = self._node(self.tree.body, 0)
        except (SyntaxError, RecursionError) as exc:
            raise ValueError("전략 식의 구문을 해석할 수 없습니다.") from exc
        if result.kind != expected_kind:
            raise ValueError(
                "거래 조건에는 비교식이 필요합니다." if expected_kind == "condition"
                else "종목별 점수를 계산하는 식이 필요합니다."
            )
        return result

    def _node(self, node: ast.AST, depth: int) -> CompiledNode:
        if depth > 16:
            raise ValueError("전략 식의 중첩이 너무 깊습니다.")
        if isinstance(node, ast.Name):
            field = self.catalog.field(node.id)
            self.fields.add(node.id)
            kind = {"MATRIX": "series", "VECTOR": "vector", "GROUP": "group"}.get(field.type)
            if kind is None:
                raise ValueError(f"숫자 신호에 사용할 수 없는 필드 자료형입니다: {node.id}")
            return CompiledNode(node.id, FIELDS.get(node.id, GROUPS.get(node.id, node.id)), kind)
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            if abs(node.value) > 1_000_000 or not math.isfinite(node.value):
                raise ValueError("숫자가 허용 범위를 벗어났습니다.")
            value = str(int(node.value)) if int(node.value) == node.value else str(node.value)
            return CompiledNode(value, value, "number")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = self._node(node.operand, depth + 1)
            if not _numeric(value):
                raise ValueError("부호를 적용할 수 없는 값입니다.")
            code = f"-{value.code}" if value.kind == "number" else f"-({value.code})"
            return CompiledNode(code, f"({value.meaning})의 부호 반전", value.kind)
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            left, right = self._node(node.left, depth + 1), self._node(node.right, depth + 1)
            if not _numeric(left) or not _numeric(right):
                raise ValueError("산술 연산에는 숫자나 종목별 데이터가 필요합니다.")
            # Avoid scalar arithmetic hiding invalid windows or a literal zero denominator.
            if left.kind == right.kind == "number":
                raise ValueError("상수 계산은 계산된 숫자로 표시해야 합니다.")
            if isinstance(node.op, ast.Div) and right.code in {"0", "-0"}:
                raise ValueError("0으로 나눌 수 없습니다.")
            sign = BINARY[type(node.op)]
            return CompiledNode(
                f"({left.code} {sign} {right.code})",
                f"({left.meaning} {sign} {right.meaning})", "series",
            )
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left = self._node(node.left, depth + 1)
            right = self._node(node.comparators[0], depth + 1)
            sign = COMPARISONS.get(type(node.ops[0]))
            if not sign or not _numeric(left) or not _numeric(right):
                raise ValueError("지원하지 않는 비교 조건입니다.")
            return CompiledNode(
                f"{left.code} {sign} {right.code}",
                f"{left.meaning} {sign} {right.meaning}", "condition",
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            args = [self._node(arg, depth + 1) for arg in node.args]
            result = self._call(name, args)
            self.steps.append({"requirement": result.meaning, "expression": result.code})
            return result
        raise ValueError("허용되지 않은 데이터·연산·구문이 있습니다.")

    def _window(self, arg: CompiledNode) -> int:
        if arg.kind != "number" or not arg.code.isdigit() or not 1 <= int(arg.code) <= 1000:
            raise ValueError("관찰 기간은 1~1000거래일 정수여야 합니다.")
        days = int(arg.code)
        self.windows.add(days)
        return days

    def _call(self, name: str, args: list[CompiledNode]) -> CompiledNode:
        if name not in self.catalog.operators:
            raise ValueError(f"BRAIN 카탈로그에서 확인되지 않은 연산자입니다: {name}")
        self.operators.add(name)
        code = f"{name}({', '.join(arg.code for arg in args)})"
        if name in {"vec_avg", "vec_sum"} and len(args) == 1 and args[0].kind == "vector":
            action = "벡터 평균" if name == "vec_avg" else "벡터 합계"
            return CompiledNode(code, f"{args[0].meaning}의 {action}", "series")
        if name in {"rank", "abs"} and len(args) == 1 and args[0].kind == "series":
            suffix = "종목 간 상대 순위" if name == "rank" else "절댓값"
            return CompiledNode(code, f"({args[0].meaning})의 {suffix}", "series")
        if name in TIME_FUNCTIONS and len(args) == 2 and args[0].kind == "series":
            days = self._window(args[1])
            meaning = f"{days}거래일 기준 {args[0].meaning}의 {TIME_FUNCTIONS[name]}"
            return CompiledNode(code, meaning, "series")
        if name == "ts_corr" and len(args) == 3 and all(a.kind == "series" for a in args[:2]):
            days = self._window(args[2])
            return CompiledNode(
                code, f"최근 {days}거래일 {args[0].meaning}과 "
                f"{args[1].meaning}의 상관계수", "series"
            )
        if name in {"group_rank", "group_neutralize"} and len(args) == 2:
            if args[0].kind == "series" and args[1].kind == "group":
                action = "내 상대 순위" if name == "group_rank" else "별 평균 제거"
                return CompiledNode(
                    code, f"{args[0].meaning}의 {args[1].meaning}{action}", "series"
                )
        if name in {"trade_when", "if_else"} and len(args) == 3:
            if args[0].kind != "condition" or args[1].kind != "series":
                raise ValueError("조건부 식에는 비교 조건과 종목별 점수가 필요합니다.")
            if name == "trade_when":
                if args[2].code != "-1":
                    raise ValueError("자동 청산은 아직 지원하지 않습니다.")
                meaning = (
                    f"{args[0].meaning}일 때 {args[1].meaning}으로 점수를 갱신하고, "
                    "조건 미충족 시 직전 값을 유지"
                )
            else:
                if not _numeric(args[2]):
                    raise ValueError("조건 미충족 시 사용할 점수가 필요합니다.")
                meaning = f"{args[0].meaning}이면 {args[1].meaning}, 아니면 {args[2].meaning}"
            return CompiledNode(code, meaning, "series")
        raise ValueError(f"지원하지 않는 함수 또는 인자 구성입니다: {name}")


def draft_source_errors(strategy: str, compiler: DraftCompiler, expression: str) -> list[str]:
    """Check objective source constraints, without guessing the hypothesis with regex."""
    errors = validate_source_numbers(strategy, expression)
    if re.search(
        r"손절|익절|청산|보유\s*기간|\d+\s*일(?:간)?\s*보유|hold\s+for|stop.loss|take.profit",
        strategy, re.I,
    ):
        errors.append("요청에 현재 지원하지 않는 보유·청산 규칙이 포함돼 있습니다.")
    for pattern, field in ((r"거래량|\bvolume\b", "volume"), (r"종가|\bclose\b", "close")):
        if re.search(pattern, strategy, re.I) and field not in compiler.fields:
            errors.append(f"명시한 {FIELDS[field]} 데이터가 코드에서 사라졌습니다.")
    # Preserve the semantic slot of explicit cumulative-return windows.
    for match in re.finditer(
        r"(\d+)\s*(?:거래)?일\s*(?:누적\s*)?수익률"
        r"(?!\s*(?:의\s*)?(?:변동성|표준편차|분산|평균))", strategy,
    ):
        window = int(match.group(1))
        if window == 1 and "returns" in compiler.fields:
            continue
        expected = ast.parse(f"close / ts_delay(close, {window}) - 1", mode="eval").body
        if not any(ast.dump(node) == ast.dump(expected) for node in ast.walk(compiler.tree)):
            errors.append("명시한 기간 수익률 계산이 보존되지 않았습니다.")
    # An entry window/threshold must survive in its own comparison, not elsewhere
    # in the score. Compare ASTs so harmless spacing/parentheses are irrelevant.
    comparisons = {"이상": ">=", "초과": ">", "이하": "<=", "미만": "<"}
    for match in re.finditer(
        r"거래량[^.。\n]*?(\d+)\s*(?:거래)?일\s*평균(?:의|보다)?\s*"
        r"(\d+(?:\.\d+)?)\s*배\s*(이상|초과|이하|미만)", strategy,
    ):
        days, multiplier, comparator = match.groups()
        condition = (
            f"volume {comparisons[comparator]} {float(multiplier)} * ts_mean(volume, {int(days)})"
        )
        expected = expression_signature(ast.parse(condition, mode="eval").body)
        if not any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"trade_when", "if_else"}
            and node.args and expression_signature(node.args[0]) == expected
            for node in ast.walk(compiler.tree)
        ):
            errors.append("명시한 거래량 평균·배수·비교 조건이 보존되지 않았습니다.")
    return errors


def compile_draft(strategy: str, ir: DraftIR, settings: dict) -> tuple[str | None, list[str], dict]:
    if ir.status != "ok":
        return None, [ir.reason or "현재 사용 가능한 데이터로 가설을 표현하지 못했습니다."], {}
    if not ir.hypothesis.strip() or not ir.refinementOptions or not ir.improvementSuggestions:
        return None, ["가설 설명 또는 개선 선택지가 누락됐습니다."], {}
    compiler = DraftCompiler()
    try:
        compiler.catalog.check_scope(settings)
    except ValueError as exc:
        return None, [str(exc)], {}
    try:
        result = compiler.compile(ir.expression)
    except ValueError as exc:
        return None, [str(exc)], {}
    errors = draft_source_errors(strategy, compiler, result.code)
    if errors:
        return None, errors, {}
    assumptions = list(ir.assumptions)
    if compiler.windows:
        assumptions.append(
            "코드에서 사용하는 관찰 기간: " + ", ".join(map(str, sorted(compiler.windows)))
            + "거래일. 입력에 없던 기간은 AI가 정한 초안 값입니다."
        )
    assumptions.append(
        "AI가 선택한 측정 방법은 가설을 시험하기 위한 초안이며 성과를 확인하지 않았습니다."
    )
    model_fields = sorted(compiler.fields - FIELDS.keys() - GROUPS.keys())
    if model_fields:
        assumptions.append(
            "카탈로그에서 ID·자료형을 검사한 필드: " + ", ".join(model_fields)
            + ". 현재 BRAIN 계정 권한과 실행 성공은 별도 확인이 필요합니다."
        )
    return result.code, [], {
        "strategyExplanation": f"{ir.hypothesis}\n코드의 계산: {result.meaning}. "
        "이 값을 종목별 점수로 사용합니다. "
        f"실제 포지션은 중립화({settings['neutralization']}), Delay {settings['delay']}, "
        f"Decay {settings['decay']} 설정에도 영향을 받습니다.",
        "assumptions": assumptions,
        "intentMapping": compiler.steps,
        "improvementSuggestions": ir.improvementSuggestions,
        "refinementOptions": ir.refinementOptions,
    }
