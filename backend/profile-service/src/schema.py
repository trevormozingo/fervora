"""Schema validation using JSON Schema files under models/."""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker, RefResolver

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

_SCHEMA_MAP = {
    "profile_create": "profile/create.schema.json",
    "profile_update": "profile/update.schema.json",
    "profile_response": "profile/response.schema.json",
    "post_create": "post/create.schema.json",
    "post_base": "post/base.schema.json",
    "post_response": "post/response.schema.json",
    "comment_create": "comment/create.schema.json",
    "comment_base": "comment/base.schema.json",
    "comment_response": "comment/response.schema.json",
    "reaction_set": "reaction/set.schema.json",
    "reaction_base": "reaction/base.schema.json",
    "reaction_response": "reaction/response.schema.json",
    "event_create": "event/create.schema.json",
    "event_base": "event/base.schema.json",
    "event_rsvp": "event/rsvp.schema.json",
}


@lru_cache(maxsize=None)
def _load_schema(schema_key: str) -> tuple[dict, Draft7Validator]:
    rel = _SCHEMA_MAP[schema_key]
    schema_path = _MODELS_DIR / rel
    with open(schema_path) as f:
        schema = json.load(f)
    resolver = RefResolver(
        base_uri=schema_path.parent.as_uri() + "/",
        referrer=schema,
    )
    return schema, Draft7Validator(schema, resolver=resolver, format_checker=FormatChecker())


def validate(schema_key: str, data: dict) -> list[str]:
    """Return a list of validation error messages, or [] if valid."""
    _, v = _load_schema(schema_key)
    return [e.message for e in v.iter_errors(data)]


def get_fields(schema_key: str) -> list[str]:
    """Return the property names defined in a schema."""
    schema, _ = _load_schema(schema_key)
    return list(schema.get("properties", {}).keys())
