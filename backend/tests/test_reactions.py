"""Reaction service integration tests."""

import os

import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")

VALID_TYPES = ["strong", "fire", "heart", "smile", "laugh", "thumbsup", "thumbsdown", "angry"]

# Expected response fields — union of base + response schema properties.
_RESPONSE_FIELDS = {
    "id", "postId", "authorUid", "type",
    "username", "profilePhoto",
}


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str = "reaction-test-user") -> dict:
    return {"X-User-Id": uid}


_test_post_id: str | None = None


def _ensure_profile(uid: str = "reaction-test-user", username: str = "reactiontester"):
    r = requests.get(_url(f"/profiles/{uid}"), headers=_headers(uid))
    if r.status_code == 404:
        body = {
            "username": username,
            "displayName": "Reaction Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        }
        r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
        assert r.status_code == 201


def _create_test_post(uid: str = "reaction-test-user") -> str:
    body = {"body": "Post for reaction testing"}
    r = requests.post(_url("/posts"), json=body, headers=_headers(uid))
    assert r.status_code == 201
    return r.json()["id"]


def setup_module():
    """Clear reactions collection, ensure test profile and post exist."""
    global _test_post_id
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].reactions.delete_many({})
    client.close()
    _ensure_profile()
    _test_post_id = _create_test_post()


def _reactions_url(post_id: str | None = None) -> str:
    pid = post_id or _test_post_id
    return f"/posts/{pid}/reactions"


# ── Set reaction ──────────────────────────────────────────────────────

def test_set_reaction():
    body = {"type": "fire"}
    r = requests.put(_url(_reactions_url()), json=body, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == _RESPONSE_FIELDS
    assert data["type"] == "fire"
    assert data["authorUid"] == "reaction-test-user"
    assert data["postId"] == _test_post_id
    assert data["username"] == "reactiontester"
    assert data["id"] is not None


def test_set_reaction_resolves_profile_photo():
    post_id = _create_test_post()
    body = {"type": "heart"}
    r = requests.put(_url(_reactions_url(post_id=post_id)), json=body, headers=_headers())
    assert r.status_code == 200
    assert r.json()["profilePhoto"] == "https://example.com/photo.jpg"


def test_set_reaction_upserts():
    """Setting a reaction again on the same post updates the type."""
    post_id = _create_test_post()

    r = requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers())
    assert r.status_code == 200
    reaction_id = r.json()["id"]

    # Change to heart
    r = requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "heart"}, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "heart"
    assert data["id"] == reaction_id  # same reaction doc, updated in place


def test_set_reaction_on_nonexistent_post():
    body = {"type": "fire"}
    r = requests.put(
        _url(_reactions_url(post_id="nonexistent123")),
        json=body,
        headers=_headers(),
    )
    assert r.status_code == 404


def test_set_reaction_all_valid_types():
    """All valid reaction types should be accepted."""
    for rtype in VALID_TYPES:
        post_id = _create_test_post()
        r = requests.put(
            _url(_reactions_url(post_id=post_id)),
            json={"type": rtype},
            headers=_headers(),
        )
        assert r.status_code == 200, f"Failed for type: {rtype}"
        assert r.json()["type"] == rtype


# ── List reactions ────────────────────────────────────────────────────

def test_list_reactions_on_post():
    post_id = _create_test_post()

    # Two users react
    _ensure_profile("reactor-a", "reactora")
    _ensure_profile("reactor-b", "reactorb")
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers("reactor-a"))
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "heart"}, headers=_headers("reactor-b"))

    r = requests.get(_url(_reactions_url(post_id=post_id)), headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    for reaction in data:
        assert set(reaction.keys()) == _RESPONSE_FIELDS
        assert reaction["postId"] == post_id


def test_list_reactions_newest_first():
    post_id = _create_test_post()

    _ensure_profile("reactor-c", "reactorc")
    _ensure_profile("reactor-d", "reactord")
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers("reactor-c"))
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "heart"}, headers=_headers("reactor-d"))

    r = requests.get(_url(_reactions_url(post_id=post_id)), headers=_headers())
    data = r.json()
    # Newest first
    assert data[0]["type"] == "heart"
    assert data[1]["type"] == "fire"


def test_list_reactions_nonexistent_post():
    r = requests.get(
        _url(_reactions_url(post_id="nonexistent123")),
        headers=_headers(),
    )
    assert r.status_code == 404


def test_list_reactions_empty():
    post_id = _create_test_post()
    r = requests.get(_url(_reactions_url(post_id=post_id)), headers=_headers())
    assert r.status_code == 200
    assert r.json() == []


# ── Remove reaction ──────────────────────────────────────────────────

def test_remove_reaction():
    post_id = _create_test_post()
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers())

    r = requests.delete(_url(_reactions_url(post_id=post_id)), headers=_headers())
    assert r.status_code == 204

    # Should no longer appear in list
    r = requests.get(_url(_reactions_url(post_id=post_id)), headers=_headers())
    assert r.json() == []


def test_remove_reaction_not_found():
    """Removing when no reaction exists returns 404."""
    post_id = _create_test_post()
    r = requests.delete(_url(_reactions_url(post_id=post_id)), headers=_headers())
    assert r.status_code == 404


def test_remove_reaction_nonexistent_post():
    r = requests.delete(
        _url(_reactions_url(post_id="nonexistent123")),
        headers=_headers(),
    )
    assert r.status_code == 404


def test_remove_does_not_affect_other_users():
    """Removing own reaction doesn't affect another user's reaction."""
    post_id = _create_test_post()

    _ensure_profile("reactor-e", "reactore")
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers())
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "heart"}, headers=_headers("reactor-e"))

    # Remove own reaction
    r = requests.delete(_url(_reactions_url(post_id=post_id)), headers=_headers())
    assert r.status_code == 204

    # Other user's reaction still there
    r = requests.get(_url(_reactions_url(post_id=post_id)), headers=_headers())
    data = r.json()
    assert len(data) == 1
    assert data[0]["authorUid"] == "reactor-e"


# ── Post aggregations ────────────────────────────────────────────────

def test_reaction_summary_on_post():
    """Post's reactionSummary should reflect reactions."""
    post_id = _create_test_post()

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["reactionSummary"] == {}

    _ensure_profile("reactor-f", "reactorf")
    _ensure_profile("reactor-g", "reactorg")
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers("reactor-f"))
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers("reactor-g"))
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "heart"}, headers=_headers())

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    summary = r.json()["reactionSummary"]
    assert summary["fire"] == 2
    assert summary["heart"] == 1


def test_my_reaction_on_post():
    """Post response should include myReaction for the current viewer."""
    post_id = _create_test_post()

    # No reaction yet
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["myReaction"] is None

    # Set a reaction
    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "strong"}, headers=_headers())

    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["myReaction"] == "strong"


def test_reaction_summary_updates_after_remove():
    """Removing a reaction should update the post's reactionSummary."""
    post_id = _create_test_post()

    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers())
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["reactionSummary"]["fire"] == 1

    requests.delete(_url(_reactions_url(post_id=post_id)), headers=_headers())
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["reactionSummary"] == {}


def test_my_reaction_clears_after_remove():
    """myReaction should be null after removing own reaction."""
    post_id = _create_test_post()

    requests.put(_url(_reactions_url(post_id=post_id)), json={"type": "fire"}, headers=_headers())
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["myReaction"] == "fire"

    requests.delete(_url(_reactions_url(post_id=post_id)), headers=_headers())
    r = requests.get(_url(f"/posts/{post_id}"), headers=_headers())
    assert r.json()["myReaction"] is None


# ── Validation ────────────────────────────────────────────────────────

def test_set_invalid_type_rejected():
    body = {"type": "invalid"}
    r = requests.put(_url(_reactions_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_set_empty_body_rejected():
    r = requests.put(_url(_reactions_url()), json={}, headers=_headers())
    assert r.status_code == 422


def test_set_extra_field_rejected():
    body = {"type": "fire", "spam": True}
    r = requests.put(_url(_reactions_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_set_missing_type_rejected():
    body = {"notType": "fire"}
    r = requests.put(_url(_reactions_url()), json=body, headers=_headers())
    assert r.status_code == 422


def test_missing_user_id_header():
    body = {"type": "fire"}
    r = requests.put(_url(_reactions_url()), json=body)
    assert r.status_code == 422
