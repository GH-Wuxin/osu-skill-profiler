"""Minimal JSON-Schema subset validator (stdlib only).

Supports the subset used by this project's schemas: type (string or list),
required, properties, additionalProperties, items, enum, const, minimum,
maximum, minLength, pattern, minItems, maxItems, oneOf, anyOf.
"""

from __future__ import annotations

import re
from typing import Any


class ValidationError(ValueError):
    pass


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate(instance: Any, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []

    type_spec = schema.get("type")
    if type_spec is not None:
        expected_types = [type_spec] if isinstance(type_spec, str) else list(type_spec)
        if not any(_type_matches(instance, expected) for expected in expected_types):
            errors.append(f"{path}: expected type {expected_types}, got {type(instance).__name__}")
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} not in enum {schema['enum']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{path}: does not match pattern {schema['pattern']!r}")

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key, property_schema in properties.items():
            if key in instance:
                errors.extend(validate(instance[key], property_schema, f"{path}.{key}"))
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        additional = schema.get("additionalProperties")
        if additional is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key!r}")
        elif isinstance(additional, dict):
            for key, value in instance.items():
                if key not in properties:
                    errors.extend(validate(value, additional, f"{path}.{key}"))

    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(instance):
                errors.extend(validate(item, items, f"{path}[{index}]"))
        elif isinstance(items, list):
            for index, item in enumerate(instance):
                if index < len(items):
                    errors.extend(validate(item, items[index], f"{path}[{index}]"))
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems {schema['maxItems']}")

    if "oneOf" in schema:
        matches = sum(not validate(instance, candidate, path) for candidate in schema["oneOf"])
        if matches != 1:
            errors.append(f"{path}: must match exactly one oneOf schema (matched {matches})")
    if "anyOf" in schema:
        if not any(not validate(instance, candidate, path) for candidate in schema["anyOf"]):
            errors.append(f"{path}: must match at least one anyOf schema")
    if "allOf" in schema:
        for candidate in schema["allOf"]:
            errors.extend(validate(instance, candidate, path))

    return errors


def assert_valid(instance: Any, schema: dict, label: str = "instance") -> None:
    errors = validate(instance, schema)
    if errors:
        raise ValidationError(f"{label} failed validation: " + "; ".join(errors))
