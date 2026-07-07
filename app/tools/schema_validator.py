"""Schema validator tool – JSON Schema and DB schema validation."""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool as LangChainBaseTool
from pydantic import BaseModel, Field


class JSONSchemaValidateInput(BaseModel):
    schema_str: str = Field(description="JSON Schema as a string")
    data_str: str = Field(description="Data to validate as a JSON string")


class JSONSchemaValidatorTool(LangChainBaseTool):
    name: str = "validate_json_schema"
    description: str = "Validate data against a JSON Schema. Returns validation errors if any."
    args_schema: type[BaseModel] = JSONSchemaValidateInput

    def _run(self, schema_str: str, data_str: str) -> str:
        try:
            schema = json.loads(schema_str)
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            return f"❌ Invalid JSON: {e}"

        # Basic structural validation (no jsonschema dependency needed)
        errors = []
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in data:
                errors.append(f"Missing required field: '{field}'")

        for field, value in data.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type and not _type_matches(value, expected_type):
                    errors.append(f"Field '{field}': expected {expected_type}, got {type(value).__name__}")

        if errors:
            return "❌ Validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
        return "✅ Data validates against schema"


def _type_matches(value: object, json_type: str) -> bool:
    """Check if a Python value matches a JSON Schema type."""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    expected = type_map.get(json_type)
    if expected is None:
        return True
    return isinstance(value, expected)
