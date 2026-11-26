"""Nested Paper field projection and completeness checks."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Literal, cast

from paper_tools.core.errors import UsageError
from paper_tools.core.models import Paper

PathToken = str | Literal["[]"]
FieldPath = tuple[PathToken, ...]

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH_PATTERN = re.compile(rf"{_NAME}(?:\[\]|\.{_NAME})*")
_TOKEN_PATTERN = re.compile(r"\[\]|[A-Za-z_][A-Za-z0-9_]*")
_MISSING = object()


@lru_cache(maxsize=256)
def parse_field_path(raw: str) -> FieldPath:
    path = raw.strip()
    if not _PATH_PATTERN.fullmatch(path):
        raise UsageError(
            f"Invalid field path {raw!r}; use 'identifiers.doi' for objects "
            "and 'authors[].name' for arrays."
        )
    return tuple(cast(PathToken, token) for token in _TOKEN_PATTERN.findall(path))


def parse_field_paths(fields: list[str]) -> list[FieldPath]:
    return [parse_field_path(field) for field in fields]


def all_field_names() -> list[str]:
    return list(Paper.model_fields)


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _present(value: Any, path: FieldPath, raw: str) -> bool:
    if not path:
        return not _is_missing(value) and not (raw.strip() == "oa_status" and value == "unknown")
    token, *rest = path
    if token == "[]":
        if not isinstance(value, list):
            raise UsageError(f"Field path {raw!r} expects an array at '[]'.")
        return bool(value) and all(_present(item, tuple(rest), raw) for item in value)
    if not isinstance(value, dict):
        raise UsageError(f"Field path {raw!r} expects an object at '{token}'.")
    if token not in value:
        return False
    return _present(value[token], tuple(rest), raw)


def field_is_present(data: dict[str, Any], raw: str) -> bool:
    return _present(data, parse_field_path(raw), raw)


def _project(value: Any, path: FieldPath, raw: str, depth: int = 0) -> Any:
    if not path:
        return _MISSING if depth > 1 and _is_missing(value) else value
    token, *rest = path
    if token == "[]":
        if not isinstance(value, list):
            raise UsageError(f"Field path {raw!r} expects an array at '[]'.")
        items = []
        for item in value:
            projected = _project(item, tuple(rest), raw, depth + 1)
            if projected is _MISSING:
                projected = {} if isinstance(item, dict) else None
            items.append(projected)
        return items
    if not isinstance(value, dict):
        raise UsageError(f"Field path {raw!r} expects an object at '{token}'.")
    if token not in value:
        return _MISSING
    projected = _project(value[token], tuple(rest), raw, depth + 1)
    if projected is _MISSING:
        return _MISSING
    return {token: projected}


def _merge_projection(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _merge_projection(target[key], value)
        else:
            target[key] = value


def project_field_paths(data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in fields:
        projected = _project(data, parse_field_path(raw), raw)
        if projected is not _MISSING:
            _merge_projection(result, projected)
    return result
