"""Feed pagination and resilience tests."""
import pytest
from bson import ObjectId
from datetime import datetime, timezone

FEED_Q = """
query Feed($limit: Int, $cursor: String) {
  feed(limit: $limit, cursor: $cursor) {
    posts { id title }
    nextCursor
  }
}
"""


async def _seed_feed(mongo, follower_uid: str, author_uid: str, count: int) -> list[str]:
    """Directly insert feed + post docs to test feed pagination without the worker."""
    post_ids = []
    for i in range(count):
        result = await mongo.posts.insert_one({
            "authorUid": author_uid,
            "title": f"Post {i}",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "isDeleted": False,
        })
        pid = str(result.inserted_id)
        post_ids.append(pid)
        await mongo.feed.insert_one({
            "followerUid": follower_uid,
            "postId": pid,
            "authorUid": author_uid,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        })
    return post_ids


async def test_feed_returns_posts(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await _seed_feed(mongo, "uid1", "uid2", 3)

    r = await gql(FEED_Q, {"limit": 10}, user_id="uid1")
    assert r.errors is None
    assert len(r.data["feed"]["posts"]) == 3

async def test_feed_empty(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(FEED_Q, {"limit": 10}, user_id="uid1")
    assert r.errors is None
    assert r.data["feed"]["posts"] == []
    assert r.data["feed"]["nextCursor"] is None

async def test_feed_pagination_cursor(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await _seed_feed(mongo, "uid1", "uid2", 5)

    # Page 1
    r1 = await gql(FEED_Q, {"limit": 3}, user_id="uid1")
    assert r1.errors is None
    assert len(r1.data["feed"]["posts"]) == 3
    cursor = r1.data["feed"]["nextCursor"]
    assert cursor is not None

    # Page 2
    r2 = await gql(FEED_Q, {"limit": 3, "cursor": cursor}, user_id="uid1")
    assert r2.errors is None
    assert len(r2.data["feed"]["posts"]) == 2
    assert r2.data["feed"]["nextCursor"] is None

async def test_feed_no_duplicate_posts_across_pages(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await _seed_feed(mongo, "uid1", "uid2", 6)

    r1 = await gql(FEED_Q, {"limit": 4}, user_id="uid1")
    r2 = await gql(FEED_Q, {"limit": 4, "cursor": r1.data["feed"]["nextCursor"]}, user_id="uid1")

    ids_p1 = {p["id"] for p in r1.data["feed"]["posts"]}
    ids_p2 = {p["id"] for p in r2.data["feed"]["posts"]}
    assert ids_p1.isdisjoint(ids_p2)

async def test_feed_filters_deleted_posts(gql, make_profile, mongo):
    """Feed entries pointing to soft-deleted posts are silently filtered out."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    post_ids = await _seed_feed(mongo, "uid1", "uid2", 3)

    # Soft-delete one post
    await mongo.posts.update_one({"_id": ObjectId(post_ids[0])}, {"$set": {"isDeleted": True}})

    r = await gql(FEED_Q, {"limit": 10}, user_id="uid1")
    assert r.errors is None
    assert len(r.data["feed"]["posts"]) == 2

async def test_feed_filters_hard_deleted_posts(gql, make_profile, mongo):
    """Feed entry pointing to a hard-deleted post (no document) is silently filtered."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    post_ids = await _seed_feed(mongo, "uid1", "uid2", 3)

    # Hard-delete one post
    await mongo.posts.delete_one({"_id": ObjectId(post_ids[0])})

    r = await gql(FEED_Q, {"limit": 10}, user_id="uid1")
    assert r.errors is None
    assert len(r.data["feed"]["posts"]) == 2

async def test_feed_requires_auth(gql):
    r = await gql(FEED_Q, {"limit": 10}, user_id=None)
    assert r.errors is not None
    assert "authentication required" in r.errors[0].message

async def test_feed_invalid_cursor_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(FEED_Q, {"limit": 5, "cursor": "not-a-valid-object-id"}, user_id="uid1")
    assert r.errors is not None
    assert "invalid cursor" in r.errors[0].message

async def test_feed_post_loader_hydrates_full_post(gql, make_profile, make_post, mongo):
    """Feed entries hydrate the full Post type including title."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1", title="Hydration Test")
    await mongo.feed.insert_one({
        "followerUid": "uid2",
        "postId": pid,
        "authorUid": "uid1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })

    r = await gql(FEED_Q, {"limit": 10}, user_id="uid2")
    assert r.errors is None
    assert r.data["feed"]["posts"][0]["title"] == "Hydration Test"
