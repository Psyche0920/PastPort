"""Translate Pydantic schemas to the provider's strict structured-output subset."""

import json

from pydantic import JsonValue, RootModel


class _JSONValue(RootModel[JsonValue]):
    pass


class StrictOutputSchema:
    @classmethod
    def convert(cls, encoded: str) -> str:
        value = _JSONValue.model_validate_json(encoded).root
        return json.dumps(cls._visit(value), sort_keys=True)

    @classmethod
    def _visit(cls, value: JsonValue) -> JsonValue:
        if isinstance(value, list):
            return [cls._visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        output = {key: cls._visit(item) for key, item in value.items() if key != "default"}
        properties = output.get("properties")
        if isinstance(properties, dict):
            output["required"] = list(properties)
            output["additionalProperties"] = False
        return output
