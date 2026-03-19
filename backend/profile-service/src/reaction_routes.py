"""Reaction routes — one reaction per user per post."""

from fastapi import APIRouter, Header, HTTPException

from .database import get_db
from .reaction_database import remove_reaction, set_reaction
from .cache import (
    get_post,
    get_profile,
    invalidate_post_counts,
    invalidate_post_reaction,
    invalidate_reaction_list,
    list_reactions_by_post,
)
from .schema import get_fields, validate

router = APIRouter(prefix="/posts/{post_id}/reactions", tags=["reactions"])


# ── Response builder ──────────────────────────────────────────────────

_RESPONSE_FIELDS: set[str] | None = None


def _get_response_fields() -> set[str]:
    global _RESPONSE_FIELDS
    if _RESPONSE_FIELDS is None:
        _RESPONSE_FIELDS = set(get_fields("reaction_base")) | set(get_fields("reaction_response"))
    return _RESPONSE_FIELDS


async def _to_response(doc: dict) -> dict:
    """Build a response dict from a DB document."""
    fields = _get_response_fields()

    author_profile = await get_profile(doc["authorUid"], get_db())
    author_username = author_profile["username"] if author_profile else None
    author_photo = author_profile.get("profilePhoto") if author_profile else None

    out: dict = {}
    for field in fields:
        if field == "id":
            out["id"] = doc["_id"]
        elif field == "type":
            out["type"] = doc.get("reactionType")
        elif field == "username":
            out["username"] = author_username
        elif field == "profilePhoto":
            out["profilePhoto"] = author_photo
        else:
            out[field] = doc.get(field)
    return out


# ── Endpoints ─────────────────────────────────────────────────────────

@router.put("", status_code=200)
async def set_user_reaction(post_id: str, request_body: dict, x_user_id: str = Header(...)):
    """Set or update the current user's reaction on a post."""
    post = await get_post(post_id, get_db())
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    errors = validate("reaction_set", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    doc = await set_reaction(post_id, x_user_id, request_body["type"])

    await invalidate_post_counts(post_id)
    await invalidate_post_reaction(post_id, x_user_id)
    await invalidate_reaction_list(post_id)

    return await _to_response(doc)


@router.get("")
async def list_by_post(post_id: str, x_user_id: str = Header(...)):
    """List all reactions on a post."""
    post = await get_post(post_id, get_db())
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    docs = await list_reactions_by_post(post_id, get_db())
    return [await _to_response(d) for d in docs]


@router.delete("", status_code=204)
async def remove_user_reaction(post_id: str, x_user_id: str = Header(...)):
    """Remove the current user's reaction from a post."""
    post = await get_post(post_id, get_db())
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    removed = await remove_reaction(post_id, x_user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Reaction not found")

    await invalidate_post_counts(post_id)
    await invalidate_post_reaction(post_id, x_user_id)
    await invalidate_reaction_list(post_id)
