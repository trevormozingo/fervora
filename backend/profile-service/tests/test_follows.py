"""
Follow integration tests.

One-way follow model:
  - POST /follows/{uid}    → follow (201), already following (409), no profile (404), self (422)
  - DELETE /follows/{uid}   → unfollow (204), not following (404)
  - GET /follows/following  → list who I follow
  - GET /follows/followers  → list who follows me

Key constraints:
  - Both follower and target must have profiles
  - Cannot follow yourself
  - Cascade: deleting a profile removes all follows in both directions
"""

import os
import uuid

import pymongo
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


def _create_profile(uid: str, username: str) -> requests.Response:
    return requests.post(
        f"{BASE}/profile", json={"username": username}, headers=_headers(uid)
    )


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.profiles.delete_many({})
    db.posts.delete_many({})
    db.follows.delete_many({})
    client.close()


# ── FOLLOW ────────────────────────────────────────────────────────────


class TestFollow:
    def test_follow_user(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        r = requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        assert r.status_code == 201
        data = r.json()
        assert data["followerUid"] == a
        assert data["followingUid"] == b

    def test_follow_already_following(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        r = requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        assert r.status_code == 409

    def test_follow_self_rejected(self):
        a = _uid()
        _create_profile(a, _username())
        r = requests.post(f"{BASE}/follows/{a}", headers=_headers(a))
        assert r.status_code == 422

    def test_follow_target_no_profile(self):
        a = _uid()
        _create_profile(a, _username())
        r = requests.post(f"{BASE}/follows/{_uid()}", headers=_headers(a))
        assert r.status_code == 404

    def test_follow_follower_no_profile(self):
        b = _uid()
        _create_profile(b, _username())
        r = requests.post(f"{BASE}/follows/{b}", headers=_headers(_uid()))
        assert r.status_code == 404

    def test_follow_neither_has_profile(self):
        r = requests.post(f"{BASE}/follows/{_uid()}", headers=_headers(_uid()))
        assert r.status_code == 404


# ── UNFOLLOW ──────────────────────────────────────────────────────────


class TestUnfollow:
    def test_unfollow_user(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        r = requests.delete(f"{BASE}/follows/{b}", headers=_headers(a))
        assert r.status_code == 204

    def test_unfollow_not_following(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        r = requests.delete(f"{BASE}/follows/{b}", headers=_headers(a))
        assert r.status_code == 404

    def test_unfollow_idempotent(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        r1 = requests.delete(f"{BASE}/follows/{b}", headers=_headers(a))
        assert r1.status_code == 204
        r2 = requests.delete(f"{BASE}/follows/{b}", headers=_headers(a))
        assert r2.status_code == 404

    def test_unfollow_is_one_directional(self):
        """A follows B, then A unfollows B — B's follow of A (if any) is unaffected."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        requests.post(f"{BASE}/follows/{a}", headers=_headers(b))
        # A unfollows B
        requests.delete(f"{BASE}/follows/{b}", headers=_headers(a))
        # B should still follow A
        r = requests.get(f"{BASE}/follows/following", headers=_headers(b))
        assert a in r.json()["following"]


# ── LIST FOLLOWING / FOLLOWERS ────────────────────────────────────────


class TestLists:
    def test_following_list(self):
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        requests.post(f"{BASE}/follows/{c}", headers=_headers(a))
        r = requests.get(f"{BASE}/follows/following", headers=_headers(a))
        assert r.status_code == 200
        data = r.json()
        assert set(data["following"]) == {b, c}
        assert data["count"] == 2

    def test_followers_list(self):
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        requests.post(f"{BASE}/follows/{a}", headers=_headers(b))
        requests.post(f"{BASE}/follows/{a}", headers=_headers(c))
        r = requests.get(f"{BASE}/follows/followers", headers=_headers(a))
        assert r.status_code == 200
        data = r.json()
        assert set(data["followers"]) == {b, c}
        assert data["count"] == 2

    def test_empty_following(self):
        a = _uid()
        _create_profile(a, _username())
        r = requests.get(f"{BASE}/follows/following", headers=_headers(a))
        assert r.json() == {"following": [], "count": 0}

    def test_empty_followers(self):
        a = _uid()
        _create_profile(a, _username())
        r = requests.get(f"{BASE}/follows/followers", headers=_headers(a))
        assert r.json() == {"followers": [], "count": 0}

    def test_follow_is_not_mutual(self):
        """A follows B does NOT mean B follows A."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        # A follows B
        r = requests.get(f"{BASE}/follows/following", headers=_headers(a))
        assert b in r.json()["following"]
        # B does NOT follow A
        r = requests.get(f"{BASE}/follows/following", headers=_headers(b))
        assert a not in r.json()["following"]


# ── CASCADE DELETE ────────────────────────────────────────────────────


class TestFollowCascade:
    def test_delete_profile_removes_outgoing_follows(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # B should have no followers
        r = requests.get(f"{BASE}/follows/followers", headers=_headers(b))
        assert r.json()["count"] == 0

    def test_delete_profile_removes_incoming_follows(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        requests.post(f"{BASE}/follows/{a}", headers=_headers(b))
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # B should no longer be following anyone
        r = requests.get(f"{BASE}/follows/following", headers=_headers(b))
        assert r.json()["count"] == 0

    def test_cascade_does_not_affect_other_follows(self):
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        requests.post(f"{BASE}/follows/{b}", headers=_headers(a))
        requests.post(f"{BASE}/follows/{c}", headers=_headers(b))
        # Delete A — B→C follow should survive
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        r = requests.get(f"{BASE}/follows/following", headers=_headers(b))
        assert c in r.json()["following"]
