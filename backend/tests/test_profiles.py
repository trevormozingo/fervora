"""Profile service integration tests."""

import os

import requests
import pymongo

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")

# Expected response fields — must match response.schema.json properties.
# If the schema changes, update this set and the tests will catch drift.
_RESPONSE_FIELDS = {
    "id", "username", "displayName", "bio", "birthday", "profilePhoto",
    "location", "interests", "fitnessLevel", "followersCount",
    "followingCount", "postCount", "isFollowing",
}


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str = "test-user-1") -> dict:
    return {"X-User-Id": uid}


def setup_module():
    """Clear profiles collection before tests."""
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].profiles.delete_many({})
    client.close()


# ── Health ────────────────────────────────────────────────────────────

def test_health():
    r = requests.get(_url("/health"))
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Create ────────────────────────────────────────────────────────────

def test_create_profile():
    body = {
        "username": "janedoe",
        "displayName": "Jane Doe",
        "profilePhoto": "https://example.com/photo.jpg",
        "birthday": "1998-05-14",
        "bio": "Lifting heavy things",
        "interests": ["Weightlifting", "Running"],
        "fitnessLevel": "intermediate",
    }
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    # Response keys must match exactly what the response schema defines
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["id"] == "test-user-1"
    assert data["username"] == "janedoe"
    assert data["displayName"] == "Jane Doe"
    assert data["bio"] == "Lifting heavy things"
    assert data["birthday"] == "1998-05-14"
    assert data["profilePhoto"] == "https://example.com/photo.jpg"
    assert data["interests"] == ["Weightlifting", "Running"]
    assert data["fitnessLevel"] == "intermediate"
    assert data["followersCount"] == 0
    assert data["followingCount"] == 0
    assert data["postCount"] == 0


def test_create_duplicate_username():
    body = {
        "username": "janedoe",
        "displayName": "Another Jane",
        "profilePhoto": "https://example.com/photo2.jpg",
        "birthday": "1995-01-01",
    }
    r = requests.post(_url("/profiles"), json=body, headers=_headers("test-user-2"))
    assert r.status_code == 409


def test_create_underage():
    body = {
        "username": "younguser",
        "displayName": "Young User",
        "profilePhoto": "https://example.com/photo3.jpg",
        "birthday": "2015-01-01",
    }
    r = requests.post(_url("/profiles"), json=body, headers=_headers("test-user-3"))
    assert r.status_code == 422


def test_create_missing_required():
    body = {"username": "noname"}
    r = requests.post(_url("/profiles"), json=body, headers=_headers("test-user-4"))
    assert r.status_code == 422


# ── Read ──────────────────────────────────────────────────────────────

def test_get_me():
    r = requests.get(_url("/profiles/me"), headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["username"] == "janedoe"


def test_get_me_not_found():
    r = requests.get(_url("/profiles/me"), headers=_headers("nonexistent"))
    assert r.status_code == 404


def test_get_by_id():
    r = requests.get(_url("/profiles/test-user-1"), headers=_headers("someone-else"))
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["id"] == "test-user-1"


def test_get_by_id_self():
    r = requests.get(_url("/profiles/test-user-1"), headers=_headers("test-user-1"))
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["id"] == "test-user-1"


def test_get_by_id_not_found():
    r = requests.get(_url("/profiles/nonexistent"), headers=_headers())
    assert r.status_code == 404


# ── Update ────────────────────────────────────────────────────────────

def test_update_profile():
    body = {"bio": "Updated bio", "fitnessLevel": "experienced"}
    r = requests.patch(_url("/profiles/me"), json=body, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["bio"] == "Updated bio"
    assert data["fitnessLevel"] == "experienced"
    # Unchanged fields preserved
    assert data["username"] == "janedoe"


def test_update_not_found():
    body = {"bio": "Ghost"}
    r = requests.patch(_url("/profiles/me"), json=body, headers=_headers("nonexistent"))
    assert r.status_code == 404


def test_update_invalid():
    body = {"fitnessLevel": "godlike"}
    r = requests.patch(_url("/profiles/me"), json=body, headers=_headers())
    assert r.status_code == 422


# ── Delete (soft) ─────────────────────────────────────────────────────

def test_soft_delete():
    r = requests.delete(_url("/profiles/me"), headers=_headers())
    assert r.status_code == 204

    # Profile should no longer be visible
    r = requests.get(_url("/profiles/me"), headers=_headers())
    assert r.status_code == 404

    r = requests.get(_url("/profiles/test-user-1"), headers=_headers("someone-else"))
    assert r.status_code == 404


def test_delete_not_found():
    r = requests.delete(_url("/profiles/me"), headers=_headers("nonexistent"))
    assert r.status_code == 404
