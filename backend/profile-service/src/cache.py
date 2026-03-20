"""Redis read-through cache for entities and computed aggregations."""

import hashlib
import json

import redis.asyncio as redis

_redis: redis.Redis | None = None

ENTITY_TTL = 300   # 5 minutes — single-entity documents
COUNT_TTL = 300     # 5 minutes — computed aggregations


async def connect(redis_url: str) -> None:
    global _redis
    _redis = redis.from_url(redis_url, decode_responses=True)


async def disconnect() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
    _redis = None


def _get_redis() -> redis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not connected")
    return _redis


# ── Entity cache helpers ──────────────────────────────────────────────

_NOT_FOUND = "__nil__"  # sentinel so we cache 404s and don't re-query


async def _get_entity(cache_key: str, fetch, ttl: int = ENTITY_TTL) -> dict | None:
    """Generic read-through: try Redis, fall back to *fetch()* from Mongo."""
    r = _get_redis()
    cached = await r.get(cache_key)
    if cached is not None:
        return None if cached == _NOT_FOUND else json.loads(cached)

    doc = await fetch()
    if doc is None:
        await r.set(cache_key, _NOT_FOUND, ex=ttl)
        return None
    await r.set(cache_key, json.dumps(doc, default=str), ex=ttl)
    return doc


async def _invalidate(cache_key: str) -> None:
    await _get_redis().delete(cache_key)


# ── Profile entity cache ─────────────────────────────────────────────

async def get_profile(uid: str, db) -> dict | None:
    async def _fetch():
        return await db.profiles.find_one({"_id": uid, "isDeleted": {"$ne": True}})
    return await _get_entity(f"profile:{uid}", _fetch)


async def invalidate_profile(uid: str) -> None:
    await _invalidate(f"profile:{uid}")


# ── Post entity cache ────────────────────────────────────────────────

async def get_post(post_id: str, db) -> dict | None:
    async def _fetch():
        return await db.posts.find_one({"_id": post_id, "isDeleted": {"$ne": True}})
    return await _get_entity(f"post:{post_id}", _fetch)


async def list_posts_by_author(author_uid: str, db, limit: int = 50) -> list[dict]:
    """Read-through cache for a user's post list."""
    r = _get_redis()
    cache_key = f"post_list:{author_uid}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    cursor = (
        db.posts.find({"authorUid": author_uid, "isDeleted": {"$ne": True}})
        .sort("createdAt", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    await r.set(cache_key, json.dumps(docs, default=str), ex=ENTITY_TTL)
    return docs


async def invalidate_post(post_id: str) -> None:
    await _invalidate(f"post:{post_id}")


async def invalidate_post_list(author_uid: str) -> None:
    await _invalidate(f"post_list:{author_uid}")


# ── Comment entity cache ─────────────────────────────────────────────

async def get_comment(comment_id: str, db) -> dict | None:
    async def _fetch():
        return await db.comments.find_one({"_id": comment_id, "isDeleted": {"$ne": True}})
    return await _get_entity(f"comment:{comment_id}", _fetch)


async def list_comments_by_post(post_id: str, db, limit: int = 50) -> list[dict]:
    """Read-through cache for a post's comment list."""
    r = _get_redis()
    cache_key = f"comment_list:{post_id}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    cursor = (
        db.comments.find({"postId": post_id, "isDeleted": {"$ne": True}})
        .sort("createdAt", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    await r.set(cache_key, json.dumps(docs, default=str), ex=ENTITY_TTL)
    return docs


async def invalidate_comment(comment_id: str) -> None:
    await _invalidate(f"comment:{comment_id}")


async def invalidate_comment_list(post_id: str) -> None:
    await _invalidate(f"comment_list:{post_id}")


# ── Reaction list cache ───────────────────────────────────────────────

async def list_reactions_by_post(post_id: str, db, limit: int = 50) -> list[dict]:
    """Read-through cache for a post's reaction list."""
    r = _get_redis()
    cache_key = f"reaction_list:{post_id}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    cursor = (
        db.reactions.find({"postId": post_id, "isDeleted": {"$ne": True}})
        .sort("createdAt", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    await r.set(cache_key, json.dumps(docs, default=str), ex=ENTITY_TTL)
    return docs


async def invalidate_reaction_list(post_id: str) -> None:
    await _invalidate(f"reaction_list:{post_id}")


# ── Event entity cache ────────────────────────────────────────────────

async def get_event(event_id: str, db) -> dict | None:
    async def _fetch():
        return await db.events.find_one({"_id": event_id, "isDeleted": {"$ne": True}})
    return await _get_entity(f"event:{event_id}", _fetch)


async def list_events_by_author(author_uid: str, db, limit: int = 50) -> list[dict]:
    """Read-through cache for a user's event list."""
    r = _get_redis()
    cache_key = f"event_list:{author_uid}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    cursor = (
        db.events.find({"authorUid": author_uid, "isDeleted": {"$ne": True}})
        .sort("startTime", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    await r.set(cache_key, json.dumps(docs, default=str), ex=ENTITY_TTL)
    return docs


async def invalidate_event(event_id: str) -> None:
    await _invalidate(f"event:{event_id}")


async def invalidate_event_list(author_uid: str) -> None:
    await _invalidate(f"event_list:{author_uid}")


# ── Follow list cache ─────────────────────────────────────────────────

async def list_following(uid: str, db, limit: int = 500) -> list[str]:
    """Read-through cache for UIDs that a user follows."""
    r = _get_redis()
    cache_key = f"following:{uid}"

    cached = await r.get(cache_key)
    if cached is not None:
        return json.loads(cached)

    cursor = (
        db.follows.find({"followerId": uid, "isDeleted": {"$ne": True}}, {"followedId": 1})
        .sort("createdAt", -1)
        .limit(limit)
    )
    uids = [doc["followedId"] async for doc in cursor]
    await r.set(cache_key, json.dumps(uids), ex=ENTITY_TTL)
    return uids


async def list_followers(uid: str, db, limit: int = 500) -> list[str]:
    """Read-through cache for UIDs that follow a user."""
    r = _get_redis()
    cache_key = f"followers:{uid}"

    cached = await r.get(cache_key)
    if cached is not None:
        return json.loads(cached)

    cursor = (
        db.follows.find({"followedId": uid, "isDeleted": {"$ne": True}}, {"followerId": 1})
        .sort("createdAt", -1)
        .limit(limit)
    )
    uids = [doc["followerId"] async for doc in cursor]
    await r.set(cache_key, json.dumps(uids), ex=ENTITY_TTL)
    return uids


async def invalidate_following(uid: str) -> None:
    await _invalidate(f"following:{uid}")


async def invalidate_followers(uid: str) -> None:
    await _invalidate(f"followers:{uid}")


# ── Profile counts ───────────────────────────────────────────────────

async def get_profile_counts(uid: str, db) -> dict:
    """Return follower/following/post counts. Cache hit → Redis, miss → compute from MongoDB."""
    r = _get_redis()
    cache_key = f"profile_counts:{uid}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    counts = await _compute_counts(uid, db)
    await r.set(cache_key, json.dumps(counts), ex=COUNT_TTL)
    return counts


async def invalidate_profile_counts(uid: str) -> None:
    """Delete cached counts so the next read recomputes."""
    r = _get_redis()
    await r.delete(f"profile_counts:{uid}")


async def _compute_counts(uid: str, db) -> dict:
    """Count from source collections. Returns 0 if collections don't exist yet."""
    followers = 0
    following = 0
    posts = 0

    collections = await db.list_collection_names()

    if "follows" in collections:
        followers = await db.follows.count_documents({"followedId": uid, "isDeleted": {"$ne": True}})
        following = await db.follows.count_documents({"followerId": uid, "isDeleted": {"$ne": True}})

    if "posts" in collections:
        posts = await db.posts.count_documents(
            {"authorUid": uid, "isDeleted": {"$ne": True}}
        )

    return {
        "followersCount": followers,
        "followingCount": following,
        "postCount": posts,
    }


# ── Post aggregations ────────────────────────────────────────────────

async def get_post_counts(post_id: str, db) -> dict:
    """Return reaction summary and comment count for a post."""
    r = _get_redis()
    cache_key = f"post_counts:{post_id}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    counts = await _compute_post_counts(post_id, db)
    await r.set(cache_key, json.dumps(counts), ex=COUNT_TTL)
    return counts


async def get_my_reaction(post_id: str, viewer_uid: str, db) -> str | None:
    """Return the viewer's reaction type on a post, or None."""
    r = _get_redis()
    cache_key = f"post_reaction:{post_id}:{viewer_uid}"

    cached = await r.get(cache_key)
    if cached is not None:
        return None if cached == "" else cached

    reaction = await _compute_my_reaction(post_id, viewer_uid, db)
    # Store empty string for "no reaction" so we can distinguish cache miss from null
    await r.set(cache_key, reaction or "", ex=COUNT_TTL)
    return reaction


async def get_recent_comments(post_id: str, db, limit: int = 3) -> list[dict]:
    """Return the most recent comments on a post."""
    r = _get_redis()
    cache_key = f"post_comments:{post_id}"

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    comments = await _compute_recent_comments(post_id, db, limit)
    await r.set(cache_key, json.dumps(comments), ex=COUNT_TTL)
    return comments


async def invalidate_post_counts(post_id: str) -> None:
    """Delete cached post counts so the next read recomputes."""
    r = _get_redis()
    await r.delete(f"post_counts:{post_id}")


async def invalidate_post_comments(post_id: str) -> None:
    """Delete cached recent comments."""
    r = _get_redis()
    await r.delete(f"post_comments:{post_id}")


async def invalidate_post_reaction(post_id: str, viewer_uid: str) -> None:
    """Delete a user's cached reaction on a post."""
    r = _get_redis()
    await r.delete(f"post_reaction:{post_id}:{viewer_uid}")


# ── Feed cache ────────────────────────────────────────────────────────

async def get_feed_page(
    owner_uid: str, db, following_uids: list[str],
    limit: int = 20, cursor: str | None = None,
) -> list[dict]:
    """Read-through cache for a feed page. Returns list of {postId, createdAt} dicts."""
    if not following_uids:
        return []

    r = _get_redis()
    # Include a hash of the following list so cache busts when follows change
    fh = hashlib.md5("|".join(sorted(following_uids)).encode()).hexdigest()[:8]
    cache_key = f"feed:{owner_uid}:{cursor or ''}:{limit}:{fh}"

    cached = await r.get(cache_key)
    if cached is not None:
        return json.loads(cached)

    query: dict = {
        "ownerUid": owner_uid,
        "isDeleted": {"$ne": True},
        "authorUid": {"$in": following_uids},
    }
    if cursor:
        query["createdAt"] = {"$lt": cursor}

    feed_cursor = (
        db.feed.find(query, {"postId": 1, "createdAt": 1, "_id": 0})
        .sort("createdAt", -1)
        .limit(limit)
    )
    docs = await feed_cursor.to_list(length=limit)
    await r.set(cache_key, json.dumps(docs, default=str), ex=ENTITY_TTL)
    return docs


async def invalidate_feed(owner_uid: str) -> None:
    """Delete all cached feed pages for a user."""
    r = _get_redis()
    async for key in r.scan_iter(match=f"feed:{owner_uid}:*"):
        await r.delete(key)


async def _compute_post_counts(post_id: str, db) -> dict:
    """Aggregate reaction summary and comment count from source collections."""
    reaction_summary: dict[str, int] = {}
    comment_count = 0

    collections = await db.list_collection_names()

    if "reactions" in collections:
        pipeline = [
            {"$match": {"postId": post_id, "isDeleted": {"$ne": True}}},
            {"$group": {"_id": "$reactionType", "count": {"$sum": 1}}},
        ]
        async for doc in db.reactions.aggregate(pipeline):
            reaction_summary[doc["_id"]] = doc["count"]

    if "comments" in collections:
        comment_count = await db.comments.count_documents(
            {"postId": post_id, "isDeleted": {"$ne": True}}
        )

    return {
        "reactionSummary": reaction_summary,
        "commentCount": comment_count,
    }


async def _compute_my_reaction(post_id: str, viewer_uid: str, db) -> str | None:
    collections = await db.list_collection_names()
    if "reactions" not in collections:
        return None
    doc = await db.reactions.find_one(
        {"postId": post_id, "authorUid": viewer_uid, "isDeleted": {"$ne": True}}
    )
    return doc["reactionType"] if doc else None


async def _compute_recent_comments(post_id: str, db, limit: int = 3) -> list[dict]:
    collections = await db.list_collection_names()
    if "comments" not in collections:
        return []
    cursor = (
        db.comments.find({"postId": post_id, "isDeleted": {"$ne": True}})
        .sort("createdAt", -1)
        .limit(limit)
    )
    results = []
    async for doc in cursor:
        results.append({
            "id": doc["_id"],
            "authorUid": doc.get("authorUid"),
            "body": doc.get("body"),
            "createdAt": doc.get("createdAt"),
        })
    return results
