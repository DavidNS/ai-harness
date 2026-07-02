
"""JSON Schema validation helpers for v2 artifact documents."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError

_SCHEMA_DIR = Path(__file__).with_name("json_schemas")


def validate_json_schema(value: Any, schema_name: str) -> None:
    schema = _load_schema(schema_name)
    _validate(value, schema, schema_name, "$")


@lru_cache(maxsize=None)
def _load_schema(schema_name: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / f"{schema_name}.schema.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except FileNotFoundError as exc:
        raise BundleValidationError(f"unknown JSON schema: {schema_name}") from exc
    if not isinstance(schema, dict):
        raise BundleValidationError(f"JSON schema {schema_name} must be an object")
    return schema


def _validate(value: Any, schema: dict[str, Any], schema_name: str, path: str) -> None:
    if "$ref" in schema:
        _validate(value, _resolve_ref(schema["$ref"], schema_name, path), schema_name, path)

    if "allOf" in schema:
        for subschema in _schema_list(schema["allOf"], schema_name, path, "allOf"):
            _validate(value, subschema, schema_name, path)
    if "anyOf" in schema:
        _validate_any_of(value, schema["anyOf"], schema_name, path)
    if "oneOf" in schema:
        _validate_one_of(value, schema["oneOf"], schema_name, path)
    if "const" in schema and value != schema["const"]:
        raise BundleValidationError(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise BundleValidationError(f"{path}: must be one of {schema['enum']!r}")

    type_spec = schema.get("type")
    if type_spec is not None and not _matches_type(value, type_spec):
        raise BundleValidationError(f"{path}: must be of type {_describe_type(type_spec)}")

    if isinstance(value, str):
        _validate_string(value, schema, path)

    if _is_object(value):
        _validate_object(value, schema, schema_name, path)
        return
    if _is_array(value):
        _validate_array(value, schema, schema_name, path)
        return


def _resolve_ref(ref: Any, schema_name: str, path: str) -> dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise BundleValidationError(f"{schema_name}: {path}.$ref must be a nonempty string")
    if ref.startswith("#"):
        raise BundleValidationError(f"{schema_name}: local JSON pointer refs are not supported: {ref}")
    return _load_schema(ref)


def _validate_any_of(value: Any, variants: Any, schema_name: str, path: str) -> None:
    errors: list[str] = []
    for index, subschema in enumerate(_schema_list(variants, schema_name, path, "anyOf")):
        try:
            _validate(value, subschema, schema_name, path)
            return
        except BundleValidationError as exc:
            errors.append(str(exc))
    raise BundleValidationError(f"{path}: does not match any allowed schema")


def _validate_one_of(value: Any, variants: Any, schema_name: str, path: str) -> None:
    matches = 0
    for subschema in _schema_list(variants, schema_name, path, "oneOf"):
        try:
            _validate(value, subschema, schema_name, path)
        except BundleValidationError:
            continue
        matches += 1
    if matches != 1:
        raise BundleValidationError(f"{path}: must match exactly one schema")


def _validate_object(value: dict[str, Any], schema: dict[str, Any], schema_name: str, path: str) -> None:
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise BundleValidationError(f"{schema_name}: required must be a list of strings")
    for key in required:
        if key not in value:
            raise BundleValidationError(f"{path}.{key if path != '$' else key}: is required")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise BundleValidationError(f"{schema_name}: properties must be an object")
    for key, subschema in properties.items():
        if key in value:
            _validate(value[key], _schema_object(subschema, schema_name, path, key), schema_name, f"{path}.{key}")

    additional = schema.get("additionalProperties", True)
    if additional is False:
        allowed = set(properties)
        extras = [key for key in value if key not in allowed]
        if extras:
            raise BundleValidationError(f"{path}: unexpected property {extras[0]!r}")
    elif isinstance(additional, dict):
        for key, item in value.items():
            if key not in properties:
                _validate(item, additional, schema_name, f"{path}.{key}")


def _validate_array(value: list[Any], schema: dict[str, Any], schema_name: str, path: str) -> None:
    min_items = schema.get("minItems")
    if min_items is not None and len(value) < int(min_items):
        raise BundleValidationError(f"{path}: must contain at least {int(min_items)} item(s)")
    max_items = schema.get("maxItems")
    if max_items is not None and len(value) > int(max_items):
        raise BundleValidationError(f"{path}: must contain at most {int(max_items)} item(s)")
    if schema.get("uniqueItems") is True:
        seen: set[str] = set()
        for item in value:
            marker = json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)
            if marker in seen:
                raise BundleValidationError(f"{path}: must contain unique items")
            seen.add(marker)
    items = schema.get("items")
    if items is not None:
        item_schema = _schema_object(items, schema_name, path, "items")
        for index, item in enumerate(value):
            _validate(item, item_schema, schema_name, f"{path}[{index}]")


def _validate_string(value: str, schema: dict[str, Any], path: str) -> None:
    min_length = schema.get("minLength")
    if min_length is not None and len(value.strip()) < int(min_length):
        raise BundleValidationError(f"{path}: must contain at least {int(min_length)} character(s)")
    max_length = schema.get("maxLength")
    if max_length is not None and len(value) > int(max_length):
        raise BundleValidationError(f"{path}: must contain at most {int(max_length)} character(s)")


def _schema_object(value: Any, schema_name: str, path: str, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleValidationError(f"{schema_name}: {path}.{field} schema must be an object")
    return value


def _schema_list(value: Any, schema_name: str, path: str, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise BundleValidationError(f"{schema_name}: {path}.{field} schema must be a list")
    return [_schema_object(item, schema_name, path, field) for item in value]


def _matches_type(value: Any, type_spec: Any) -> bool:
    if isinstance(type_spec, str):
        return _matches_single_type(value, type_spec)
    if isinstance(type_spec, list):
        return any(_matches_single_type(value, type_name) for type_name in type_spec)
    raise BundleValidationError(f"unsupported JSON schema type: {type_spec!r}")


def _matches_single_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return _is_object(value)
    if type_name == "array":
        return _is_array(value)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    raise BundleValidationError(f"unsupported JSON schema type: {type_name!r}")


def _is_object(value: Any) -> bool:
    return isinstance(value, dict)


def _is_array(value: Any) -> bool:
    return isinstance(value, list)


def _describe_type(type_spec: Any) -> str:
    if isinstance(type_spec, str):
        return type_spec
    if isinstance(type_spec, list):
        return " or ".join(type_spec)
    return repr(type_spec)
