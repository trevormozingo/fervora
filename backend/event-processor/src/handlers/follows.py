"""Follow event handlers."""

import logging
from datetime import datetime, timezone
from typing import Any

from . import register
from ..database import get_db

logger = logging.getLogger(__name__)

BACKFILL_LIMIT = 20


async def _backfill_feed(follower_uid: str, followed_uid: str) -> None:
    """Seed the follower's feed with the last N posts from the followed user."""
    db = get_db()
    cursor = (
        db.posts.find({"authorUid": followed_uid, "isDeleted": {"$ne": True}})
        .sort("createdAt", -1)
        .limit(BACKFILL_LIMIT)
    )
    posts = await cursor.to_list(length=BACKFILL_LIMIT)
    if not posts:
        return

    now = datetime.now(timezone.utc).isoformat()
    from pymongo import UpdateOne
    ops = [
        UpdateOne(
            {"ownerUid": follower_uid, "postId": p["_id"]},
            {
                "$set": {"isDeleted": False, "authorUid": followed_uid, "createdAt": now},
                "$unset": {"deletedAt": ""},
            },
            upsert=True,
        )
        for p in posts
    ]
    result = await db.feed.bulk_write(ops)
    logger.info("Backfilled %d posts into %s's feed from %s (upserted=%d, modified=%d)",
                len(ops), follower_uid, followed_uid, result.upserted_count, result.modified_count)


async def _soft_delete_feed_entries(follower_uid: str, followed_uid: str) -> None:
    """Soft-delete all feed entries authored by followed_uid from follower's feed."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    result = await db.feed.update_many(
        {"ownerUid": follower_uid, "authorUid": followed_uid, "isDeleted": {"$ne": True}},
        {"$set": {"isDeleted": True, "deletedAt": now}},
    )
    logger.info("Soft-deleted %d feed entries for %s from %s", result.modified_count, follower_uid, followed_uid)


@register("follows", "insert")
async def on_follow_created(event: dict[str, Any]) -> None:
    """A new follow relationship was created — backfill feed."""
    doc = event.get("fullDocument", {})
    follower = doc.get("followerId")
    followed = doc.get("followedId")
    logger.info("New follow: %s -> %s", follower, followed)
    await _backfill_feed(follower, followed)


@register("follows", "update")
async def on_follow_updated(event: dict[str, Any]) -> None:
    """A follow was re-activated or soft-deleted (unfollow)."""
    doc = event.get("fullDocument", {})
    follower = doc.get("followerId")
    followed = doc.get("followedId")

    if doc.get("isDeleted"):
        logger.info("Unfollow: %s -> %s", follower, followed)
        await _soft_delete_feed_entries(follower, followed)
        return

    logger.info("Re-follow: %s -> %s", follower, followed)
    await _backfill_feed(follower, followed)
