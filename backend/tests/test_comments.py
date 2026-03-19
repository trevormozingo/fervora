"""Comment service integration tests."""

import os

import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")

# Expected response fields — union of base + response schema properties.
_RESPONSE_FIELDS = {
    "id", "postId", "authorUid", "body", "createdAt",
    "authorUsername", "authorProfilePhoto",
}


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str = "comment-test-user") -> dict:
    return {"X-User-Id": uid}


_test_post_id: str | None = None


def _ensure_profile(uid: str = "comment-test-user", username: str = "commenttester"):
    r = requests.get(_url(f"/profiles/{uid}"), headers=_headers(uid))
    if r.status_code == 404:
        body = {
            "username": username,
            "displayName": "Comment Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        }
        r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
        assert r.status_code == 201


def _create_test_post(uid: str = "comment-test-user") -> str:
    body = {"body": "Post for comment testing"}
    r = requests.post(_url("/posts"), json=body, headers=_headers(uid))
    assert r.status_code == 201
    return r.json()["id"]


def setup_module():
    """Clear comments collection, ensure test profile and post exist."""
    global _test_post_id
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].comments.delete_many({})
    client.close()
    _ensure_profile()
    _test_post_id = _create_test_post()


def _comments_url(post_id: str | None = None, comment_id: str | None = None) -> str:
    pid = post_id or _test_post_id
    base = f"/posts/{pid}/comments"
    if comment_id:
        return f"{base}/{comment_id}"
    return base


# ── Create ────────────────────────────────────────────────────────────

def test_create_comment():
    body = {"body": "Great post!"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["body"] == "Great post!"
    assert data["authorUid"] == "comment-test-user"
    assert data["postId"] == _test_post_id
    assert data["authorUsername"] == "commenttester"
    assert data["id"] is not None
    assert data["createdAt"] is not None


def test_create_comment_resolves_author_photo():
    body = {"body": "Nice!"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["authorProfilePhoto"] == "https://example.com/photo.jpg"


def test_create_comment_on_nonexistent_post():
    body = {"body": "Hello"}
    r = requests.post(
        _url(_comments_url(post_id="nonexistent123")),
        json=body,
        headers=_headers(),
    )
    assert r.status_code == 404


# ── Read ──────────────────────────────────────────────────────────────

def test_get_comment_by_id():
    # Create a comment first
    body = {"body": "Fetchable comment"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    comment_id = r.json()["id"]

    r = requests.get(
        _url(_comments_url(comment_id=comment_id)),
        headers=_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == comment_id
    assert data["body"] == "Fetchable comment"


def test_get_comment_not_found():
    r = requests.get(
        _url(_comments_url(comment_id="nonexistent123")),
        headers=_headers(),
    )
    assert r.status_code == 404


def test_get_comment_wrong_post():
    """Getting a comment with a mismatched post ID returns 404."""
    body = {"body": "Wrong post test"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    comment_id = r.json()["id"]

    # Try to get it under a different post
    r = requests.get(
        _url(_comments_url(post_id="wrong-post-id", comment_id=comment_id)),
        headers=_headers(),
    )
    assert r.status_code == 404


def test_list_comments_by_post():
    """List returns comments for a specific post."""
    # Create a fresh post with known comments
    post_id = _create_test_post()
    for i in range(3):
        r = requests.post(
            _url(_comments_url(post_id=post_id)),
            json={"body": f"Comment {i}"},
            headers=_headers(),
        )
        assert r.status_code == 201

    r = requests.get(_url(_comments_url(post_id=post_id)), headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    # Verify each has the expected shape
    for comment in data:
        assert set(comment.keys()) == _RESPONSE_FIELDS
        assert comment["postId"] == post_id


def test_list_comments_returns_newest_first():
    post_id = _create_test_post()
    bodies = ["First", "Second", "Third"]
    for b in bodies:
        r = requests.post(
            _url(_comments_url(post_id=post_id)),
            json={"body": b},
            headers=_headers(),
        )
        assert r.status_code == 201

    r = requests.get(_url(_comments_url(post_id=post_id)), headers=_headers())
    data = r.json()
    assert data[0]["body"] == "Third"
    assert data[2]["body"] == "First"


def test_list_comments_nonexistent_post():
    r = requests.get(
        _url(_comments_url(post_id="nonexistent123")),
        headers=_headers(),
    )
    assert r.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────

def test_soft_delete_own_comment():
    body = {"body": "Delete me"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    comment_id = r.json()["id"]

    r = requests.delete(
        _url(_comments_url(comment_id=comment_id)),
        headers=_headers(),
    )
    assert r.status_code == 204

    # Should no longer be fetchable
    r = requests.get(
        _url(_comments_url(comment_id=comment_id)),
        headers=_headers(),
    )
    assert r.status_code == 404


def test_cannot_delete_other_users_comment():
    body = {"body": "Not yours"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    comment_id = r.json()["id"]

    r = requests.delete(
        _url(_comments_url(comment_id=comment_id)),
        headers={"X-User-Id": "other-user"},
    )
    assert r.status_code == 404

    # Original user can still see it
    r = requests.get(
        _url(_comments_url(comment_id=comment_id)),
        headers=_headers(),
    )
    assert r.status_code == 200


def test_delete_nonexistent_comment():
    r = requests.delete(
        _url(_comments_url(comment_id="nonexistent123")),
        headers=_headers(),
    )
    assert r.status_code == 404


def test_delete_comment_wrong_post():
    """Deleting a comment under the wrong post returns 404."""
    body = {"body": "Wrong post delete"}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201
    comment_id = r.json()["id"]

    r = requests.delete(
        _url(_comments_url(post_id="wrong-post-id", comment_id=comment_id)),
        headers=_headers(),
    )
    assert r.status_code == 404


# ── Cache invalidation ───────────────────────────────────────────────

def test_comment_count_updates_after_create():
    """Post's commentCount should reflect new comments."""
    post_id = _create_test_post()

    # Check initial count
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.status_code == 200
    assert r.json()["commentCount"] == 0

    # Add a comment
    r = requests.post(
        _url(_comments_url(post_id=post_id)),
        json={"body": "Count test 1"},
        headers=_headers(),
    )
    assert r.status_code == 201

    # Count should now be 1
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.status_code == 200
    assert r.json()["commentCount"] == 1


def test_comment_count_updates_after_delete():
    """Post's commentCount goes down after soft-deleting a comment."""
    post_id = _create_test_post()

    # Add 2 comments
    comment_ids = []
    for i in range(2):
        r = requests.post(
            _url(_comments_url(post_id=post_id)),
            json={"body": f"Del count {i}"},
            headers=_headers(),
        )
        assert r.status_code == 201
        comment_ids.append(r.json()["id"])

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["commentCount"] == 2

    # Delete one
    r = requests.delete(
        _url(_comments_url(post_id=post_id, comment_id=comment_ids[0])),
        headers=_headers(),
    )
    assert r.status_code == 204

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["commentCount"] == 1


def test_recent_comments_update_on_post():
    """Post's recentComments should reflect newly added comments."""
    post_id = _create_test_post()

    r = requests.post(
        _url(_comments_url(post_id=post_id)),
        json={"body": "Recent test"},
        headers=_headers(),
    )
    assert r.status_code == 201

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    recent = r.json()["recentComments"]
    assert len(recent) == 1
    assert recent[0]["body"] == "Recent test"


# ── Validation ────────────────────────────────────────────────────────

def test_create_empty_body_rejected():
    body = {}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_blank_body_rejected():
    body = {"body": ""}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_body_too_long_rejected():
    body = {"body": "x" * 2001}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_extra_field_rejected():
    body = {"body": "Valid", "spam": True}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_body_max_length():
    body = {"body": "x" * 2000}
    r = requests.post(_url(_comments_url()), json=body, headers=_headers())
    assert r.status_code == 201


def test_missing_user_id_header():
    body = {"body": "No user"}
    r = requests.post(_url(_comments_url()), json=body)
    assert r.status_code == 422
