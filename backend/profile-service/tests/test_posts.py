"""
Post integration tests.

Tests match the schema contracts:
  create.schema.json → POST /posts  { title?, body?, media?, workout?, bodyMetrics? } minProperties:1
  base.schema.json   → response     { id, authorUid, title, body, media, workout, bodyMetrics, createdAt }

Key constraints:
  - Only users with an existing profile can create posts (403 otherwise)
  - Only the author can delete their own post
  - Cascade: deleting a profile deletes all their posts
"""

import os
import uuid

import pymongo
import requests

BASE = os.environ.get("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "fervora_test")

POST_FIELDS = {"id", "authorUid", "title", "body", "media", "workout", "bodyMetrics", "createdAt"}


def _uid() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def _username() -> str:
    return f"user_{uuid.uuid4().hex[:10]}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid, "Content-Type": "application/json"}


def _create_profile(uid: str, username: str) -> requests.Response:
    return requests.post(
        f"{BASE}/profile", json={"username": username}, headers=_headers(uid)
    )


def _create_post(uid: str, body: dict) -> requests.Response:
    return requests.post(f"{BASE}/posts", json=body, headers=_headers(uid))


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.profiles.delete_many({})
    db.posts.delete_many({})
    client.close()


# ── CREATE ────────────────────────────────────────────────────────────


class TestCreatePost:
    def test_create_post_with_title(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"title": "My First Post"})
        assert r.status_code == 201
        data = r.json()
        assert set(data.keys()) == POST_FIELDS
        assert data["authorUid"] == uid
        assert data["title"] == "My First Post"
        assert data["body"] is None
        assert data["media"] is None
        assert data["workout"] is None
        assert data["bodyMetrics"] is None
        assert data["id"]  # non-empty string
        assert data["createdAt"]  # non-empty string

    def test_create_post_with_body(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"body": "Just a text post"})
        assert r.status_code == 201
        assert r.json()["body"] == "Just a text post"

    def test_create_post_with_workout(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {
            "workout": {"activityType": "running", "durationSeconds": 1800, "caloriesBurned": 300}
        })
        assert r.status_code == 201
        w = r.json()["workout"]
        assert w["activityType"] == "running"
        assert w["durationSeconds"] == 1800
        assert w["caloriesBurned"] == 300

    def test_create_post_with_body_metrics(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"bodyMetrics": {"weightLbs": 185.5}})
        assert r.status_code == 201
        assert r.json()["bodyMetrics"]["weightLbs"] == 185.5

    def test_create_post_with_media(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {
            "media": [{"url": "https://example.com/img.jpg", "mimeType": "image/jpeg"}]
        })
        assert r.status_code == 201
        assert len(r.json()["media"]) == 1

    def test_create_post_all_fields(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {
            "title": "Full Post",
            "body": "Everything",
            "media": [{"url": "https://example.com/v.mp4", "mimeType": "video/mp4"}],
            "workout": {"activityType": "cycling"},
            "bodyMetrics": {"weightLbs": 200, "bodyFatPercentage": 15.0},
        })
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Full Post"
        assert data["body"] == "Everything"
        assert data["workout"]["activityType"] == "cycling"

    def test_create_post_empty_body_rejected(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {})
        assert r.status_code == 422

    def test_create_post_extra_fields_rejected(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"title": "ok", "hackerField": "nope"})
        assert r.status_code == 422

    def test_create_post_invalid_workout_activity(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"workout": {"activityType": "teleporting"}})
        assert r.status_code == 422

    def test_create_post_title_too_long(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"title": "x" * 201})
        assert r.status_code == 422

    def test_create_post_body_too_long(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"body": "x" * 5001})
        assert r.status_code == 422

    def test_create_post_no_header(self):
        r = requests.post(f"{BASE}/posts", json={"title": "hello"})
        assert r.status_code == 422

    def test_create_post_response_fields(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = _create_post(uid, {"title": "Test"})
        assert r.status_code == 201
        assert set(r.json().keys()) == POST_FIELDS


# ── PROFILE REQUIRED ─────────────────────────────────────────────────


class TestProfileRequired:
    def test_create_post_without_profile_rejected(self):
        """A UID with no profile cannot create posts."""
        uid = _uid()
        r = _create_post(uid, {"title": "Orphan post"})
        assert r.status_code == 403

    def test_create_post_after_profile_deleted_rejected(self):
        """After deleting their profile, user can't create posts."""
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        requests.delete(f"{BASE}/profile", headers=_headers(uid))
        r = _create_post(uid, {"title": "Ghost post"})
        assert r.status_code == 403


# ── DELETE ────────────────────────────────────────────────────────────


class TestDeletePost:
    def test_delete_own_post(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        post = _create_post(uid, {"title": "To delete"}).json()
        r = requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(uid))
        assert r.status_code == 204

    def test_delete_nonexistent_post(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = requests.delete(f"{BASE}/posts/000000000000000000000000", headers=_headers(uid))
        assert r.status_code == 404

    def test_delete_invalid_post_id(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        r = requests.delete(f"{BASE}/posts/not-a-valid-id", headers=_headers(uid))
        assert r.status_code == 404

    def test_delete_other_users_post(self):
        uid1, uid2 = _uid(), _uid()
        _create_profile(uid1, _username())
        _create_profile(uid2, _username())
        post = _create_post(uid1, {"title": "Mine"}).json()
        r = requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(uid2))
        assert r.status_code == 404

    def test_delete_idempotent(self):
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        post = _create_post(uid, {"title": "Once"}).json()
        r1 = requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(uid))
        assert r1.status_code == 204
        r2 = requests.delete(f"{BASE}/posts/{post['id']}", headers=_headers(uid))
        assert r2.status_code == 404


# ── CASCADE DELETE ────────────────────────────────────────────────────


class TestCascadeDelete:
    def test_profile_delete_cascades_posts(self):
        """Deleting a profile deletes all their posts."""
        uid, name = _uid(), _username()
        _create_profile(uid, name)
        post_ids = []
        for i in range(3):
            r = _create_post(uid, {"title": f"Post {i}"})
            post_ids.append(r.json()["id"])

        # Delete the profile
        requests.delete(f"{BASE}/profile", headers=_headers(uid))

        # Verify posts are gone by trying to delete them
        for pid in post_ids:
            r = requests.delete(f"{BASE}/posts/{pid}", headers=_headers(_uid()))
            assert r.status_code == 404

    def test_cascade_does_not_affect_other_users_posts(self):
        """Deleting user A's profile does not delete user B's posts."""
        uid_a, uid_b = _uid(), _uid()
        _create_profile(uid_a, _username())
        _create_profile(uid_b, _username())

        _create_post(uid_a, {"title": "A's post"})
        post_b = _create_post(uid_b, {"title": "B's post"}).json()

        requests.delete(f"{BASE}/profile", headers=_headers(uid_a))

        # B's post should still be deletable by B
        r = requests.delete(f"{BASE}/posts/{post_b['id']}", headers=_headers(uid_b))
        assert r.status_code == 204


# ── ISOLATION ─────────────────────────────────────────────────────────


class TestPostIsolation:
    def test_multiple_users_posts_independent(self):
        uid1, uid2 = _uid(), _uid()
        _create_profile(uid1, _username())
        _create_profile(uid2, _username())
        p1 = _create_post(uid1, {"title": "User1 post"}).json()
        p2 = _create_post(uid2, {"title": "User2 post"}).json()
        assert p1["authorUid"] == uid1
        assert p2["authorUid"] == uid2
        assert p1["id"] != p2["id"]
