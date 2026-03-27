import logging
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import BulkWriteError

from .storage import delete_storage_url

logger = logging.getLogger(__name__)

TTL = 3600  # 1 hour — must match profile-service/src/cache.py


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def handle_post_created(data: dict, db, redis) -> None:
    post_id = data["postId"]
    author_uid = data["authorUid"]
    created_at = _now()

    # Verify the post exists and isn't deleted before fanning out.
    post = await db.posts.find_one({"_id": ObjectId(post_id), "isDeleted": {"$ne": True}}, {"_id": 1})
    if not post:
        logger.warning("post.created  post not found or already deleted  postId=%s", post_id)
        return

    follower_ids = []
    async for doc in db.follows.find(
        {"followingUid": author_uid, "isDeleted": {"$ne": True}},
        {"followerUid": 1},
    ):
        follower_ids.append(doc["followerUid"])

    if follower_ids:
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
            if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
                raise
    else:
        logger.debug("post.created  no followers  authorUid=%s", author_uid)

    logger.info(
        "post.created  fanned out postId=%s to %d followers",
        post_id, len(follower_ids),
    )


async def handle_post_deleted(data: dict, db, redis) -> None:
    post_id = data["postId"]
    soft_delete = {"$set": {"isDeleted": True}}

    # Collect IDs before updating so we can tombstone their cache entries.
    comment_ids, reaction_ids = [], []
    async for doc in db.comments.find({"postId": post_id}, {"_id": 1}):
        comment_ids.append(str(doc["_id"]))
    async for doc in db.reactions.find({"postId": post_id}, {"_id": 1}):
        reaction_ids.append(str(doc["_id"]))

    r_feed = await db.feed.update_many({"postId": post_id}, soft_delete)
    r_comments = await db.comments.update_many({"postId": post_id}, soft_delete)
    r_reactions = await db.reactions.update_many({"postId": post_id}, soft_delete)

    try:
        async with redis.pipeline() as pipe:
            pipe.setex(f"post:{post_id}", TTL, "__nil__")
            for cid in comment_ids:
                pipe.setex(f"comment:{cid}", TTL, "__nil__")
            for rid in reaction_ids:
                pipe.setex(f"reaction:{rid}", TTL, "__nil__")
            await pipe.execute()
    except Exception as exc:
        logger.error("post.deleted  redis cleanup failed  error=%s", exc)

    logger.info(
        "post.deleted  soft-deleted feed=%d comments=%d reactions=%d  postId=%s",
        r_feed.modified_count, r_comments.modified_count, r_reactions.modified_count, post_id,
    )

    # Delete any Firebase Storage blobs attached to this post.
    post_doc = await db.posts.find_one({"_id": ObjectId(post_id)}, {"media": 1})
    if post_doc and post_doc.get("media"):
        for item in post_doc["media"]:
            if item.get("url"):
                await delete_storage_url(item["url"])


async def handle_profile_deleted(data: dict, db, redis) -> None:
    user_id = data["userId"]
    soft_delete = {"$set": {"isDeleted": True}}

    post_ids = []
    async for doc in db.posts.find({"authorUid": user_id}, {"_id": 1}):
        post_ids.append(str(doc["_id"]))

    comment_ids, reaction_ids = [], []
    if post_ids:
        async for doc in db.comments.find({"postId": {"$in": post_ids}}, {"_id": 1}):
            comment_ids.append(str(doc["_id"]))
        async for doc in db.reactions.find({"postId": {"$in": post_ids}}, {"_id": 1}):
            reaction_ids.append(str(doc["_id"]))

    async for doc in db.comments.find({"authorUid": user_id}, {"_id": 1}):
        cid = str(doc["_id"])
        if cid not in comment_ids:
            comment_ids.append(cid)
    async for doc in db.reactions.find({"authorUid": user_id}, {"_id": 1}):
        rid = str(doc["_id"])
        if rid not in reaction_ids:
            reaction_ids.append(rid)

    r_posts     = await db.posts.update_many({"authorUid": user_id}, soft_delete)
    r_comments  = await db.comments.update_many(
        {"$or": [{"authorUid": user_id}, {"postId": {"$in": post_ids}}]}, soft_delete
    )
    r_reactions = await db.reactions.update_many(
        {"$or": [{"authorUid": user_id}, {"postId": {"$in": post_ids}}]}, soft_delete
    )
    r_events    = await db.events.update_many({"organizerUid": user_id}, soft_delete)
    r_rsvps     = await db.rsvps.update_many({"userId": user_id}, soft_delete)
    r_follows   = await db.follows.update_many(
        {"$or": [{"followerUid": user_id}, {"followingUid": user_id}]}, soft_delete
    )
    r_feed      = await db.feed.update_many(
        {"$or": [{"authorUid": user_id}, {"followerUid": user_id}]}, soft_delete
    )

    try:
        async with redis.pipeline() as pipe:
            pipe.setex(f"profile:{user_id}", TTL, "__nil__")
            for pid in post_ids:
                pipe.setex(f"post:{pid}", TTL, "__nil__")
            for cid in comment_ids:
                pipe.setex(f"comment:{cid}", TTL, "__nil__")
            for rid in reaction_ids:
                pipe.setex(f"reaction:{rid}", TTL, "__nil__")
            await pipe.execute()
    except Exception as exc:
        logger.error("profile.deleted  redis cleanup failed  error=%s", exc)

    logger.info(
        "profile.deleted  userId=%s  posts=%d comments=%d reactions=%d "
        "events=%d rsvps=%d follows=%d feed=%d",
        user_id,
        r_posts.modified_count, r_comments.modified_count, r_reactions.modified_count,
        r_events.modified_count, r_rsvps.modified_count, r_follows.modified_count,
        r_feed.modified_count,
    )

    # Delete the profile photo from Firebase Storage.
    profile_doc = await db.profiles.find_one({"_id": user_id}, {"profilePhoto": 1})
    if profile_doc and profile_doc.get("profilePhoto"):
        await delete_storage_url(profile_doc["profilePhoto"])

async def handle_follow_created(data: dict, db, redis) -> None:
    BACKFILL_LIMIT = 50

    follower_uid = data["followerUid"]
    following_uid = data["followingUid"]

    posts = await db.posts.find(
        {"authorUid": following_uid, "isDeleted": {"$ne": True}},
        {"_id": 1, "createdAt": 1},
    ).sort("createdAt", -1).limit(BACKFILL_LIMIT).to_list(BACKFILL_LIMIT)

    if not posts:
        logger.debug("follow.created  no posts to backfill  followingUid=%s", following_uid)
        return

    docs = [
        {
            "followerUid": follower_uid,
            "postId": str(post["_id"]),
            "authorUid": following_uid,
            "createdAt": post["createdAt"],
        }
        for post in posts
    ]

    try:
        await db.feed.insert_many(docs, ordered=False)
    except BulkWriteError as exc:
        if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
            raise

    logger.info(
        "follow.created  backfilled %d posts for followerUid=%s from followingUid=%s",
        len(posts), follower_uid, following_uid,
    )

async def handle_follow_deleted(data: dict, db, redis) -> None:
    follower_uid = data.get("followerUid")
    following_uid = data.get("followingUid")

    if not follower_uid or not following_uid:
        # Hard-delete only carries a followId with no UIDs — nothing we can do.
        logger.warning("follow.deleted  missing UIDs, cannot purge feed  data=%s", data)
        return

    r = await db.feed.update_many(
        {"followerUid": follower_uid, "authorUid": following_uid},
        {"$set": {"isDeleted": True}},
    )

    logger.info(
        "follow.deleted  purged %d feed entries for followerUid=%s from followingUid=%s",
        r.modified_count, follower_uid, following_uid,
    )


