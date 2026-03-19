"""
MongoDB database layer for follows.

One-way follow model (Instagram-style). Soft-delete pattern:
documents are never hard-deleted. Instead, `isDeleted` is set to True
and a `deletedAt` timestamp is recorded.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from .database import get_db


def _follows():
    return get_db().follows


def _active(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    q: dict[str, Any] = {"isDeleted": {"$ne": True}}
    if extra:
        q.update(extra)
    return q


async def create_follow(follower_uid: str, followed_uid: str) -> dict[str, Any] | None:
    """Create a follow relationship. Returns the doc, or None if already following."""
    existing = await _follows().find_one(
        _active({"followerId": follower_uid, "followedId": followed_uid})
    )
    if existing:
        return None  # already following

    now = datetime.now(timezone.utc).isoformat()
    doc: dict[str, Any] = {
        "_id": str(ObjectId()),
        "followerId": follower_uid,
        "followedId": followed_uid,
        "createdAt": now,
    }
    await _follows().insert_one(doc)
    return doc


async def remove_follow(follower_uid: str, followed_uid: str) -> bool:
    """Soft-delete a follow relationship."""
    now = datetime.now(timezone.utc).isoformat()
    result = await _follows().update_one(
        _active({"followerId": follower_uid, "followedId": followed_uid}),
        {"$set": {"isDeleted": True, "deletedAt": now}},
    )
    return result.modified_count > 0
