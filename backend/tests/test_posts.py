"""Post service integration tests."""

import os

import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")

# Expected response fields — union of base + response schema properties.
_RESPONSE_FIELDS = {
    "id", "authorUid", "title", "body", "media", "workout", "bodyMetrics",
    "healthKitId", "createdAt",
    "authorUsername", "authorProfilePhoto",
    "reactionSummary", "commentCount", "recentComments", "myReaction",
}


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str = "post-test-user") -> dict:
    return {"X-User-Id": uid}


def _ensure_profile(uid: str = "post-test-user", username: str = "posttester"):
    """Create a profile if one doesn't exist for the test user."""
    r = requests.get(_url(f"/profiles/{uid}"), headers=_headers(uid))
    if r.status_code == 404:
        body = {
            "username": username,
            "displayName": "Post Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        }
        r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
        assert r.status_code == 201


def setup_module():
    """Clear posts collection and ensure test profile exists."""
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].posts.delete_many({})
    client.close()
    _ensure_profile()


# ── Health ────────────────────────────────────────────────────────────

def test_health():
    r = requests.get(_url("/health"))
    assert r.status_code == 200


# ── Create ────────────────────────────────────────────────────────────

def test_create_post_with_body():
    body = {"body": "My first post!"}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["body"] == "My first post!"
    assert data["authorUid"] == "post-test-user"
    assert data["authorUsername"] == "posttester"
    assert data["id"] is not None
    assert data["createdAt"] is not None


def test_create_post_with_title_and_body():
    body = {"title": "Leg Day", "body": "Squats and lunges today"}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Leg Day"
    assert data["body"] == "Squats and lunges today"


def test_create_post_with_workout():
    body = {
        "body": "Morning run",
        "workout": {
            "activityType": "running",
            "durationSeconds": 1800,
            "distanceMiles": 3.1,
        },
    }
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["workout"]["activityType"] == "running"
    assert data["workout"]["durationSeconds"] == 1800


def test_create_post_with_media():
    body = {
        "body": "Check this out",
        "media": [
            {"url": "https://example.com/img.jpg", "mimeType": "image/jpeg"},
        ],
    }
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert len(data["media"]) == 1
    assert data["media"][0]["mimeType"] == "image/jpeg"


def test_create_post_with_body_metrics():
    body = {
        "body": "New PR!",
        "bodyMetrics": {"weightLbs": 185.5, "bodyFatPercentage": 15.2},
    }
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["bodyMetrics"]["weightLbs"] == 185.5


def test_create_post_response_has_defaults():
    """New posts should have zero counts and empty computed fields."""
    body = {"body": "Defaults test"}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["reactionSummary"] == {}
    assert data["commentCount"] == 0
    assert data["recentComments"] == []
    assert data["myReaction"] is None


# ── Read ──────────────────────────────────────────────────────────────

def test_get_post_by_id():
    body = {"body": "Get me later"}
    create_r = requests.post(_url("/posts"), json=body, headers=_headers())
    post_id = create_r.json()["id"]

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == post_id
    assert data["body"] == "Get me later"
    assert set(data.keys()) == _RESPONSE_FIELDS


def test_get_post_not_found():
    r = requests.get(_url("/posts/nonexistent"), headers=_headers())
    assert r.status_code == 404


def test_list_posts_by_author():
    # Create a second user's post to ensure filtering works
    _ensure_profile("other-user", "otheruser")
    requests.post(
        _url("/posts"),
        json={"body": "Other user's post"},
        headers=_headers("other-user"),
    )

    r = requests.get(
        _url("/posts"), params={"author": "post-test-user"}, headers=_headers()
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for post in data:
        assert post["authorUid"] == "post-test-user"
        assert set(post.keys()) == _RESPONSE_FIELDS


def test_list_posts_returns_newest_first():
    r = requests.get(
        _url("/posts"), params={"author": "post-test-user"}, headers=_headers()
    )
    data = r.json()
    if len(data) >= 2:
        assert data[0]["createdAt"] >= data[1]["createdAt"]


# ── Delete ────────────────────────────────────────────────────────────

def test_soft_delete_own_post():
    body = {"body": "Delete me"}
    create_r = requests.post(_url("/posts"), json=body, headers=_headers())
    post_id = create_r.json()["id"]

    r = requests.delete(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.status_code == 204

    # Should no longer be visible
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.status_code == 404


def test_cannot_delete_other_users_post():
    body = {"body": "Not yours"}
    create_r = requests.post(_url("/posts"), json=body, headers=_headers())
    post_id = create_r.json()["id"]

    # Different user tries to delete
    r = requests.delete(_url(f"/posts/{post_id}"), headers=_headers("other-user"))
    assert r.status_code == 404

    # Original user can still see it
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.status_code == 200


def test_delete_nonexistent_post():
    r = requests.delete(_url("/posts/nonexistent"), headers=_headers())
    assert r.status_code == 404


# ── Validation ────────────────────────────────────────────────────────

def test_create_empty_body_rejected():
    r = requests.post(_url("/posts"), json={}, headers=_headers())
    assert r.status_code == 422


def test_create_extra_field_rejected():
    body = {"body": "Hi", "badField": "nope"}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_title_too_long_rejected():
    body = {"title": "x" * 201}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_body_too_long_rejected():
    body = {"body": "x" * 5001}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_media_too_many_items_rejected():
    body = {
        "media": [
            {"url": f"https://example.com/{i}.jpg", "mimeType": "image/jpeg"}
            for i in range(11)
        ]
    }
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_media_missing_required_fields_rejected():
    body = {"media": [{"url": "https://example.com/img.jpg"}]}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_workout_invalid_activity_type_rejected():
    body = {"workout": {"activityType": "flying"}}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_workout_missing_activity_type_rejected():
    body = {"workout": {"durationSeconds": 100}}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_body_metrics_invalid_percentage_rejected():
    body = {"bodyMetrics": {"bodyFatPercentage": 101}}
    r = requests.post(_url("/posts"), json=body, headers=_headers())
    assert r.status_code == 422


def test_missing_user_id_header():
    body = {"body": "No header"}
    r = requests.post(_url("/posts"), json=body)
    assert r.status_code == 422
