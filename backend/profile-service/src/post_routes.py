"""Post routes."""

from fastapi import APIRouter, Header, HTTPException

from .database import get_db
from .post_database import create_post, soft_delete_post
from .cache import (
    get_post,
    get_profile,
    get_my_reaction,
    get_post_counts,
    get_recent_comments,
    invalidate_post,
    invalidate_post_comments,
    invalidate_post_counts,
    invalidate_post_list,
    invalidate_profile,
    list_posts_by_author,
)
from .schema import get_fields, validate

router = APIRouter(prefix="/posts", tags=["posts"])


# ── Response builder ──────────────────────────────────────────────────

# The post response schema uses allOf to merge base + response-specific
# properties. Combine both sets of field names for the response shape.
_RESPONSE_FIELDS: set[str] | None = None


def _get_response_fields() -> set[str]:
    global _RESPONSE_FIELDS
    if _RESPONSE_FIELDS is None:
        _RESPONSE_FIELDS = set(get_fields("post_base")) | set(get_fields("post_response"))
    return _RESPONSE_FIELDS


async def _to_response(doc: dict, viewer_uid: str | None = None) -> dict:
    """Build a response dict from a DB document."""
    fields = _get_response_fields()
    db = get_db()

    # Resolve author info via cache
    author_profile = await get_profile(doc["authorUid"], db)
    author_username = author_profile["username"] if author_profile else None
    author_photo = author_profile.get("profilePhoto") if author_profile else None

    # Cached aggregations
    post_id = doc["_id"]
    counts = await get_post_counts(post_id, db)
    recent = await get_recent_comments(post_id, db)
    my_reaction = await get_my_reaction(post_id, viewer_uid, db) if viewer_uid else None

    out: dict = {}
    for field in fields:
        if field == "id":
            out["id"] = post_id
        elif field == "authorUsername":
            out["authorUsername"] = author_username
        elif field == "authorProfilePhoto":
            out["authorProfilePhoto"] = author_photo
        elif field == "reactionSummary":
            out["reactionSummary"] = counts.get("reactionSummary", {})
        elif field == "commentCount":
            out["commentCount"] = counts.get("commentCount", 0)
        elif field == "recentComments":
            out["recentComments"] = recent
        elif field == "myReaction":
            out["myReaction"] = my_reaction
        else:
            out[field] = doc.get(field)
    return out


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create(request_body: dict, x_user_id: str = Header(...)):
    errors = validate("post_create", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    doc = await create_post(x_user_id, request_body)
    # Invalidate profile counts (postCount changed) and post list for this author
    await invalidate_profile(x_user_id)
    await invalidate_post_list(x_user_id)
    return await _to_response(doc, viewer_uid=x_user_id)


@router.get("/{post_id}")
async def get_by_id(post_id: str, x_user_id: str = Header(...)):
    doc = await get_post(post_id, get_db())
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return await _to_response(doc, viewer_uid=x_user_id)


@router.get("")
async def list_by_author(author: str, x_user_id: str = Header(...)):
    """List posts by a specific author. Query param: ?author=<uid>"""
    docs = await list_posts_by_author(author, get_db())
    return [await _to_response(d, viewer_uid=x_user_id) for d in docs]


@router.delete("/{post_id}", status_code=204)
async def delete(post_id: str, x_user_id: str = Header(...)):
    deleted = await soft_delete_post(post_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    await invalidate_post(post_id)
    await invalidate_post_list(x_user_id)
    await invalidate_post_counts(post_id)
    await invalidate_post_comments(post_id)
