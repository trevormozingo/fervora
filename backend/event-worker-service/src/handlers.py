import logging
from datetime import datetime, timezone

from pymongo.errors import BulkWriteError

logger = logging.getLogger(__name__)

TTL = 3600  # 1 hour — must match profile-service/src/cache.py


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def handle_post_created(data: dict, db, redis) -> None:
    """
    Fan-out a new post to the feed of every follower of the author.
    Inserts one document per follower into the `feed` collection
    AND updates the user's feed in Redis (ZSET).
    """
    post_id = data["postId"]
    author_uid = data["authorUid"]
    created_at = _now()
    timestamp = created_at.timestamp()

    # 1. Verify Post Exists & Isn't Deleted
    post = await db.posts.find_one({"_id": post_id, "isDeleted": {"$ne": True}}, {"_id": 1})
    if not post:
        logger.warning("post.created  post not found or already deleted  postId=%s", post_id)
        return

    # 2. Find All Followers
    follower_ids = []
    async for doc in db.follows.find(
        {"followingUid": author_uid, "isDeleted": {"$ne": True}},
        {"followerUid": 1},
    ):
        follower_ids.append(doc["followerUid"])

    if not follower_ids:
        logger.debug("post.created  no followers  authorUid=%s", author_uid)
        return

    # 3. Fan-out to MongoDB `feed` collection
    docs = [
        {
            "followerUid": fid,
            "postId": post_id,
            "authorUid": author_uid,
            "createdAt": created_at,
        }
        for fid in follower_ids
    ]

    try:
        await db.feed.insert_many(docs, ordered=False)
    except BulkWriteError as exc:
        # Duplicate key (E11000) means the entry already exists — safe to ignore.
        if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
            raise

    # 4. Fan-out to Redis Caches
    # Key: feed:{uid}  Score: timestamp  Member: postId
    # expire() resets the TTL each time a new post arrives, keeping active feeds warm.
    try:
        async with redis.pipeline() as pipe:
            for fid in follower_ids:
                key = f"feed:{fid}"
                pipe.zadd(key, {post_id: timestamp})
                pipe.expire(key, TTL)
            await pipe.execute()
    except Exception as exc:
        logger.error("post.created  redis fan-out failed  error=%s", exc)
        # We don't raise here because the persistent store (Mongo) succeeded.
        # Redis is just a cache.

    logger.info(
        "post.created  fanned out postId=%s to %d followers of authorUid=%s",
        post_id, len(follower_ids), author_uid,
    )


async def handle_post_deleted(data: dict, db, redis) -> None:
    """
    Soft-delete all feed entries, comments, and reactions referencing the deleted post.
    Also tombstones individual document caches and removes the post from feed ZSETs.
    """
    post_id = data["postId"]
    soft_delete = {"$set": {"isDeleted": True}}

    # 1. Collect IDs for cache cleanup before the mongo updates.
    comment_ids, reaction_ids, follower_ids = [], [], []
    async for doc in db.comments.find({"postId": post_id}, {"_id": 1}):
        comment_ids.append(str(doc["_id"]))
    async for doc in db.reactions.find({"postId": post_id}, {"_id": 1}):
        reaction_ids.append(str(doc["_id"]))
    async for doc in db.feed.find({"postId": post_id}, {"followerUid": 1}):
        follower_ids.append(doc["followerUid"])

    # 2. Soft-delete in MongoDB.
    r_feed = await db.feed.update_many({"postId": post_id}, soft_delete)
    r_comments = await db.comments.update_many({"postId": post_id}, soft_delete)
    r_reactions = await db.reactions.update_many({"postId": post_id}, soft_delete)

    # 3. Update Redis: tombstone individual doc caches, remove from feed ZSETs.
    try:
        async with redis.pipeline() as pipe:
            for cid in comment_ids:
                pipe.setex(f"comment:{cid}", TTL, "__nil__")
            for rid in reaction_ids:
                pipe.setex(f"reaction:{rid}", TTL, "__nil__")
            for fid in follower_ids:
                pipe.zrem(f"feed:{fid}", post_id)
            await pipe.execute()
    except Exception as exc:
        logger.error("post.deleted  redis cleanup failed  error=%s", exc)

    logger.info(
        "post.deleted  soft-deleted feed=%d comments=%d reactions=%d  postId=%s",
        r_feed.modified_count, r_comments.modified_count, r_reactions.modified_count, post_id,
    )


# --- Stubs for other handlers to satisfy main.py imports ---

async def handle_profile_deleted(data: dict, db, redis) -> None:
    pass

async def handle_follow_created(data: dict, db, redis) -> None:
    pass

async def handle_follow_deleted(data: dict, db, redis) -> None:
    pass


