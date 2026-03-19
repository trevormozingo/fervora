"""Comment routes."""

from fastapi import APIRouter, Header, HTTPException

from .database import get_db
from .comment_database import (
    create_comment,
    soft_delete_comment,
)
from .cache import (
    get_comment,
    get_post,
    get_profile,
    invalidate_comment,
    invalidate_comment_list,
    invalidate_post_comments,
    invalidate_post_counts,
    list_comments_by_post,
)
from .schema import get_fields, validate

router = APIRouter(prefix="/posts/{post_id}/comments", tags=["comments"])


# ── Response builder ──────────────────────────────────────────────────

_RESPONSE_FIELDS: set[str] | None = None


def _get_response_fields() -> set[str]:
    global _RESPONSE_FIELDS
    if _RESPONSE_FIELDS is None:
        _RESPONSE_FIELDS = set(get_fields("comment_base")) | set(get_fields("comment_response"))
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
        elif field == "authorUsername":
            out["authorUsername"] = author_username
        elif field == "authorProfilePhoto":
            out["authorProfilePhoto"] = author_photo
        else:
            out[field] = doc.get(field)
    return out


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create(post_id: str, request_body: dict, x_user_id: str = Header(...)):
    # Verify post exists
    post = await get_post(post_id, get_db())
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    errors = validate("comment_create", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    doc = await create_comment(post_id, x_user_id, request_body)

    # Invalidate cached comment count + recent comments + comment list for this post
    await invalidate_post_counts(post_id)
    await invalidate_post_comments(post_id)
    await invalidate_comment_list(post_id)

    return await _to_response(doc)


@router.get("")
async def list_by_post(post_id: str, x_user_id: str = Header(...)):
    post = await get_post(post_id, get_db())
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    docs = await list_comments_by_post(post_id, get_db())
    return [await _to_response(d) for d in docs]


@router.get("/{comment_id}")
async def get_by_id(post_id: str, comment_id: str, x_user_id: str = Header(...)):
    doc = await get_comment(comment_id, get_db())
    if not doc or doc.get("postId") != post_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    return await _to_response(doc)


@router.delete("/{comment_id}", status_code=204)
async def delete(post_id: str, comment_id: str, x_user_id: str = Header(...)):
    # Verify the comment belongs to this post before deleting
    doc = await get_comment(comment_id, get_db())
    if not doc or doc.get("postId") != post_id:
        raise HTTPException(status_code=404, detail="Comment not found")

    deleted = await soft_delete_comment(comment_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")

    await invalidate_comment(comment_id)
    await invalidate_comment_list(post_id)
    await invalidate_post_counts(post_id)
    await invalidate_post_comments(post_id)
