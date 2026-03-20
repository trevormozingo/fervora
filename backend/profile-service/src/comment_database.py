"""
MongoDB database layer for comments.

Soft-delete pattern: documents are never hard-deleted. Instead, `isDeleted`
is set to True and a `deletedAt` timestamp is recorded. All queries exclude
soft-deleted documents by default.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from .schema import get_fields

# Reuse the shared database connection from the profile database module.
from .database import get_db


def _comments():
    return get_db().comments


# ── Active-only filter ────────────────────────────────────────────────

def _active(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    q: dict[str, Any] = {"isDeleted": {"$ne": True}}
    if extra:
        q.update(extra)
    return q


# ── CRUD ──────────────────────────────────────────────────────────────

async def create_comment(post_id: str, author_uid: str, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc: dict[str, Any] = {
        "_id": str(ObjectId()),
        "postId": post_id,
        "authorUid": author_uid,
    }
    for field in get_fields("comment_create"):
        if field in data:
            doc[field] = data[field]
    doc["createdAt"] = now
    await _comments().insert_one(doc)
    return doc


async def create_comment_in_session(post_id: str, author_uid: str, data: dict[str, Any], session) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc: dict[str, Any] = {
        "_id": str(ObjectId()),
        "postId": post_id,
        "authorUid": author_uid,
    }
    for field in get_fields("comment_create"):
        if field in data:
            doc[field] = data[field]
    doc["createdAt"] = now
    await _comments().insert_one(doc, session=session)
    return doc


async def soft_delete_comment(comment_id: str, author_uid: str) -> bool:
    """Soft-delete a comment. Only the author can delete their own comment."""
    now = datetime.now(timezone.utc).isoformat()
    result = await _comments().update_one(
        _active({"_id": comment_id, "authorUid": author_uid}),
        {"$set": {"isDeleted": True, "deletedAt": now}},
    )
    return result.modified_count > 0
