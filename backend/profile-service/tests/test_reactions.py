"""
Reaction integration tests.

Emoji reactions on posts. One reaction per user per post.
PUT to set/update, DELETE to remove, GET to list.

Cascade rules:
  - Delete post → reactions removed
  - Delete profile → user's reactions removed + reactions on user's posts removed
"""

import os
import uuid

import pymongo
from bson import ObjectId
import requests

BASE = os.environ.get("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "fervora_test")

VALID_TYPES = ["strong", "fire", "heart", "smile", "laugh", "thumbsup", "thumbsdown", "angry"]


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


def _react(uid: str, post_id: str, reaction_type: str) -> requests.Response:
    return requests.put(
        f"{BASE}/posts/{post_id}/reactions",
        json={"type": reaction_type},
        headers=_headers(uid),
    )


def _unreact(uid: str, post_id: str) -> requests.Response:
    return requests.delete(
        f"{BASE}/posts/{post_id}/reactions", headers=_headers(uid)
    )


def _get_reactions(post_id: str) -> requests.Response:
    return requests.get(f"{BASE}/posts/{post_id}/reactions")


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.profiles.delete_many({})
    db.posts.delete_many({})
    db.follows.delete_many({})
    db.feed.delete_many({})
    db.reactions.delete_many({})
    db.comments.delete_many({})
    client.close()


# ── Set Reaction ──────────────────────────────────────────────────────


class TestSetReaction:
    def test_react_to_post(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "react to me"}).json()
        r = _react(a, post["id"], "fire")
        assert r.status_code == 200
        data = r.json()
        assert data["postId"] == post["id"]
        assert data["authorUid"] == a
        assert data["type"] == "fire"

    def test_update_reaction(self):
        """Reacting again updates the type (not duplicates)."""
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "change me"}).json()
        _react(a, post["id"], "fire")
        r = _react(a, post["id"], "heart")
        assert r.status_code == 200
        assert r.json()["type"] == "heart"
        # Should still be only one reaction
        reactions = _get_reactions(post["id"]).json()
        assert reactions["count"] == 1

    def test_multiple_users_react(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "popular"}).json()
        _react(a, post["id"], "fire")
        _react(b, post["id"], "heart")
        reactions = _get_reactions(post["id"]).json()
        assert reactions["count"] == 2
        types = {r["type"] for r in reactions["reactions"]}
        assert types == {"fire", "heart"}

    def test_react_to_nonexistent_post(self):
        a = _uid()
        _create_profile(a, _username())
        fake_id = str(ObjectId())
        r = _react(a, fake_id, "fire")
        assert r.status_code == 404

    def test_invalid_reaction_type(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "bad react"}).json()
        r = _react(a, post["id"], "invalid_emoji")
        assert r.status_code == 422

    def test_all_reaction_types_valid(self):
        a = _uid()
        _create_profile(a, _username())
        for rtype in VALID_TYPES:
            post = _create_post(a, {"title": f"test {rtype}"}).json()
            r = _react(a, post["id"], rtype)
            assert r.status_code == 200, f"Failed for type: {rtype}"

    def test_react_empty_body_rejected(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "no body"}).json()
        r = requests.put(
            f"{BASE}/posts/{post['id']}/reactions",
            json={},
            headers=_headers(a),
        )
        assert r.status_code == 422


# ── Remove Reaction ───────────────────────────────────────────────────


class TestRemoveReaction:
    def test_unreact(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "unreact me"}).json()
        _react(a, post["id"], "fire")
        r = _unreact(a, post["id"])
        assert r.status_code == 204
        assert _get_reactions(post["id"]).json()["count"] == 0

    def test_unreact_not_reacted(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "never reacted"}).json()
        r = _unreact(a, post["id"])
        assert r.status_code == 404

    def test_unreact_does_not_affect_others(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "shared"}).json()
        _react(a, post["id"], "fire")
        _react(b, post["id"], "heart")
        _unreact(a, post["id"])
        reactions = _get_reactions(post["id"]).json()
        assert reactions["count"] == 1
        assert reactions["reactions"][0]["authorUid"] == b


# ── List Reactions ────────────────────────────────────────────────────


class TestListReactions:
    def test_empty_reactions(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "no reactions"}).json()
        r = _get_reactions(post["id"])
        assert r.status_code == 200
        assert r.json()["count"] == 0
        assert r.json()["reactions"] == []


# ── Cascade Delete ────────────────────────────────────────────────────


class TestReactionCascade:
    def test_delete_post_removes_reactions(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "will be deleted"}).json()
        _react(a, post["id"], "fire")
        _react(b, post["id"], "heart")
        requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(a))
        # Verify no orphaned reactions at DB level
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.reactions.count_documents({"postId": ObjectId(post["id"])}) == 0
        client.close()

    def test_delete_profile_removes_user_reactions(self):
        """Deleting a profile removes that user's reactions on all posts."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(b, {"title": "b post"}).json()
        _react(a, post["id"], "fire")
        _react(b, post["id"], "heart")
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # A's reaction should be gone, B's should remain
        reactions = _get_reactions(post["id"]).json()
        assert reactions["count"] == 1
        assert reactions["reactions"][0]["authorUid"] == b
        # Verify at DB level
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.reactions.count_documents({"authorUid": a}) == 0
        client.close()

    def test_delete_profile_removes_reactions_on_their_posts(self):
        """Deleting author's profile removes reactions on their posts."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "a post"}).json()
        _react(b, post["id"], "fire")
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # Post is gone, so are reactions on it
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.reactions.count_documents({"postId": ObjectId(post["id"])}) == 0
        client.close()

    def test_cascade_does_not_affect_other_reactions(self):
        """Deleting A doesn't remove B's reactions on C's posts."""
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        post_c = _create_post(c, {"title": "c post"}).json()
        _react(a, post_c["id"], "fire")
        _react(b, post_c["id"], "heart")
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        reactions = _get_reactions(post_c["id"]).json()
        assert reactions["count"] == 1
        assert reactions["reactions"][0]["authorUid"] == b
