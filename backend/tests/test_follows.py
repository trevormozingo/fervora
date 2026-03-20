"""Follow service integration tests.

One-way follow model:
  - POST /follows/{uid}    → follow (201), already following (409), no profile (404), self (422)
  - DELETE /follows/{uid}   → unfollow (204), not following (404)
  - GET /follows/following  → list who I follow
  - GET /follows/followers  → list who follows me
  - GET /follows/{uid}/following → list who a user follows
  - GET /follows/{uid}/followers → list who follows a user
"""

import os
import uuid

import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid}


def _uid() -> str:
    return f"ftest-{uuid.uuid4().hex[:12]}"


def _ensure_profile(uid: str):
    username = f"u{uid.replace('-', '')[:14]}"
    r = requests.get(_url(f"/profiles/{uid}"), headers=_headers(uid))
    if r.status_code == 404:
        body = {
            "username": username,
            "displayName": "Follow Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        }
        r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
        assert r.status_code == 201


def setup_module():
    """Clear follows collection."""
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].follows.delete_many({})
    client.close()


def teardown_module():
    pass


# ── Follow ────────────────────────────────────────────────────────────

def test_follow_user():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    r = requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 201
    data = r.json()
    assert data["followerUid"] == a
    assert data["followingUid"] == b


def test_follow_already_following():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r = requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 409


def test_follow_self_rejected():
    a = _uid()
    _ensure_profile(a)
    r = requests.post(_url(f"/follows/{a}"), headers=_headers(a))
    assert r.status_code == 422


def test_follow_target_no_profile():
    a = _uid()
    _ensure_profile(a)
    r = requests.post(_url(f"/follows/{_uid()}"), headers=_headers(a))
    assert r.status_code == 404


def test_follow_follower_no_profile():
    b = _uid()
    _ensure_profile(b)
    r = requests.post(_url(f"/follows/{b}"), headers=_headers(_uid()))
    assert r.status_code == 403


# ── Unfollow ──────────────────────────────────────────────────────────

def test_unfollow_user():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 204


def test_unfollow_not_following():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    r = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 404


def test_unfollow_idempotent():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r1 = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r1.status_code == 204
    r2 = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r2.status_code == 404


def test_unfollow_is_one_directional():
    """A follows B, then A unfollows B — B's follow of A is unaffected."""
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    requests.post(_url(f"/follows/{a}"), headers=_headers(b))
    # A unfollows B
    requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    # B should still follow A
    r = requests.get(_url("/follows/following"), headers=_headers(b))
    following_ids = [p["id"] for p in r.json()["following"]]
    assert a in following_ids


# ── List following/followers ──────────────────────────────────────────

def test_following_list():
    a, b, c = _uid(), _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    _ensure_profile(c)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    requests.post(_url(f"/follows/{c}"), headers=_headers(a))
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    assert r.status_code == 200
    data = r.json()
    following_ids = {p["id"] for p in data["following"]}
    assert following_ids == {b, c}
    assert data["count"] == 2


def test_followers_list():
    a, b, c = _uid(), _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    _ensure_profile(c)
    requests.post(_url(f"/follows/{a}"), headers=_headers(b))
    requests.post(_url(f"/follows/{a}"), headers=_headers(c))
    r = requests.get(_url("/follows/followers"), headers=_headers(a))
    assert r.status_code == 200
    data = r.json()
    follower_ids = {p["id"] for p in data["followers"]}
    assert follower_ids == {b, c}
    assert data["count"] == 2


def test_empty_following():
    a = _uid()
    _ensure_profile(a)
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    assert r.json() == {"following": [], "count": 0}


def test_empty_followers():
    a = _uid()
    _ensure_profile(a)
    r = requests.get(_url("/follows/followers"), headers=_headers(a))
    assert r.json() == {"followers": [], "count": 0}


def test_follow_is_not_mutual():
    """A follows B does NOT mean B follows A."""
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    # A follows B
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    following_ids = [p["id"] for p in r.json()["following"]]
    assert b in following_ids
    # B does NOT follow A
    r = requests.get(_url("/follows/following"), headers=_headers(b))
    following_ids = [p["id"] for p in r.json()["following"]]
    assert a not in following_ids


def test_list_other_user_following():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    # Third party can see A's following list
    r = requests.get(_url(f"/follows/{a}/following"), headers=_headers(b))
    assert r.status_code == 200
    following_ids = [p["id"] for p in r.json()["following"]]
    assert b in following_ids


def test_list_other_user_followers():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    # Third party can see B's followers list
    r = requests.get(_url(f"/follows/{b}/followers"), headers=_headers(a))
    assert r.status_code == 200
    follower_ids = [p["id"] for p in r.json()["followers"]]
    assert a in follower_ids


# ── Profile counts ────────────────────────────────────────────────────

def test_follow_updates_profile_counts():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)

    # Initially 0
    r = requests.get(_url(f"/profiles/{a}"), headers=_headers(a))
    assert r.json()["followingCount"] == 0

    requests.post(_url(f"/follows/{b}"), headers=_headers(a))

    # A's followingCount = 1, B's followersCount = 1
    r = requests.get(_url(f"/profiles/{a}"), headers=_headers(a))
    assert r.json()["followingCount"] == 1

    r = requests.get(_url(f"/profiles/{b}"), headers=_headers(b))
    assert r.json()["followersCount"] == 1


def test_unfollow_updates_profile_counts():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)

    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    requests.delete(_url(f"/follows/{b}"), headers=_headers(a))

    r = requests.get(_url(f"/profiles/{a}"), headers=_headers(a))
    assert r.json()["followingCount"] == 0

    r = requests.get(_url(f"/profiles/{b}"), headers=_headers(b))
    assert r.json()["followersCount"] == 0


# ── Resolved profiles in follow lists ────────────────────────────────

def test_following_list_has_profile_fields():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    profile = r.json()["following"][0]
    assert "id" in profile
    assert "username" in profile
    assert "displayName" in profile
    assert "profilePhoto" in profile
