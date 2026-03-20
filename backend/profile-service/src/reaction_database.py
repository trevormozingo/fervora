"""
MongoDB database layer for reactions.

One reaction per user per post. Setting a reaction upserts; removing
soft-deletes. Soft-delete pattern matches profiles/posts/comments.
"""

from datetime import datetime, timezone
from typing import Any

from .database import get_db


def _reactions():
    return get_db().reactions


def _active(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    q: dict[str, Any] = {"isDeleted": {"$ne": True}}
    if extra:
        q.update(extra)
    return q


async def set_reaction(post_id: str, author_uid: str, reaction_type: str) -> dict[str, Any]:
    """Set (upsert) a reaction. One active reaction per user per post."""
    now = datetime.now(timezone.utc).isoformat()
    return await _reactions().find_one_and_update(
        {"postId": post_id, "authorUid": author_uid},
        {
            "$set": {"reactionType": reaction_type, "isDeleted": False, "updatedAt": now},
            "$unset": {"deletedAt": ""},
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
        return_document=True,
    )


async def set_reaction_in_session(post_id: str, author_uid: str, reaction_type: str, session) -> dict[str, Any]:
    """Set (upsert) a reaction within a transaction."""
    now = datetime.now(timezone.utc).isoformat()
    return await _reactions().find_one_and_update(
        {"postId": post_id, "authorUid": author_uid},
        {
            "$set": {"reactionType": reaction_type, "isDeleted": False, "updatedAt": now},
            "$unset": {"deletedAt": ""},
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
        return_document=True,
        session=session,
    )


async def remove_reaction(post_id: str, author_uid: str) -> bool:
    """Soft-delete a user's reaction on a post."""
    now = datetime.now(timezone.utc).isoformat()
    result = await _reactions().update_one(
        _active({"postId": post_id, "authorUid": author_uid}),
        {"$set": {"isDeleted": True, "deletedAt": now}},
    )
    return result.modified_count > 0
