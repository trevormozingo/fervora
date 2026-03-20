"""
Feed integration tests.

Fan-out-on-write: the event-processor creates feed entries when posts
are created and backfills on follow. These tests seed the feed collection
directly via pymongo to test the feed endpoint independently of the
event-processor pipeline.

GET /feed — returns posts from users the caller follows, newest first.
Cursor-based pagination via ?cursor=<createdAt>&limit=<n>.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta

import pymongo
import redis
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


def _flush_feed_cache(owner_uid: str):
    """Clear cached feed pages for a user (simulates event-processor invalidation)."""
    r = redis.from_url(REDIS_URL)
    for key in r.scan_iter(match=f"feed:{owner_uid}:*"):
        r.delete(key)
    r.close()


def _flush_following_cache(uid: str):
    """Clear cached following list so the feed query picks up new follows."""
    r = redis.from_url(REDIS_URL)
    r.delete(f"following:{uid}")
    r.close()


def _uid() -> str:
    return f"feed-{uuid.uuid4().hex[:12]}"


def _username() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid, "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _create_profile(uid: str) -> dict:
    r = requests.post(
        _url("/profiles"),
        json={
            "username": _username(),
            "displayName": "Feed Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        },
        headers=_headers(uid),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _follow(follower_uid: str, followed_uid: str):
    """Create a follow relationship via the API."""
    r = requests.post(
        _url(f"/follows/{followed_uid}"),
        headers=_headers(follower_uid),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_post(uid: str, title: str = "test post") -> dict:
    r = requests.post(
        _url("/posts"),
        json={"title": title},
        headers=_headers(uid),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _get_feed(uid: str, **params) -> requests.Response:
    return requests.get(_url("/feed"), headers=_headers(uid), params=params)


def _now_iso(offset_seconds: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.isoformat()


def _seed_feed(owner_uid: str, post_id: str, author_uid: str, created_at: str | None = None):
    """Insert a feed entry directly into MongoDB."""
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.feed.update_one(
        {"ownerUid": owner_uid, "postId": post_id},
        {
            "$set": {
                "authorUid": author_uid,
                "createdAt": created_at or _now_iso(),
                "isDeleted": False,
            },
            "$unset": {"deletedAt": ""},
        },
        upsert=True,
    )
    client.close()


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.feed.delete_many({})
    client.close()


# ── Basic Feed ────────────────────────────────────────────────────────


class TestFeedEndpoint:
    def test_feed_returns_seeded_posts(self):
        """Feed endpoint returns posts from seeded feed entries."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)
        post = _create_post(b, title="hello from B")
        _seed_feed(a, post["id"], b)

        r = _get_feed(a)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == post["id"]
        assert data["items"][0]["title"] == "hello from B"

    def test_feed_empty_when_no_entries(self):
        """Empty feed when no feed entries exist."""
        a = _uid()
        _create_profile(a)
        r = _get_feed(a)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["items"] == []
        assert data["cursor"] is None

    def test_feed_newest_first(self):
        """Feed entries are returned newest first."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)

        post1 = _create_post(b, title="first")
        post2 = _create_post(b, title="second")

        _seed_feed(a, post1["id"], b, _now_iso(-10))
        _seed_feed(a, post2["id"], b, _now_iso(0))

        r = _get_feed(a)
        items = r.json()["items"]
        assert len(items) == 2
        assert items[0]["title"] == "second"
        assert items[1]["title"] == "first"

    def test_feed_multiple_authors(self):
        """Feed shows posts from multiple authors."""
        a = _uid()
        b = _uid()
        c = _uid()
        _create_profile(a)
        _create_profile(b)
        _create_profile(c)
        _follow(a, b)
        _follow(a, c)

        post_b = _create_post(b, title="from B")
        post_c = _create_post(c, title="from C")

        _seed_feed(a, post_b["id"], b)
        _seed_feed(a, post_c["id"], c)

        r = _get_feed(a)
        data = r.json()
        assert data["count"] == 2
        titles = {item["title"] for item in data["items"]}
        assert titles == {"from B", "from C"}

    def test_feed_includes_enrichment(self):
        """Feed items include author info and aggregations."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)
        post = _create_post(b, title="enriched post")
        _seed_feed(a, post["id"], b)

        r = _get_feed(a)
        item = r.json()["items"][0]
        assert "authorUsername" in item
        assert "authorProfilePhoto" in item
        assert "reactionSummary" in item
        assert "commentCount" in item
        assert "recentComments" in item
        assert "feedCreatedAt" in item

    def test_feed_skips_deleted_posts(self):
        """Feed entries for deleted posts are not returned."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)
        post = _create_post(b, title="will be deleted")
        _seed_feed(a, post["id"], b)

        # Delete the post
        requests.delete(_url(f"/posts/{post['id']}"), headers=_headers(b))

        r = _get_feed(a)
        assert r.json()["count"] == 0


# ── Pagination ────────────────────────────────────────────────────────


class TestFeedPagination:
    def test_feed_limit(self):
        """Limit controls how many items are returned."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)

        for i in range(5):
            post = _create_post(b, title=f"post {i}")
            _seed_feed(a, post["id"], b, _now_iso(-5 + i))

        r = _get_feed(a, limit=3)
        data = r.json()
        assert data["count"] == 3
        assert data["cursor"] is not None

    def test_feed_cursor_pagination(self):
        """Using cursor returns the next page."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)

        for i in range(5):
            post = _create_post(b, title=f"post {i}")
            _seed_feed(a, post["id"], b, _now_iso(-5 + i))

        page1 = _get_feed(a, limit=3).json()
        assert page1["count"] == 3

        page2 = _get_feed(a, limit=3, cursor=page1["cursor"]).json()
        assert page2["count"] == 2

        # No overlap
        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_feed_cursor_none_on_last_page(self):
        """When there are no more items after the cursor, count is 0."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)
        post = _create_post(b, title="only one")
        _seed_feed(a, post["id"], b)

        r = _get_feed(a, limit=10)
        data = r.json()
        assert data["count"] == 1

        page2 = _get_feed(a, limit=10, cursor=data["cursor"]).json()
        assert page2["count"] == 0
        assert page2["cursor"] is None


# ── Feed Collection Integrity ─────────────────────────────────────────


class TestFeedCollection:
    def test_feed_entries_isolated_per_user(self):
        """User A's feed entries don't appear in user B's feed."""
        a = _uid()
        b = _uid()
        c = _uid()
        _create_profile(a)
        _create_profile(b)
        _create_profile(c)
        _follow(a, c)
        post = _create_post(c, title="for A only")
        _seed_feed(a, post["id"], c)

        # A sees it
        assert _get_feed(a).json()["count"] == 1
        # B doesn't
        assert _get_feed(b).json()["count"] == 0

    def test_soft_deleted_feed_entries_hidden(self):
        """Soft-deleted feed entries do not appear in the feed."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)
        post = _create_post(b, title="soft deleted")
        _seed_feed(a, post["id"], b)
        assert _get_feed(a).json()["count"] == 1

        # Soft-delete the feed entry directly
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        db.feed.update_one(
            {"ownerUid": a, "postId": post["id"]},
            {"$set": {"isDeleted": True, "deletedAt": _now_iso()}},
        )
        client.close()

        # Flush feed cache (in production the event-processor does this)
        _flush_feed_cache(a)

        assert _get_feed(a).json()["count"] == 0

    def test_feed_entry_unique_per_owner_post(self):
        """Upserting the same (ownerUid, postId) pair doesn't create duplicates."""
        a = _uid()
        b = _uid()
        _create_profile(a)
        _create_profile(b)
        _follow(a, b)
        post = _create_post(b, title="unique test")

        _seed_feed(a, post["id"], b, _now_iso(-5))
        _seed_feed(a, post["id"], b, _now_iso(0))  # upsert same pair

        # Should still be exactly 1 entry
        assert _get_feed(a).json()["count"] == 1

    def test_feed_filters_out_unfollowed_authors(self):
        """Feed entries from authors the user doesn't follow are hidden."""
        a = _uid()
        b = _uid()
        c = _uid()
        _create_profile(a)
        _create_profile(b)
        _create_profile(c)
        _follow(a, b)  # a follows b but NOT c

        post_b = _create_post(b, title="followed author")
        post_c = _create_post(c, title="not followed")

        _seed_feed(a, post_b["id"], b)
        _seed_feed(a, post_c["id"], c)

        data = _get_feed(a).json()
        assert data["count"] == 1
        assert data["items"][0]["title"] == "followed author"
