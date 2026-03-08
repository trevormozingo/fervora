"""
MongoDB database layer.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect(mongo_uri: str, db_name: str = "ironguild") -> None:
    global _client, _db
    _client = AsyncIOMotorClient(mongo_uri)
    _db = _client[db_name]
    await _db.profiles.create_index("username", unique=True)
    await _db.posts.create_index([("authorUid", 1), ("createdAt", -1)])
    await _db.follows.create_index(
        [("followerUid", 1), ("followingUid", 1)], unique=True
    )
    await _db.follows.create_index("followingUid")
    await _db.feed.create_index([("ownerUid", 1), ("createdAt", -1)])
    await _db.feed.create_index("postId")
    await _db.feed.create_index("authorUid")
    await _db.reactions.create_index(
        [("postId", 1), ("uid", 1)], unique=True
    )
    await _db.reactions.create_index("postId")
    await _db.reactions.create_index("uid")
    await _db.comments.create_index([("postId", 1), ("createdAt", 1)])
    await _db.comments.create_index("authorUid")
    await _db.events.create_index([("creatorUid", 1), ("startTime", 1)])
    await _db.events.create_index("invitees.uid")


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


async def create_profile(uid: str, data: dict[str, Any]) -> dict[str, Any]:
    """
    Insert a new profile.
    Stored fields match base.schema.json: username, displayName, bio, birthday.
    """
    doc = {
        "_id": uid,
        "username": data["username"],
        "displayName": data.get("displayName", data["username"]),
        "bio": None,
        "birthday": None,
    }
    await _profiles().insert_one(doc)
    return doc


async def get_profile_by_id(uid: str) -> dict[str, Any] | None:
    return await _profiles().find_one({"_id": uid})


async def get_profile_by_username(username: str) -> dict[str, Any] | None:
    return await _profiles().find_one({"username": username})


async def update_profile(uid: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Update only the provided fields (from update.schema.json)."""
    return await _profiles().find_one_and_update(
        {"_id": uid},
        {"$set": data},
        return_document=True,
    )


async def delete_profile(uid: str) -> bool:
    """Delete a profile and cascade-delete all related data atomically."""
    async with await _client.start_session() as session:
        async with session.start_transaction():
            result = await _profiles().delete_one({"_id": uid}, session=session)
            if result.deleted_count == 0:
                return False

            # Gather this user's post IDs before deleting them
            post_cursor = _posts().find(
                {"authorUid": uid}, {"_id": 1}, session=session
            )
            post_ids = [doc["_id"] async for doc in post_cursor]

            await _posts().delete_many({"authorUid": uid}, session=session)
            await _follows().delete_many(
                {"$or": [{"followerUid": uid}, {"followingUid": uid}]},
                session=session,
            )
            await _feed().delete_many(
                {"$or": [{"authorUid": uid}, {"ownerUid": uid}]},
                session=session,
            )
            # Remove reactions/comments BY this user (on anyone's posts)
            await _reactions().delete_many({"uid": uid}, session=session)
            await _comments().delete_many({"authorUid": uid}, session=session)
            # Remove reactions/comments ON this user's deleted posts
            if post_ids:
                await _reactions().delete_many(
                    {"postId": {"$in": post_ids}}, session=session
                )
                await _comments().delete_many(
                    {"postId": {"$in": post_ids}}, session=session
                )
            # Remove events created by this user
            await _events().delete_many({"creatorUid": uid}, session=session)
            # Remove this user from invitee lists on other events
            await _events().update_many(
                {"invitees.uid": uid},
                {"$pull": {"invitees": {"uid": uid}}},
                session=session,
            )
            return True


# ── Posts ─────────────────────────────────────────────────────────────


def _posts():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.posts


async def create_post(uid: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Insert a new post and fan-out feed entries to all followers.

    Returns None if the user has no profile (rejected).
    Uses a transaction so profile check, post insert, and feed fan-out
    are atomic.
    """
    async with await _client.start_session() as session:
        async with session.start_transaction():
            profile = await _profiles().find_one({"_id": uid}, session=session)
            if profile is None:
                return None

            now = datetime.now(timezone.utc).isoformat()
            doc = {
                "authorUid": uid,
                "title": data.get("title"),
                "body": data.get("body"),
                "media": data.get("media"),
                "workout": data.get("workout"),
                "bodyMetrics": data.get("bodyMetrics"),
                "createdAt": now,
            }
            result = await _posts().insert_one(doc, session=session)
            doc["_id"] = result.inserted_id
            post_id = result.inserted_id

            # Fan-out: create a feed entry for every follower
            followers = _follows().find(
                {"followingUid": uid}, {"followerUid": 1, "_id": 0},
                session=session,
            )
            feed_docs = [
                {
                    "ownerUid": f["followerUid"],
                    "postId": post_id,
                    "authorUid": uid,
                    "createdAt": now,
                }
                async for f in followers
            ]
            if feed_docs:
                await _feed().insert_many(feed_docs, session=session)

            return doc


async def delete_post(post_id: str, uid: str) -> bool:
    """Delete a post and its feed/reactions/comments atomically. Only the author can delete."""
    try:
        oid = ObjectId(post_id)
    except Exception:
        return False
    async with await _client.start_session() as session:
        async with session.start_transaction():
            result = await _posts().delete_one(
                {"_id": oid, "authorUid": uid}, session=session
            )
            if result.deleted_count == 0:
                return False
            await _feed().delete_many({"postId": oid}, session=session)
            await _reactions().delete_many({"postId": oid}, session=session)
            await _comments().delete_many({"postId": oid}, session=session)
            return True


# ── Follows ───────────────────────────────────────────────────────────


def _follows():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.follows


async def follow_user(follower_uid: str, following_uid: str) -> bool | None:
    """
    Create a follow relationship. Both users must have profiles.

    Returns True if newly created, False if already following, None if
    either user has no profile.

    Uses a transaction so profile checks + insert are atomic.
    """
    async with await _client.start_session() as session:
        try:
            async with session.start_transaction():
                follower = await _profiles().find_one({"_id": follower_uid}, session=session)
                if follower is None:
                    return None
                target = await _profiles().find_one({"_id": following_uid}, session=session)
                if target is None:
                    return None
                await _follows().insert_one(
                    {"followerUid": follower_uid, "followingUid": following_uid},
                    session=session,
                )
                return True
        except DuplicateKeyError:
            return False


async def unfollow_user(follower_uid: str, following_uid: str) -> bool:
    """Remove a follow relationship. Returns True if deleted."""
    result = await _follows().delete_one(
        {"followerUid": follower_uid, "followingUid": following_uid}
    )
    return result.deleted_count > 0


async def get_following(uid: str) -> list[str]:
    """Get list of UIDs that this user follows."""
    cursor = _follows().find(
        {"followerUid": uid}, {"followingUid": 1, "_id": 0}
    )
    return [doc["followingUid"] async for doc in cursor]


async def get_followers(uid: str) -> list[str]:
    """Get list of UIDs that follow this user."""
    cursor = _follows().find(
        {"followingUid": uid}, {"followerUid": 1, "_id": 0}
    )
    return [doc["followerUid"] async for doc in cursor]


# ── Feed ──────────────────────────────────────────────────────────────


def _feed():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.feed


async def get_feed(
    uid: str, limit: int = 20, cursor: str | None = None
) -> list[dict[str, Any]]:
    """
    Get feed entries for a user, newest first.
    Cursor-based pagination using createdAt.
    Returns post documents (not feed pointer docs).
    """
    query: dict[str, Any] = {"ownerUid": uid}
    if cursor:
        query["createdAt"] = {"$lt": cursor}

    feed_cursor = _feed().find(
        query, {"postId": 1, "_id": 0}
    ).sort("createdAt", -1).limit(limit)

    post_ids = [doc["postId"] async for doc in feed_cursor]
    if not post_ids:
        return []

    # Fetch the actual post documents
    posts_cursor = _posts().find({"_id": {"$in": post_ids}})
    posts_by_id = {doc["_id"]: doc async for doc in posts_cursor}

    # Return in feed order, skip any posts that were somehow deleted
    return [posts_by_id[pid] for pid in post_ids if pid in posts_by_id]


# ── Reactions ─────────────────────────────────────────────────────────


def _reactions():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.reactions


async def set_reaction(
    post_id: str, uid: str, reaction_type: str
) -> dict[str, Any] | None:
    """
    Set a reaction on a post. One reaction per user per post.
    If the user already reacted, update the type.
    Returns None if the post doesn't exist.
    """
    try:
        oid = ObjectId(post_id)
    except Exception:
        return None
    # Verify post exists
    post = await _posts().find_one({"_id": oid})
    if post is None:
        return None
    doc = await _reactions().find_one_and_update(
        {"postId": oid, "uid": uid},
        {"$set": {"postId": oid, "uid": uid, "type": reaction_type}},
        upsert=True,
        return_document=True,
    )
    return doc


async def remove_reaction(post_id: str, uid: str) -> bool:
    """Remove a user's reaction from a post."""
    try:
        oid = ObjectId(post_id)
    except Exception:
        return False
    result = await _reactions().delete_one({"postId": oid, "uid": uid})
    return result.deleted_count > 0


async def get_reactions(post_id: str) -> list[dict[str, Any]]:
    """Get all reactions on a post."""
    try:
        oid = ObjectId(post_id)
    except Exception:
        return []
    cursor = _reactions().find(
        {"postId": oid}, {"_id": 0, "postId": 0}
    )
    return [doc async for doc in cursor]


# ── Comments ──────────────────────────────────────────────────────────


def _comments():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.comments


async def create_comment(
    post_id: str, uid: str, data: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Create a comment on a post. Returns None if post doesn't exist.
    Requires the user to have a profile.
    """
    try:
        oid = ObjectId(post_id)
    except Exception:
        return None
    async with await _client.start_session() as session:
        async with session.start_transaction():
            profile = await _profiles().find_one({"_id": uid}, session=session)
            if profile is None:
                return None
            post = await _posts().find_one({"_id": oid}, session=session)
            if post is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            doc = {
                "postId": oid,
                "authorUid": uid,
                "body": data["body"],
                "createdAt": now,
            }
            result = await _comments().insert_one(doc, session=session)
            doc["_id"] = result.inserted_id
            return doc


async def delete_comment(comment_id: str, uid: str) -> bool:
    """Delete a comment. Only the comment author can delete."""
    try:
        oid = ObjectId(comment_id)
    except Exception:
        return False
    result = await _comments().delete_one({"_id": oid, "authorUid": uid})
    return result.deleted_count > 0


async def get_comments(
    post_id: str, limit: int = 50, cursor: str | None = None
) -> list[dict[str, Any]]:
    """Get comments on a post, oldest first. Cursor-based pagination."""
    try:
        oid = ObjectId(post_id)
    except Exception:
        return []
    query: dict[str, Any] = {"postId": oid}
    if cursor:
        try:
            cursor_oid = ObjectId(cursor)
            query["_id"] = {"$gt": cursor_oid}
        except Exception:
            pass
    comments_cursor = _comments().find(query).sort("_id", 1).limit(limit)
    return [doc async for doc in comments_cursor]


# ── Events ──────────────────────────────────────────────────────────────


def _events():
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db.events


async def create_event(
    uid: str, data: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Create an event. Requires a profile.
    Converts inviteeUids to invitees with status=pending.
    """
    async with await _client.start_session() as session:
        async with session.start_transaction():
            profile = await _profiles().find_one({"_id": uid}, session=session)
            if profile is None:
                return None

            invitee_uids = data.get("inviteeUids", []) or []
            invitees = [{"uid": u, "status": "pending"} for u in invitee_uids]

            doc = {
                "creatorUid": uid,
                "title": data["title"],
                "description": data.get("description"),
                "location": data.get("location"),
                "startTime": data["startTime"],
                "endTime": data.get("endTime"),
                "rrule": data.get("rrule"),
                "invitees": invitees,
            }
            result = await _events().insert_one(doc, session=session)
            doc["_id"] = result.inserted_id
            return doc


async def get_event(event_id: str) -> dict[str, Any] | None:
    """Get a single event by ID."""
    try:
        oid = ObjectId(event_id)
    except Exception:
        return None
    return await _events().find_one({"_id": oid})


async def get_user_events(uid: str) -> list[dict[str, Any]]:
    """Get events created by a user, sorted by startTime."""
    cursor = _events().find({"creatorUid": uid}).sort("startTime", 1)
    return [doc async for doc in cursor]


async def get_invited_events(uid: str) -> list[dict[str, Any]]:
    """Get events a user is invited to, sorted by startTime."""
    cursor = _events().find({"invitees.uid": uid}).sort("startTime", 1)
    return [doc async for doc in cursor]


async def delete_event(event_id: str, uid: str) -> bool:
    """Delete an event. Only the creator can delete."""
    try:
        oid = ObjectId(event_id)
    except Exception:
        return False
    result = await _events().delete_one({"_id": oid, "creatorUid": uid})
    return result.deleted_count > 0


async def rsvp_event(
    event_id: str, uid: str, status: str
) -> dict[str, Any] | None:
    """
    Set RSVP status for a user on an event.
    Returns updated event or None if not found/not invited.
    """
    try:
        oid = ObjectId(event_id)
    except Exception:
        return None
    result = await _events().find_one_and_update(
        {"_id": oid, "invitees.uid": uid},
        {"$set": {"invitees.$.status": status}},
        return_document=True,
    )
    return result
