"""
Profile CRUD integration tests.

Tests match the schema contracts exactly:
  create.schema.json  → POST /profile     { username, displayName? }
  update.schema.json  → PATCH /profile    { displayName?, bio?, birthday? }  minProperties:1
  public.schema.json  → GET /profile/{u}  { id, username, displayName, bio, birthday }
  private.schema.json → GET /profile      { id, username, displayName, bio, birthday }
"""

import os
import uuid

import pymongo
import requests

BASE = os.environ.get("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "fervora_test")

PROFILE_FIELDS = {"id", "username", "displayName", "bio", "birthday"}


def _uid() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def _username() -> str:
    return f"user_{uuid.uuid4().hex[:10]}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid, "Content-Type": "application/json"}


def _create(uid: str, username: str, display_name: str | None = None) -> requests.Response:
    body = {"username": username}
    if display_name is not None:
        body["displayName"] = display_name
    return requests.post(f"{BASE}/profile", json=body, headers=_headers(uid))


def setup_module():
    """Wipe the profiles collection before the test run."""
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].profiles.delete_many({})
    client.close()


# ── CREATE ────────────────────────────────────────────────────────────


class TestCreate:
    def test_create_with_username_only(self):
        uid, name = _uid(), _username()
        r = _create(uid, name)
        assert r.status_code == 201
        data = r.json()
        assert set(data.keys()) == PROFILE_FIELDS
        assert data["username"] == name
        assert data["displayName"] == name  # defaults to username
        assert data["bio"] is None
        assert data["birthday"] is None

    def test_create_with_display_name(self):
        uid, name = _uid(), _username()
        r = _create(uid, name, display_name="John Doe")
        assert r.status_code == 201
        assert r.json()["displayName"] == "John Doe"

    def test_create_missing_username(self):
        r = requests.post(f"{BASE}/profile", json={}, headers=_headers(_uid()))
        assert r.status_code == 422

    def test_create_username_too_short(self):
        r = _create(_uid(), "ab")
        assert r.status_code == 422

    def test_create_username_too_long(self):
        r = _create(_uid(), "a" * 31)
        assert r.status_code == 422

    def test_create_username_invalid_chars(self):
        r = _create(_uid(), "bad username!")
        assert r.status_code == 422

    def test_create_duplicate_username(self):
        name = _username()
        _create(_uid(), name)
        r = _create(_uid(), name)
        assert r.status_code == 409

    def test_create_duplicate_uid(self):
        uid = _uid()
        _create(uid, _username())
        r = _create(uid, _username())
        assert r.status_code == 409

    def test_create_no_header(self):
        r = requests.post(f"{BASE}/profile", json={"username": _username()})
        assert r.status_code == 422

    def test_create_extra_fields_rejected(self):
        r = requests.post(
            f"{BASE}/profile",
            json={"username": _username(), "bio": "nope"},
            headers=_headers(_uid()),
        )
        assert r.status_code == 422

    def test_create_display_name_too_long(self):
        r = _create(_uid(), _username(), display_name="x" * 101)
        assert r.status_code == 422

    def test_create_response_has_no_extra_fields(self):
        r = _create(_uid(), _username())
        assert r.status_code == 201
        assert set(r.json().keys()) == PROFILE_FIELDS


# ── GET OWN (PRIVATE) ────────────────────────────────────────────────


class TestGetOwn:
    def test_get_own_profile(self):
        uid, name = _uid(), _username()
        _create(uid, name, display_name="Me")
        r = requests.get(f"{BASE}/profile", headers=_headers(uid))
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) == PROFILE_FIELDS
        assert data["username"] == name
        assert data["displayName"] == "Me"

    def test_get_own_not_found(self):
        r = requests.get(f"{BASE}/profile", headers=_headers(_uid()))
        assert r.status_code == 404

    def test_get_own_no_header(self):
        r = requests.get(f"{BASE}/profile")
        assert r.status_code == 422


# ── GET PUBLIC ────────────────────────────────────────────────────────


class TestGetPublic:
    def test_get_public_profile(self):
        uid, name = _uid(), _username()
        _create(uid, name, display_name="Public User")
        r = requests.get(f"{BASE}/profile/{name}")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) == PROFILE_FIELDS
        assert data["username"] == name
        assert data["displayName"] == "Public User"

    def test_get_public_not_found(self):
        r = requests.get(f"{BASE}/profile/nonexistent_user_xyz")
        assert r.status_code == 404

    def test_get_public_no_auth_needed(self):
        uid, name = _uid(), _username()
        _create(uid, name)
        r = requests.get(f"{BASE}/profile/{name}")
        assert r.status_code == 200


# ── UPDATE ────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_display_name(self):
        uid, name = _uid(), _username()
        _create(uid, name)
        r = requests.patch(
            f"{BASE}/profile",
            json={"displayName": "New Name"},
            headers=_headers(uid),
        )
        assert r.status_code == 200
        assert r.json()["displayName"] == "New Name"

    def test_update_bio(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile", json={"bio": "Hello world"}, headers=_headers(uid)
        )
        assert r.status_code == 200
        assert r.json()["bio"] == "Hello world"

    def test_update_bio_to_null(self):
        uid = _uid()
        _create(uid, _username())
        requests.patch(f"{BASE}/profile", json={"bio": "temp"}, headers=_headers(uid))
        r = requests.patch(f"{BASE}/profile", json={"bio": None}, headers=_headers(uid))
        assert r.status_code == 200
        assert r.json()["bio"] is None

    def test_update_birthday(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile",
            json={"birthday": "1990-05-15"},
            headers=_headers(uid),
        )
        assert r.status_code == 200
        assert r.json()["birthday"] == "1990-05-15"

    def test_update_birthday_invalid_format(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile",
            json={"birthday": "not-a-date"},
            headers=_headers(uid),
        )
        assert r.status_code == 422

    def test_update_multiple_fields(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile",
            json={"displayName": "Updated", "bio": "new bio", "birthday": "2000-01-01"},
            headers=_headers(uid),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["displayName"] == "Updated"
        assert data["bio"] == "new bio"
        assert data["birthday"] == "2000-01-01"

    def test_update_empty_body_rejected(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(f"{BASE}/profile", json={}, headers=_headers(uid))
        assert r.status_code == 422

    def test_update_extra_fields_rejected(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile",
            json={"bio": "ok", "hackerField": "nope"},
            headers=_headers(uid),
        )
        assert r.status_code == 422

    def test_update_not_found(self):
        r = requests.patch(
            f"{BASE}/profile",
            json={"bio": "hi"},
            headers=_headers(_uid()),
        )
        assert r.status_code == 404

    def test_update_display_name_too_long(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile",
            json={"displayName": "x" * 101},
            headers=_headers(uid),
        )
        assert r.status_code == 422

    def test_update_bio_too_long(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile",
            json={"bio": "x" * 501},
            headers=_headers(uid),
        )
        assert r.status_code == 422

    def test_update_preserves_unchanged_fields(self):
        uid, name = _uid(), _username()
        _create(uid, name, display_name="Original")
        requests.patch(f"{BASE}/profile", json={"bio": "my bio"}, headers=_headers(uid))
        r = requests.get(f"{BASE}/profile", headers=_headers(uid))
        data = r.json()
        assert data["displayName"] == "Original"
        assert data["bio"] == "my bio"
        assert data["username"] == name

    def test_update_response_has_no_extra_fields(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.patch(
            f"{BASE}/profile", json={"bio": "test"}, headers=_headers(uid)
        )
        assert set(r.json().keys()) == PROFILE_FIELDS


# ── DELETE ────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_profile(self):
        uid = _uid()
        _create(uid, _username())
        r = requests.delete(f"{BASE}/profile", headers=_headers(uid))
        assert r.status_code == 204

    def test_delete_then_get_returns_404(self):
        uid, name = _uid(), _username()
        _create(uid, name)
        requests.delete(f"{BASE}/profile", headers=_headers(uid))
        r = requests.get(f"{BASE}/profile", headers=_headers(uid))
        assert r.status_code == 404

    def test_delete_then_public_returns_404(self):
        uid, name = _uid(), _username()
        _create(uid, name)
        requests.delete(f"{BASE}/profile", headers=_headers(uid))
        r = requests.get(f"{BASE}/profile/{name}")
        assert r.status_code == 404

    def test_delete_not_found(self):
        r = requests.delete(f"{BASE}/profile", headers=_headers(_uid()))
        assert r.status_code == 404

    def test_delete_idempotent_check(self):
        uid = _uid()
        _create(uid, _username())
        r1 = requests.delete(f"{BASE}/profile", headers=_headers(uid))
        assert r1.status_code == 204
        r2 = requests.delete(f"{BASE}/profile", headers=_headers(uid))
        assert r2.status_code == 404

    def test_delete_frees_username(self):
        name = _username()
        uid1 = _uid()
        _create(uid1, name)
        requests.delete(f"{BASE}/profile", headers=_headers(uid1))
        r = _create(_uid(), name)
        assert r.status_code == 201


# ── ISOLATION ─────────────────────────────────────────────────────────


class TestIsolation:
    def test_separate_users_independent(self):
        uid1, name1 = _uid(), _username()
        uid2, name2 = _uid(), _username()
        _create(uid1, name1, display_name="User1")
        _create(uid2, name2, display_name="User2")
        r1 = requests.get(f"{BASE}/profile", headers=_headers(uid1))
        r2 = requests.get(f"{BASE}/profile", headers=_headers(uid2))
        assert r1.json()["displayName"] == "User1"
        assert r2.json()["displayName"] == "User2"

    def test_update_does_not_affect_other_user(self):
        uid1, uid2 = _uid(), _uid()
        _create(uid1, _username(), display_name="A")
        _create(uid2, _username(), display_name="B")
        requests.patch(
            f"{BASE}/profile",
            json={"displayName": "A-updated"},
            headers=_headers(uid1),
        )
        r = requests.get(f"{BASE}/profile", headers=_headers(uid2))
        assert r.json()["displayName"] == "B"

    def test_delete_does_not_affect_other_user(self):
        uid1, uid2 = _uid(), _uid()
        _create(uid1, _username())
        _create(uid2, _username())
        requests.delete(f"{BASE}/profile", headers=_headers(uid1))
        r = requests.get(f"{BASE}/profile", headers=_headers(uid2))
        assert r.status_code == 200


# ── HEALTH ────────────────────────────────────────────────────────────


class TestHealth:
    def test_health(self):
        r = requests.get(f"{BASE}/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
