"""
Feed integration tests.

Fan-out-on-write: when a user creates a post, feed entries are created
for all their followers. GET /feed returns those posts newest-first.

Cascade rules:
  - Delete post  → feed entries for that post removed
  - Delete profile → all authored feed entries + owned feed entries removed
"""

import os
import time
import uuid

import pymongo
from bson import ObjectId
import requests

BASE = os.environ.get("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "fervora_test")


def _uid() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def _username() -> str:
    return f"user_{uuid.uuid4().hex[:10]}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid, "Content-Type": "application/json"}


def _create_profile(uid: str, username: str):
    return requests.post(
        f"{BASE}/profile", json={"username": username}, headers=_headers(uid)
    )


def _create_post(uid: str, body: dict) -> requests.Response:
    return requests.post(f"{BASE}/posts", json=body, headers=_headers(uid))


def _follow(follower: str, target: str):
    return requests.post(f"{BASE}/follows/{target}", headers=_headers(follower))


def _get_feed(uid: str, **params) -> requests.Response:
    return requests.get(f"{BASE}/feed", headers=_headers(uid), params=params)


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.profiles.delete_many({})
    db.posts.delete_many({})
    db.follows.delete_many({})
    db.feed.delete_many({})
    client.close()


# ── Basic Feed ────────────────────────────────────────────────────────


class TestFeed:
    def test_feed_shows_followed_user_post(self):
        """A follows B → B posts → A sees it in feed."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        post = _create_post(b, {"title": "hello from B"}).json()
        r = _get_feed(a)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == post["id"]
        assert data["items"][0]["title"] == "hello from B"

    def test_feed_empty_when_not_following(self):
        """A doesn't follow anyone → empty feed."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_post(b, {"title": "invisible"})
        r = _get_feed(a)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_feed_does_not_show_own_posts(self):
        """Your own posts don't appear in your feed (you're not your own follower)."""
        a = _uid()
        _create_profile(a, _username())
        _create_post(a, {"title": "my own post"})
        r = _get_feed(a)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_feed_multiple_followed_users(self):
        """A follows B and C → sees posts from both."""
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        _follow(a, b)
        _follow(a, c)
        _create_post(b, {"title": "from B"})
        _create_post(c, {"title": "from C"})
        r = _get_feed(a)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        titles = {item["title"] for item in data["items"]}
        assert titles == {"from B", "from C"}

    def test_feed_newest_first(self):
        """Feed entries are returned newest first."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        _create_post(b, {"title": "first"})
        _create_post(b, {"title": "second"})
        r = _get_feed(a)
        items = r.json()["items"]
        assert len(items) == 2
        assert items[0]["title"] == "second"
        assert items[1]["title"] == "first"

    def test_feed_only_posts_after_follow(self):
        """Posts created before following don't appear in feed."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_post(b, {"title": "before follow"})
        _follow(a, b)
        _create_post(b, {"title": "after follow"})
        r = _get_feed(a)
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["title"] == "after follow"


# ── Pagination ────────────────────────────────────────────────────────


class TestFeedPagination:
    def test_feed_limit(self):
        """Limit controls how many items are returned."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        for i in range(5):
            _create_post(b, {"title": f"post {i}"})
        r = _get_feed(a, limit=3)
        data = r.json()
        assert data["count"] == 3
        assert data["cursor"] is not None

    def test_feed_cursor_pagination(self):
        """Using cursor returns the next page."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        for i in range(5):
            _create_post(b, {"title": f"post {i}"})

        page1 = _get_feed(a, limit=3).json()
        assert page1["count"] == 3

        page2 = _get_feed(a, limit=3, cursor=page1["cursor"]).json()
        assert page2["count"] == 2

        # No overlap
        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_feed_cursor_returns_none_on_last_page(self):
        """When there are no more items, cursor is null."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        _create_post(b, {"title": "only one"})
        r = _get_feed(a, limit=10)
        data = r.json()
        assert data["count"] == 1
        # cursor points to the last item's createdAt — a subsequent
        # request with this cursor should return 0 items
        page2 = _get_feed(a, limit=10, cursor=data["cursor"]).json()
        assert page2["count"] == 0
        assert page2["cursor"] is None


# ── Cascade Delete ────────────────────────────────────────────────────


class TestFeedCascade:
    def test_delete_post_removes_feed_entries(self):
        """Deleting a post removes its feed entries (verified at DB level)."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        post = _create_post(b, {"title": "will be deleted"}).json()
        # Confirm it's in the feed
        assert _get_feed(a).json()["count"] == 1
        # Delete the post
        requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(b))
        # Feed should be empty via API
        assert _get_feed(a).json()["count"] == 0
        # Verify no orphaned feed docs in MongoDB
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.feed.count_documents({"postId": ObjectId(post["id"])}) == 0
        client.close()

    def test_delete_author_profile_removes_feed_entries(self):
        """Deleting the author's profile removes their feed entries (verified at DB level)."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        _create_post(b, {"title": "will vanish"})
        assert _get_feed(a).json()["count"] == 1
        # B deletes their profile
        requests.delete(f"{BASE}/profile", headers=_headers(b))
        # Verify via API
        assert _get_feed(a).json()["count"] == 0
        # Verify no orphaned feed docs authored by B
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.feed.count_documents({"authorUid": b}) == 0
        client.close()

    def test_delete_follower_profile_removes_their_feed(self):
        """Deleting the follower's profile removes their feed entries."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _follow(a, b)
        _create_post(b, {"title": "for A"})
        assert _get_feed(a).json()["count"] == 1
        # A deletes their profile — their feed entries should be gone
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # Verify directly via MongoDB that no feed docs with ownerUid=a exist
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.feed.count_documents({"ownerUid": a}) == 0
        client.close()

    def test_cascade_does_not_affect_other_feeds(self):
        """Deleting B's profile doesn't remove C's posts from A's feed."""
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        _follow(a, b)
        _follow(a, c)
        _create_post(b, {"title": "B post"})
        _create_post(c, {"title": "C post"})
        assert _get_feed(a).json()["count"] == 2
        # Delete B's profile
        requests.delete(f"{BASE}/profile", headers=_headers(b))
        feed = _get_feed(a).json()
        assert feed["count"] == 1
        assert feed["items"][0]["title"] == "C post"
