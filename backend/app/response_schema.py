"""Structured response schema; local validation retains numeric bounds."""

from .catalog_context import CURRENT_CATALOG
from .models import IntentIR


def strict_schema() -> dict:
    schema = IntentIR.model_json_schema()
    catalog = CURRENT_CATALOG.get()
    if catalog is not None:
        fields = sorted(catalog.fields)
        if not fields:
            raise ValueError("필드 후보 목록이 비어 있습니다.")
        metric = schema["$defs"]["IntentMetric"]["properties"]
        metric["field"]["enum"] = fields
        if catalog.source_excerpts:
            metric["source"]["enum"] = list(catalog.source_excerpts)
            schema["$defs"]["IntentEntry"]["properties"]["source"]["enum"] = list(
                catalog.source_excerpts,
            )
        for option in metric["reference"]["anyOf"]:
            if option.get("type") == "string":
                option["enum"] = fields
        # Keep auxiliary prose from consuming the bounded output needed for the plan.
        schema["properties"]["improvementSuggestions"]["maxItems"] = 1
        schema["properties"]["refinementOptions"]["maxItems"] = 2
        for name, limits in {
            "ImprovementSuggestion": {"title": 16, "rationale": 32, "experiment": 48},
            "RefinementOption": {"label": 16, "description": 32, "strategy": 120},
        }.items():
            for key, limit in limits.items():
                schema["$defs"][name]["properties"][key]["maxLength"] = limit

    def visit(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object" and "properties" in value:
                value["required"] = list(value["properties"])
            # Pydantic enforces bounds locally; keep the wire schema portable.
            if isinstance(value.get("title"), str):
                value.pop("title")
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                value.pop(key, None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema
