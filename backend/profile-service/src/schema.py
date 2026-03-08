"""
Schema loader and validator.

Loads JSON Schema files from models/profile/ and validates data against them.
Schemas are the single source of truth.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, FormatChecker, ValidationError
from jsonschema.validators import RefResolver

_format_checker = FormatChecker()
_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def _load_schema(path: str) -> dict:
    with open(_MODELS_DIR / path, "r") as f:
        return json.load(f)


def _build_dir_resolver(subdir: str) -> RefResolver:
    """Build a RefResolver scoped to a specific models subdirectory."""
    schema_dir = _MODELS_DIR / subdir
    base_schema = _load_schema(f"{subdir}/base.schema.json")
    base_uri = schema_dir.as_uri() + "/"
    store = {}
    for schema_file in schema_dir.glob("*.schema.json"):
        schema = json.loads(schema_file.read_text())
        store[schema_file.as_uri()] = schema
        store[schema_file.name] = schema
    return RefResolver(base_uri, base_schema, store=store)


_profile_resolver = _build_dir_resolver("profile")
_post_resolver = _build_dir_resolver("post")
_reaction_resolver = _build_dir_resolver("reaction")
_comment_resolver = _build_dir_resolver("comment")
_event_resolver = _build_dir_resolver("event")

VALIDATORS = {
    "create": Draft7Validator(
        _load_schema("profile/create.schema.json"),
        resolver=_profile_resolver,
        format_checker=_format_checker,
    ),
    "update": Draft7Validator(
        _load_schema("profile/update.schema.json"),
        resolver=_profile_resolver,
        format_checker=_format_checker,
    ),
    "post_create": Draft7Validator(
        _load_schema("post/create.schema.json"),
        resolver=_post_resolver,
        format_checker=_format_checker,
    ),
    "reaction_set": Draft7Validator(
        _load_schema("reaction/set.schema.json"),
        resolver=_reaction_resolver,
        format_checker=_format_checker,
    ),
    "comment_create": Draft7Validator(
        _load_schema("comment/create.schema.json"),
        resolver=_comment_resolver,
        format_checker=_format_checker,
    ),
    "event_create": Draft7Validator(
        _load_schema("event/create.schema.json"),
        resolver=_event_resolver,
        format_checker=_format_checker,
    ),
    "event_rsvp": Draft7Validator(
        _load_schema("event/rsvp.schema.json"),
        resolver=_event_resolver,
        format_checker=_format_checker,
    ),
}


def validate(schema_name: str, data: dict[str, Any]) -> list[str]:
    """Validate data against a named schema. Returns error messages (empty = valid)."""
    validator = VALIDATORS.get(schema_name)
    if validator is None:
        raise ValueError(f"Unknown schema: {schema_name}")
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [_format_error(e) for e in errors]


def _format_error(error: ValidationError) -> str:
    path = ".".join(str(p) for p in error.absolute_path)
    if path:
        return f"{path}: {error.message}"
    return error.message
