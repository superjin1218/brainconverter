"""Structured response schema; local validation retains numeric bounds."""

from .brain_catalog import ACTIVE_CATALOG
from .models import IntentIR


def strict_schema() -> dict:
    schema = IntentIR.model_json_schema()
    selection = ACTIVE_CATALOG.get()
    if selection is not None:
        schema["$defs"]["CatalogField"] = {"type": "string", "enum": list(selection.ids)}
        metric = schema["$defs"]["IntentMetric"]["properties"]
        metric["field"] = {"$ref": "#/$defs/CatalogField"}
        metric["reference"] = {"anyOf": [{"$ref": "#/$defs/CatalogField"}, {"type": "null"}]}

    def visit(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object" and "properties" in value:
                value["required"] = list(value["properties"])
            # Pydantic enforces bounds locally; keep the wire schema portable.
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                value.pop(key, None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema
