"""
Comment integration tests.

Comments on posts. Only users with a profile can comment.
POST to create, DELETE to remove, GET to list (cursor-paginated, oldest first).

Cascade rules:
  - Delete post → comments removed
  - Delete profile → user's comments removed + comments on user's posts removed
"""

import os
import uuid

import pymongo
from bson import ObjectId
import requests

BASE = os.environ.get("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "fervora_test")

COMMENT_FIELDS = {"id", "postId", "authorUid", "authorUsername", "body", "createdAt"}


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


def _comment(uid: str, post_id: str, body: str) -> requests.Response:
    return requests.post(
        f"{BASE}/posts/{post_id}/comments",
        json={"body": body},
        headers=_headers(uid),
    )


def _get_comments(post_id: str, **params) -> requests.Response:
    return requests.get(f"{BASE}/posts/{post_id}/comments", params=params)


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


# ── Create Comment ────────────────────────────────────────────────────


class TestCreateComment:
    def test_create_comment(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "comment me"}).json()
        r = _comment(a, post["id"], "great post!")
        assert r.status_code == 201
        data = r.json()
        assert set(data.keys()) == COMMENT_FIELDS
        assert data["postId"] == post["id"]
        assert data["authorUid"] == a
        assert data["body"] == "great post!"

    def test_comment_on_nonexistent_post(self):
        a = _uid()
        _create_profile(a, _username())
        r = _comment(a, str(ObjectId()), "orphan comment")
        assert r.status_code == 404

    def test_comment_without_profile(self):
        a = _uid()
        post_owner = _uid()
        _create_profile(post_owner, _username())
        post = _create_post(post_owner, {"title": "need profile"}).json()
        r = _comment(a, post["id"], "no profile")
        assert r.status_code == 404

    def test_comment_empty_body_rejected(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "empty"}).json()
        r = requests.post(
            f"{BASE}/posts/{post['id']}/comments",
            json={"body": ""},
            headers=_headers(a),
        )
        assert r.status_code == 422

    def test_comment_missing_body_rejected(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "missing"}).json()
        r = requests.post(
            f"{BASE}/posts/{post['id']}/comments",
            json={},
            headers=_headers(a),
        )
        assert r.status_code == 422

    def test_comment_extra_fields_rejected(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "extra"}).json()
        r = requests.post(
            f"{BASE}/posts/{post['id']}/comments",
            json={"body": "valid", "extra": "bad"},
            headers=_headers(a),
        )
        assert r.status_code == 422

    def test_multiple_comments_on_same_post(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "multi"}).json()
        _comment(a, post["id"], "first")
        _comment(b, post["id"], "second")
        _comment(a, post["id"], "third")
        comments = _get_comments(post["id"]).json()
        assert comments["count"] == 3


# ── Delete Comment ────────────────────────────────────────────────────


class TestDeleteComment:
    def test_delete_own_comment(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "del comment"}).json()
        c = _comment(a, post["id"], "delete me").json()
        r = requests.delete(
            f"{BASE}/posts/{post['id']}/comments/{c['id']}",
            headers=_headers(a),
        )
        assert r.status_code == 204
        assert _get_comments(post["id"]).json()["count"] == 0

    def test_cannot_delete_others_comment(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "ownership"}).json()
        c = _comment(b, post["id"], "b's comment").json()
        r = requests.delete(
            f"{BASE}/posts/{post['id']}/comments/{c['id']}",
            headers=_headers(a),
        )
        assert r.status_code == 404
        # B's comment still exists
        assert _get_comments(post["id"]).json()["count"] == 1

    def test_delete_nonexistent_comment(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "no comment"}).json()
        r = requests.delete(
            f"{BASE}/posts/{post['id']}/comments/{str(ObjectId())}",
            headers=_headers(a),
        )
        assert r.status_code == 404


# ── List Comments ─────────────────────────────────────────────────────


class TestListComments:
    def test_list_comments_oldest_first(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "ordered"}).json()
        _comment(a, post["id"], "first")
        _comment(a, post["id"], "second")
        _comment(a, post["id"], "third")
        comments = _get_comments(post["id"]).json()
        assert comments["count"] == 3
        bodies = [c["body"] for c in comments["items"]]
        assert bodies == ["first", "second", "third"]

    def test_empty_comments(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "no comments"}).json()
        r = _get_comments(post["id"])
        assert r.status_code == 200
        assert r.json()["count"] == 0
        assert r.json()["items"] == []

    def test_comment_pagination(self):
        a = _uid()
        _create_profile(a, _username())
        post = _create_post(a, {"title": "paginate"}).json()
        for i in range(5):
            _comment(a, post["id"], f"comment {i}")
        page1 = _get_comments(post["id"], limit=3).json()
        assert page1["count"] == 3
        assert page1["cursor"] is not None

        page2 = _get_comments(post["id"], limit=3, cursor=page1["cursor"]).json()
        assert page2["count"] == 2

        # No overlap
        p1_ids = {c["id"] for c in page1["items"]}
        p2_ids = {c["id"] for c in page2["items"]}
        assert p1_ids.isdisjoint(p2_ids)


# ── Cascade Delete ────────────────────────────────────────────────────


class TestCommentCascade:
    def test_delete_post_removes_comments(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "will be deleted"}).json()
        _comment(a, post["id"], "a comment")
        _comment(b, post["id"], "b comment")
        requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(a))
        # Verify no orphaned comments at DB level
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.comments.count_documents({"postId": ObjectId(post["id"])}) == 0
        client.close()

    def test_delete_profile_removes_user_comments(self):
        """Deleting a profile removes that user's comments on all posts."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(b, {"title": "b post"}).json()
        _comment(a, post["id"], "a comment")
        _comment(b, post["id"], "b comment")
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # A's comment gone, B's remains
        comments = _get_comments(post["id"]).json()
        assert comments["count"] == 1
        assert comments["items"][0]["body"] == "b comment"
        # Verify at DB level
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.comments.count_documents({"authorUid": a}) == 0
        client.close()

    def test_delete_profile_removes_comments_on_their_posts(self):
        """Deleting author's profile removes comments on their posts."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        post = _create_post(a, {"title": "a post"}).json()
        _comment(b, post["id"], "b's comment on a's post")
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # Post is gone, so are comments on it
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.comments.count_documents({"postId": ObjectId(post["id"])}) == 0
        client.close()

    def test_cascade_does_not_affect_other_comments(self):
        """Deleting A doesn't remove B's comments on C's posts."""
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        post_c = _create_post(c, {"title": "c post"}).json()
        _comment(a, post_c["id"], "a's comment")
        _comment(b, post_c["id"], "b's comment")
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        comments = _get_comments(post_c["id"]).json()
        assert comments["count"] == 1
        assert comments["items"][0]["body"] == "b's comment"
