"""
Event-listener service.

Watches MongoDB change streams on three collections and publishes events
to durable RabbitMQ queues for downstream consumers.

Queues published to:
    profile.deleted  — a profile was soft-deleted
    post.created     — a new post was inserted
    post.deleted     — a post was soft-deleted
    follow.created   — a follow relationship was created
    follow.deleted   — a follow relationship was removed (soft or hard delete)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from .publisher import connect_rabbitmq, setup_queues, publish

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MONGO_URI = os.environ["MONGO_URI"]
MONGO_DB = os.environ.get("MONGO_DB", "fervora")
RABBITMQ_URL = os.environ["RABBITMQ_URL"]
REDIS_URL = os.environ["REDIS_URL"]


# ── Resume token helpers ──────────────────────────────────────────────────────

def _token_key(collection: str) -> str:
    return f"listener:token:{collection}"


async def _load_token(redis: Redis, collection: str):
    raw = await redis.get(_token_key(collection))
    return json.loads(raw) if raw else None


async def _save_token(redis: Redis, collection: str, token) -> None:
    await redis.set(_token_key(collection), json.dumps(token))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Watchers ──────────────────────────────────────────────────────────────────

async def watch_profiles(db, channel, redis) -> None:
    """Publish profile.deleted whenever isDeleted is set to True."""
    pipeline = [{"$match": {
        "operationType": "update",
        "updateDescription.updatedFields.isDeleted": True,
    }}]

    while True:
        try:
            token = await _load_token(redis, "profiles")
            kwargs = {"resume_after": token} if token else {}

            async with db.profiles.watch(pipeline, full_document="updateLookup", **kwargs) as stream:
                logger.info("listening to profiles collection ...")
                async for change in stream:
                    doc = change.get("fullDocument") or {}
                    user_id = doc.get("_id") or str(change["documentKey"]["_id"])
                    payload = {
                        "event": "profile.deleted",
                        "userId": user_id,
                        "timestamp": _now(),
                    }
                    await publish(channel, "profile.deleted", payload)
                    logger.info("profile.deleted  userId=%s", user_id)
                    # Save token only after successful publish → at-least-once guarantee.
                    await _save_token(redis, "profiles", change["_id"])

        except Exception as exc:
            logger.error("watch_profiles error: %s — reconnecting in 5 s", exc)
            await asyncio.sleep(5)


async def watch_posts(db, channel, redis) -> None:
    """Publish post.created on insert and post.deleted on soft-delete."""
    pipeline = [{"$match": {
        "$or": [
            {"operationType": "insert"},
            {
                "operationType": "update",
                "updateDescription.updatedFields.isDeleted": True,
            },
        ],
    }}]

    while True:
        try:
            token = await _load_token(redis, "posts")
            kwargs = {"resume_after": token} if token else {}

            async with db.posts.watch(pipeline, full_document="updateLookup", **kwargs) as stream:
                logger.info("listening to posts collection ...")
                async for change in stream:
                    op = change["operationType"]
                    doc = change.get("fullDocument") or {}
                    post_id = str(change["documentKey"]["_id"])

                    if op == "insert":
                        payload = {
                            "event": "post.created",
                            "postId": post_id,
                            "authorUid": doc.get("authorUid"),
                            "timestamp": _now(),
                        }
                        await publish(channel, "post.created", payload)
                        logger.info("post.created    postId=%s authorUid=%s", post_id, payload["authorUid"])
                    else:
                        payload = {
                            "event": "post.deleted",
                            "postId": post_id,
                            "authorUid": doc.get("authorUid"),
                            "timestamp": _now(),
                        }
                        await publish(channel, "post.deleted", payload)
                        logger.info("post.deleted    postId=%s", post_id)

                    # Save token only after successful publish → at-least-once guarantee.
                    await _save_token(redis, "posts", change["_id"])

        except Exception as exc:
            logger.error("watch_posts error: %s — reconnecting in 5 s", exc)
            await asyncio.sleep(5)


async def watch_follows(db, channel, redis) -> None:
    """Publish follow.created on insert and follow.deleted on soft/hard delete."""
    pipeline = [{"$match": {
        "$or": [
            {"operationType": "insert"},
            {
                "operationType": "update",
                "updateDescription.updatedFields.isDeleted": True,
            },
            {"operationType": "delete"},
        ],
    }}]

    while True:
        try:
            token = await _load_token(redis, "follows")
            kwargs = {"resume_after": token} if token else {}

            async with db.follows.watch(pipeline, full_document="updateLookup", **kwargs) as stream:
                logger.info("listening to follows collection ...")
                async for change in stream:
                    op = change["operationType"]
                    doc = change.get("fullDocument") or {}

                    if op == "insert":
                        payload = {
                            "event": "follow.created",
                            "followerUid": doc.get("followerUid"),
                            "followingUid": doc.get("followingUid"),
                            "timestamp": _now(),
                        }
                        await publish(channel, "follow.created", payload)
                        logger.info(
                            "follow.created  followerUid=%s followingUid=%s",
                            payload["followerUid"], payload["followingUid"],
                        )
                    elif op == "delete":
                        # Hard delete: no document data, emit with the raw follow ID
                        payload = {
                            "event": "follow.deleted",
                            "followId": str(change["documentKey"]["_id"]),
                            "timestamp": _now(),
                        }
                        await publish(channel, "follow.deleted", payload)
                        logger.info("follow.deleted  (hard-delete) followId=%s", payload["followId"])
                    else:
                        # Soft delete (update with isDeleted: true)
                        payload = {
                            "event": "follow.deleted",
                            "followerUid": doc.get("followerUid"),
                            "followingUid": doc.get("followingUid"),
                            "timestamp": _now(),
                        }
                        await publish(channel, "follow.deleted", payload)
                        logger.info(
                            "follow.deleted  followerUid=%s followingUid=%s",
                            payload.get("followerUid"), payload.get("followingUid"),
                        )

                    # Save token only after successful publish → at-least-once guarantee.
                    await _save_token(redis, "follows", change["_id"])

        except Exception as exc:
            logger.error("watch_follows error: %s — reconnecting in 5 s", exc)
            await asyncio.sleep(5)


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("connecting to MongoDB at %s ...", MONGO_URI)
    mongo = AsyncIOMotorClient(MONGO_URI)
    db = mongo[MONGO_DB]

    logger.info("connecting to Redis at %s ...", REDIS_URL)
    redis = Redis.from_url(REDIS_URL, decode_responses=True)

    logger.info("connecting to RabbitMQ at %s ...", RABBITMQ_URL)
    conn = await connect_rabbitmq(RABBITMQ_URL)
    channel = await conn.channel()
    await setup_queues(channel)

    logger.info("all connections established — starting change stream watchers")
    await asyncio.gather(
        watch_profiles(db, channel, redis),
        watch_posts(db, channel, redis),
        watch_follows(db, channel, redis),
    )


if __name__ == "__main__":
    asyncio.run(main())
