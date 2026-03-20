"""
MongoDB database layer for profiles.

Soft-delete pattern: documents are never hard-deleted. Instead, `isDeleted`
is set to True and a `deletedAt` timestamp is recorded. All queries exclude
soft-deleted documents by default.
"""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from .schema import get_fields

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect(mongo_uri: str, db_name: str = "fervora") -> None:
    global _client, _db
    _client = AsyncIOMotorClient(mongo_uri)
    _db = _client[db_name]

    # Profiles
    await _db.profiles.create_index("username", unique=True)
    await _db.profiles.create_index([("location", "2dsphere")])

    # Posts
    await _db.posts.create_index([("authorUid", 1), ("isDeleted", 1), ("createdAt", -1)])

    # Comments
    await _db.comments.create_index([("postId", 1), ("isDeleted", 1), ("createdAt", -1)])
    await _db.comments.create_index([("authorUid", 1), ("isDeleted", 1)])

    # Reactions
    await _db.reactions.create_index(
        [("postId", 1), ("authorUid", 1)],
        unique=True,
    )
    await _db.reactions.create_index([("postId", 1), ("isDeleted", 1)])

    # Events
    await _db.events.create_index([("authorUid", 1), ("isDeleted", 1), ("startTime", -1)])
    await _db.events.create_index([("invitees.uid", 1), ("isDeleted", 1)])

    # Follows
    await _db.follows.create_index(
        [("followerId", 1), ("followedId", 1)],
        unique=True,
    )
    await _db.follows.create_index([("followerId", 1), ("isDeleted", 1)])
    await _db.follows.create_index([("followedId", 1), ("isDeleted", 1)])

    # Feed (fan-out-on-write)
    await _db.feed.create_index(
        [("ownerUid", 1), ("postId", 1)],
        unique=True,
    )
    await _db.feed.create_index([("ownerUid", 1), ("isDeleted", 1), ("createdAt", -1)])
    await _db.feed.create_index([("ownerUid", 1), ("authorUid", 1), ("isDeleted", 1)])
    await _db.feed.create_index([("postId", 1), ("isDeleted", 1)])


async def disconnect() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


def _profiles():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.profiles


def get_db():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db


def get_client():
    if _client is None:
        raise RuntimeError("Database not connected")
    return _client


# ── Active-only filter ────────────────────────────────────────────────

def _active(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a query filter that excludes soft-deleted documents."""
    q: dict[str, Any] = {"isDeleted": {"$ne": True}}
    if extra:
        q.update(extra)
    return q


# ── CRUD ──────────────────────────────────────────────────────────────


async def create_profile(uid: str, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc: dict[str, Any] = {"_id": uid}
    for field in get_fields("profile_create"):
        doc[field] = data.get(field)
    doc["createdAt"] = now
    doc["updatedAt"] = now
    await _profiles().insert_one(doc)
    return doc


async def update_profile(uid: str, data: dict[str, Any]) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    allowed = set(get_fields("profile_update"))
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updatedAt"] = now
    return await _profiles().find_one_and_update(
        _active({"_id": uid}),
        {"$set": updates},
        return_document=True,
    )


async def soft_delete_profile(uid: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    result = await _profiles().update_one(
        _active({"_id": uid}),
        {"$set": {"isDeleted": True, "deletedAt": now}},
    )
    return result.modified_count > 0
