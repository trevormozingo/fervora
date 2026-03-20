"""Post event handlers."""

import logging
from datetime import datetime, timezone
from typing import Any

from . import register
from ..database import get_db

logger = logging.getLogger(__name__)


@register("posts", "insert")
async def on_post_created(event: dict[str, Any]) -> None:
    """A new post was created — fan out to all followers' feeds."""
    doc = event.get("fullDocument", {})
    post_id = event["documentKey"]
    author = doc.get("authorUid")
    created_at = doc.get("createdAt", datetime.now(timezone.utc).isoformat())
    logger.info("Post created: id=%s author=%s", post_id, author)

    db = get_db()
    cursor = db.follows.find(
        {"followedId": author, "isDeleted": {"$ne": True}},
        {"followerId": 1},
    )
    follower_ids = [d["followerId"] async for d in cursor]

    if not follower_ids:
        return

    from pymongo import UpdateOne
    ops = [
        UpdateOne(
            {"ownerUid": fid, "postId": post_id},
            {
                "$set": {"isDeleted": False, "authorUid": author, "createdAt": created_at},
                "$unset": {"deletedAt": ""},
            },
            upsert=True,
        )
        for fid in follower_ids
    ]
    result = await db.feed.bulk_write(ops)
    logger.info("Fan-out post %s to %d followers (upserted=%d, modified=%d)",
                post_id, len(follower_ids), result.upserted_count, result.modified_count)


@register("posts", "update")
async def on_post_updated(event: dict[str, Any]) -> None:
    """A post was soft-deleted — remove from all feeds."""
    doc = event.get("fullDocument", {})
    post_id = event["documentKey"]

    if doc.get("isDeleted"):
        logger.info("Post deleted: id=%s author=%s", post_id, doc.get("authorUid"))
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        result = await db.feed.update_many(
            {"postId": post_id, "isDeleted": {"$ne": True}},
            {"$set": {"isDeleted": True, "deletedAt": now}},
        )
        logger.info("Soft-deleted %d feed entries for post %s", result.modified_count, post_id)
        return

    logger.info("Post updated: id=%s", post_id)
