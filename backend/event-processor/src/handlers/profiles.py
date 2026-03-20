"""Profile event handlers."""

import logging
from datetime import datetime, timezone
from typing import Any

from . import register
from ..database import get_db

logger = logging.getLogger(__name__)


async def _cascade_soft_delete(uid: str) -> None:
    """Soft-delete all data owned/authored by a deleted profile."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    update = {"$set": {"isDeleted": True, "deletedAt": now}}
    active = {"isDeleted": {"$ne": True}}

    # Entities authored by this user
    posts = await db.posts.update_many({"authorUid": uid, **active}, update)
    comments_authored = await db.comments.update_many({"authorUid": uid, **active}, update)
    reactions_authored = await db.reactions.update_many({"authorUid": uid, **active}, update)
    events = await db.events.update_many({"authorUid": uid, **active}, update)

    # Comments and reactions on the user's posts (now soft-deleted)
    deleted_post_ids = [
        str(p["_id"])
        async for p in db.posts.find({"authorUid": uid, "isDeleted": True}, {"_id": 1})
    ]
    comments_on_posts = await db.comments.update_many(
        {"postId": {"$in": deleted_post_ids}, **active}, update
    ) if deleted_post_ids else type("R", (), {"modified_count": 0})()
    reactions_on_posts = await db.reactions.update_many(
        {"postId": {"$in": deleted_post_ids}, **active}, update
    ) if deleted_post_ids else type("R", (), {"modified_count": 0})()

    # Follows in both directions
    follows_as_follower = await db.follows.update_many({"followerId": uid, **active}, update)
    follows_as_followed = await db.follows.update_many({"followedId": uid, **active}, update)

    # Feed entries authored by or owned by this user
    feed_authored = await db.feed.update_many({"authorUid": uid, **active}, update)
    feed_owned = await db.feed.update_many({"ownerUid": uid, **active}, update)

    logger.info(
        "Profile delete cascade for %s: posts=%d comments=%d+%d reactions=%d+%d "
        "events=%d follows=%d+%d feed=%d+%d",
        uid, posts.modified_count,
        comments_authored.modified_count, comments_on_posts.modified_count,
        reactions_authored.modified_count, reactions_on_posts.modified_count,
        events.modified_count,
        follows_as_follower.modified_count, follows_as_followed.modified_count,
        feed_authored.modified_count, feed_owned.modified_count,
    )


@register("profiles", "insert")
async def on_profile_created(event: dict[str, Any]) -> None:
    """A new profile was created."""
    doc = event.get("fullDocument", {})
    uid = event["documentKey"]
    logger.info("Profile created: uid=%s username=%s", uid, doc.get("username"))


@register("profiles", "update")
async def on_profile_updated(event: dict[str, Any]) -> None:
    """A profile was updated or soft-deleted."""
    doc = event.get("fullDocument", {})
    uid = event["documentKey"]

    if doc.get("isDeleted"):
        logger.info("Profile deleted: uid=%s", uid)
        await _cascade_soft_delete(uid)
        return

    updated = event.get("updatedFields", {})
    logger.info("Profile updated: uid=%s fields=%s", uid, list(updated.keys()))
