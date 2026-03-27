"""
Shared fixtures and helpers for the profile-service test suite.

Test isolation: every test gets its own in-memory MongoDB database and
FakeRedis instance, so no cleanup is needed between tests.
"""
from __future__ import annotations
import asyncio
import pytest
import mongomock_motor
import fakeredis.aioredis as aioredis
from bson import ObjectId

from src.main import schema
from src.cache import TTL
from src.loaders import (
    make_profile_loader,
    make_post_loader,
    make_reaction_summary_loader,
    make_viewer_reaction_loader,
    make_rsvp_summary_loader,
    make_viewer_rsvp_loader,
)

# ── Core fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mongo():
    client = mongomock_motor.AsyncMongoMockClient()
    return client["fervora_test"]


@pytest.fixture
async def redis():
    r = aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


def _make_ctx(db, redis, user_id=None):
    return {
        "user_id": user_id,
        "db": db,
        "redis": redis,
        "profile_loader": make_profile_loader(db, redis),
        "post_loader": make_post_loader(db, redis),
        "reaction_summary_loader": make_reaction_summary_loader(db),
        "viewer_reaction_loader": make_viewer_reaction_loader(db, user_id),
        "rsvp_summary_loader": make_rsvp_summary_loader(db),
        "viewer_rsvp_loader": make_viewer_rsvp_loader(db, user_id),
    }


@pytest.fixture
def gql(mongo, redis):
    """Execute a GraphQL operation.  Returns an ExecutionResult with .data and .errors."""
    async def execute(query: str, variables=None, user_id=None):
        return await schema.execute(
            query,
            variable_values=variables or {},
            context_value=_make_ctx(mongo, redis, user_id),
        )
    return execute


# ── Domain quick-create helpers (fixtures that return async callables) ────────

CREATE_PROFILE_MUT = """
mutation CreateProfile($input: CreateProfileInput!) {
  createProfile(input: $input) { id username displayName }
}
"""

CREATE_POST_MUT = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) { id title }
}
"""

CREATE_COMMENT_MUT = """
mutation CreateComment($input: CreateCommentInput!) {
  createComment(input: $input) { id body }
}
"""

SET_REACTION_MUT = """
mutation SetReaction($input: SetReactionInput!) {
  setReaction(input: $input) { id reactionType }
}
"""

CREATE_EVENT_MUT = """
mutation CreateEvent($input: CreateEventInput!) {
  createEvent(input: $input) { id title }
}
"""


@pytest.fixture
def make_profile(gql):
    async def _inner(uid: str, username: str = "testuser", overrides: dict | None = None) -> str:
        inp = {
            "username": username,
            "displayName": "Test User",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1990-01-01",
        }
        if overrides:
            inp.update(overrides)
        r = await gql(CREATE_PROFILE_MUT, {"input": inp}, user_id=uid)
        assert r.errors is None, r.errors
        return r.data["createProfile"]["id"]
    return _inner


@pytest.fixture
def make_post(gql, make_profile):
    async def _inner(uid: str, **extra) -> str:
        inp = {"title": "Test Workout", **extra}
        r = await gql(CREATE_POST_MUT, {"input": inp}, user_id=uid)
        assert r.errors is None, r.errors
        return r.data["createPost"]["id"]
    return _inner


@pytest.fixture
def make_comment(gql):
    async def _inner(uid: str, post_id: str, body: str = "Great post!") -> str:
        r = await gql(CREATE_COMMENT_MUT, {"input": {"postId": post_id, "body": body}}, user_id=uid)
        assert r.errors is None, r.errors
        return r.data["createComment"]["id"]
    return _inner


@pytest.fixture
def make_reaction(gql):
    async def _inner(uid: str, post_id: str, reaction_type: str = "fire") -> str:
        r = await gql(SET_REACTION_MUT, {"input": {"postId": post_id, "reactionType": reaction_type}}, user_id=uid)
        assert r.errors is None, r.errors
        return r.data["setReaction"]["id"]
    return _inner


@pytest.fixture
def make_event(gql):
    async def _inner(uid: str, **extra) -> str:
        inp = {"title": "Morning Run", "startsAt": "2026-04-01T07:00:00Z", **extra}
        r = await gql(CREATE_EVENT_MUT, {"input": inp}, user_id=uid)
        assert r.errors is None, r.errors
        return r.data["createEvent"]["id"]
    return _inner


# ── Worker cascade simulators ─────────────────────────────────────────────────

async def worker_cascade_post_deleted(db, redis, post_id: str) -> None:
    """Mirrors handle_post_deleted in event-worker-service."""
    comment_ids = [
        str(d["_id"]) async for d in db.comments.find({"postId": post_id}, {"_id": 1})
    ]
    reaction_ids = [
        str(d["_id"]) async for d in db.reactions.find({"postId": post_id}, {"_id": 1})
    ]
    await db.comments.update_many({"postId": post_id}, {"$set": {"isDeleted": True}})
    await db.reactions.update_many({"postId": post_id}, {"$set": {"isDeleted": True}})
    await db.feed.update_many({"postId": post_id}, {"$set": {"isDeleted": True}})

    pipe = redis.pipeline()
    pipe.setex(f"post:{post_id}", TTL, "__nil__")
    for cid in comment_ids:
        pipe.setex(f"comment:{cid}", TTL, "__nil__")
    for rid in reaction_ids:
        pipe.setex(f"reaction:{rid}", TTL, "__nil__")
    await pipe.execute()


async def worker_cascade_profile_deleted(db, redis, author_uid: str) -> None:
    """Mirrors handle_profile_deleted in event-worker-service."""
    post_ids = [str(d["_id"]) async for d in db.posts.find({"authorUid": author_uid}, {"_id": 1})]

    await db.posts.update_many({"authorUid": author_uid}, {"$set": {"isDeleted": True}})

    comment_ids = [str(d["_id"]) async for d in db.comments.find({"authorUid": author_uid}, {"_id": 1})]
    await db.comments.update_many({"authorUid": author_uid}, {"$set": {"isDeleted": True}})

    if post_ids:
        extra_cids = [
            str(d["_id"]) async for d in db.comments.find({"postId": {"$in": post_ids}}, {"_id": 1})
        ]
        await db.comments.update_many({"postId": {"$in": post_ids}}, {"$set": {"isDeleted": True}})
        comment_ids.extend(extra_cids)

    reaction_ids = [str(d["_id"]) async for d in db.reactions.find({"authorUid": author_uid}, {"_id": 1})]
    await db.reactions.update_many({"authorUid": author_uid}, {"$set": {"isDeleted": True}})

    if post_ids:
        extra_rids = [
            str(d["_id"]) async for d in db.reactions.find({"postId": {"$in": post_ids}}, {"_id": 1})
        ]
        await db.reactions.update_many({"postId": {"$in": post_ids}}, {"$set": {"isDeleted": True}})
        reaction_ids.extend(extra_rids)

    await db.events.update_many({"organizerUid": author_uid}, {"$set": {"isDeleted": True}})
    await db.rsvps.update_many({"userId": author_uid}, {"$set": {"isDeleted": True}})
    await db.follows.update_many(
        {"$or": [{"followerUid": author_uid}, {"followingUid": author_uid}]},
        {"$set": {"isDeleted": True}},
    )
    await db.feed.update_many(
        {"$or": [{"authorUid": author_uid}, {"followerUid": author_uid}]},
        {"$set": {"isDeleted": True}},
    )

    pipe = redis.pipeline()
    pipe.setex(f"profile:{author_uid}", TTL, "__nil__")
    for pid in post_ids:
        pipe.setex(f"post:{pid}", TTL, "__nil__")
    for cid in set(comment_ids):
        pipe.setex(f"comment:{cid}", TTL, "__nil__")
    for rid in set(reaction_ids):
        pipe.setex(f"reaction:{rid}", TTL, "__nil__")
    await pipe.execute()
