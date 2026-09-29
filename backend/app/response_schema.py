"""Structured response schema; local validation retains numeric bounds."""

from .models import DraftIR


def strict_schema() -> dict:
    schema = DraftIR.model_json_schema()

    def visit(value):
        if isinstance(value, dict):
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
