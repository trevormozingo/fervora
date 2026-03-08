"""
Integration tests for the API Gateway.

Uses the Firebase Auth Emulator to create real test users and obtain
genuine ID tokens. Tests verify that the gateway:
  1. Requires a valid Bearer token for protected endpoints
  2. Proxies requests to the profile-service correctly
  3. Injects X-User-Id from the verified Firebase UID
  4. Allows unauthenticated access to public endpoints
  5. Returns proper error codes for missing/invalid auth
  6. Proxies posts, follows, feed, reactions, comments, events
"""

import json
import os
import uuid

import requests

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
EMULATOR_HOST = os.getenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "ironguild-local")

# Firebase Auth Emulator REST endpoints
_EMULATOR_SIGNUP_URL = (
    f"http://{EMULATOR_HOST}/identitytoolkit.googleapis.com/v1"
    f"/accounts:signUp?key=fake-api-key"
)
_EMULATOR_SIGNIN_URL = (
    f"http://{EMULATOR_HOST}/identitytoolkit.googleapis.com/v1"
    f"/accounts:signInWithPassword?key=fake-api-key"
)
_EMULATOR_DELETE_URL = (
    f"http://{EMULATOR_HOST}/emulator/v1/projects/{PROJECT_ID}/accounts"
)


def _create_emulator_user(email: str = None, password: str = "testpass123"):
    """
    Create a user in the Firebase Auth Emulator and return (uid, id_token).
    """
    if email is None:
        email = f"test-{uuid.uuid4().hex[:8]}@test.com"

    resp = requests.post(
        _EMULATOR_SIGNUP_URL,
        json={"email": email, "password": password, "returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["localId"], data["idToken"]


def _sign_in(email: str, password: str = "testpass123"):
    """Sign in an existing emulator user and return (uid, id_token)."""
    resp = requests.post(
        _EMULATOR_SIGNIN_URL,
        json={"email": email, "password": password, "returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["localId"], data["idToken"]


def auth_header(token: str) -> dict:
    """Build an Authorization header with a Bearer token."""
    return {"Authorization": f"Bearer {token}"}


def unique_username() -> str:
    return f"gw_{uuid.uuid4().hex[:10]}"


def _create_user_with_profile(username: str = None):
    """Helper: create a Firebase user AND a profile. Returns (uid, token, username)."""
    uid, token = _create_emulator_user()
    uname = username or unique_username()
    resp = requests.post(
        f"{GATEWAY_URL}/profile",
        json={"username": uname},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    return uid, token, uname


def _cleanup_profile(token: str):
    """Helper: delete profile via gateway."""
    requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))


def setup_module():
    """Verify gateway and emulator are reachable."""
    resp = requests.get(f"{GATEWAY_URL}/health")
    assert resp.status_code == 200
    resp = requests.get(f"http://{EMULATOR_HOST}/")
    assert resp.status_code == 200


def teardown_module():
    """Delete all emulator accounts."""
    requests.delete(_EMULATOR_DELETE_URL)


# ─────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────

class TestHealth:

    def test_gateway_health(self):
        resp = requests.get(f"{GATEWAY_URL}/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "api-gateway"


# ─────────────────────────────────────────────────────────────────────
# Auth enforcement
# ─────────────────────────────────────────────────────────────────────

class TestAuthEnforcement:

    def test_post_profile_no_token_401(self):
        """POST /profile without Bearer token returns 401."""
        resp = requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": "notoken"},
        )
        assert resp.status_code == 401

    def test_get_own_profile_no_token_401(self):
        """GET /profile without Bearer token returns 401."""
        resp = requests.get(f"{GATEWAY_URL}/profile")
        assert resp.status_code == 401

    def test_patch_profile_no_token_401(self):
        """PATCH /profile without Bearer token returns 401."""
        resp = requests.patch(
            f"{GATEWAY_URL}/profile",
            json={"bio": "hacker"},
        )
        assert resp.status_code == 401

    def test_delete_profile_no_token_401(self):
        """DELETE /profile without Bearer token returns 401."""
        resp = requests.delete(f"{GATEWAY_URL}/profile")
        assert resp.status_code == 401

    def test_invalid_token_401(self):
        """A garbage token should return 401."""
        resp = requests.get(
            f"{GATEWAY_URL}/profile",
            headers=auth_header("this-is-not-a-valid-token"),
        )
        assert resp.status_code == 401

    def test_public_profile_no_token_ok(self):
        """GET /profile/{username} should NOT require auth."""
        # Will 404 because user doesn't exist, but NOT 401
        resp = requests.get(f"{GATEWAY_URL}/profile/nonexistent")
        assert resp.status_code != 401


# ─────────────────────────────────────────────────────────────────────
# Profile CRUD through the gateway (with real emulator tokens)
# ─────────────────────────────────────────────────────────────────────

class TestProfileCrudViaGateway:

    def test_create_profile(self):
        """POST /profile with a real emulator token creates a profile."""
        uid, token = _create_emulator_user()
        username = unique_username()
        resp = requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == username

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))

    def test_get_own_profile(self):
        """GET /profile returns the authenticated user's profile."""
        uid, token = _create_emulator_user()
        username = unique_username()
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )

        resp = requests.get(f"{GATEWAY_URL}/profile", headers=auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == username

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))

    def test_update_profile(self):
        """PATCH /profile updates the profile."""
        uid, token = _create_emulator_user()
        username = unique_username()
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )

        resp = requests.patch(
            f"{GATEWAY_URL}/profile",
            json={"bio": "Updated via gateway"},
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["bio"] == "Updated via gateway"

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))

    def test_get_public_profile(self):
        """GET /profile/{username} returns the public profile (no auth needed)."""
        uid, token = _create_emulator_user()
        username = unique_username()
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )

        resp = requests.get(f"{GATEWAY_URL}/profile/{username}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == username
        assert "id" in body
        assert "createdAt" not in body

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))

    def test_delete_profile(self):
        """DELETE /profile removes the profile."""
        uid, token = _create_emulator_user()
        username = unique_username()
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )

        resp = requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))
        assert resp.status_code == 204

    def test_get_after_delete_404(self):
        """GET /profile after deletion returns 404."""
        uid, token = _create_emulator_user()
        username = unique_username()
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))

        resp = requests.get(f"{GATEWAY_URL}/profile", headers=auth_header(token))
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# User isolation — different Firebase users are different profiles
# ─────────────────────────────────────────────────────────────────────

class TestUserIsolation:

    def test_two_users_have_separate_profiles(self):
        """Two Firebase users create separate profiles."""
        uid_a, token_a = _create_emulator_user()
        uid_b, token_b = _create_emulator_user()
        username_a = unique_username()
        username_b = unique_username()

        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username_a},
            headers=auth_header(token_a),
        )
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username_b},
            headers=auth_header(token_b),
        )

        resp_a = requests.get(f"{GATEWAY_URL}/profile", headers=auth_header(token_a))
        resp_b = requests.get(f"{GATEWAY_URL}/profile", headers=auth_header(token_b))

        assert resp_a.json()["username"] == username_a
        assert resp_b.json()["username"] == username_b

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token_a))
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token_b))

    def test_user_b_cannot_modify_user_a(self):
        """PATCH with user B's token only affects user B's profile."""
        uid_a, token_a = _create_emulator_user()
        uid_b, token_b = _create_emulator_user()

        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": unique_username()},
            headers=auth_header(token_a),
        )
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": unique_username()},
            headers=auth_header(token_b),
        )

        # User B updates their own bio
        requests.patch(
            f"{GATEWAY_URL}/profile",
            json={"bio": "I am user B"},
            headers=auth_header(token_b),
        )

        # User A's bio should be unchanged
        resp_a = requests.get(f"{GATEWAY_URL}/profile", headers=auth_header(token_a))
        assert resp_a.json()["bio"] is None

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token_a))
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token_b))


# ─────────────────────────────────────────────────────────────────────
# Validation passthrough
# ─────────────────────────────────────────────────────────────────────

class TestValidationPassthrough:

    def test_create_bad_username_422(self):
        """Validation errors from profile-service are passed through."""
        _, token = _create_emulator_user()
        resp = requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": "ab"},  # too short
            headers=auth_header(token),
        )
        assert resp.status_code == 422

    def test_update_empty_body_422(self):
        """Empty PATCH body should be rejected by profile-service."""
        _, token = _create_emulator_user()
        username = unique_username()
        requests.post(
            f"{GATEWAY_URL}/profile",
            json={"username": username},
            headers=auth_header(token),
        )

        resp = requests.patch(
            f"{GATEWAY_URL}/profile",
            json={},
            headers=auth_header(token),
        )
        assert resp.status_code == 422

        # Clean up
        requests.delete(f"{GATEWAY_URL}/profile", headers=auth_header(token))


# ─────────────────────────────────────────────────────────────────────
# Post routes through the gateway
# ─────────────────────────────────────────────────────────────────────

class TestPostsViaGateway:

    def test_create_post_requires_auth(self):
        """POST /posts without auth returns 401."""
        resp = requests.post(f"{GATEWAY_URL}/posts", json={"body": "hello"})
        assert resp.status_code == 401

    def test_create_and_delete_post(self):
        """Create a post, verify 201, then delete it."""
        uid, token, _ = _create_user_with_profile()

        resp = requests.post(
            f"{GATEWAY_URL}/posts",
            json={"body": "My first post"},
            headers=auth_header(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["body"] == "My first post"
        assert body["authorUid"] == uid
        post_id = body["id"]

        # Delete the post
        resp = requests.delete(
            f"{GATEWAY_URL}/posts/{post_id}",
            headers=auth_header(token),
        )
        assert resp.status_code == 204

        _cleanup_profile(token)

    def test_create_post_no_profile_403(self):
        """Creating a post without a profile returns 403."""
        _, token = _create_emulator_user()
        resp = requests.post(
            f"{GATEWAY_URL}/posts",
            json={"body": "orphan post"},
            headers=auth_header(token),
        )
        assert resp.status_code == 403

    def test_delete_nonexistent_post_404(self):
        """Deleting a post that doesn't exist returns 404."""
        uid, token, _ = _create_user_with_profile()
        resp = requests.delete(
            f"{GATEWAY_URL}/posts/000000000000000000000000",
            headers=auth_header(token),
        )
        assert resp.status_code == 404
        _cleanup_profile(token)


# ─────────────────────────────────────────────────────────────────────
# Follow routes through the gateway
# ─────────────────────────────────────────────────────────────────────

class TestFollowsViaGateway:

    def test_follow_requires_auth(self):
        """POST /follows/{uid} without auth returns 401."""
        resp = requests.post(f"{GATEWAY_URL}/follows/some-uid")
        assert resp.status_code == 401

    def test_follow_and_unfollow(self):
        """Follow another user, verify, then unfollow."""
        _, token_a, _ = _create_user_with_profile()
        uid_b, token_b, _ = _create_user_with_profile()

        # A follows B
        resp = requests.post(
            f"{GATEWAY_URL}/follows/{uid_b}",
            headers=auth_header(token_a),
        )
        assert resp.status_code == 201

        # Check following list
        resp = requests.get(
            f"{GATEWAY_URL}/follows/following",
            headers=auth_header(token_a),
        )
        assert resp.status_code == 200
        assert uid_b in resp.json()["following"]

        # Check followers list
        resp = requests.get(
            f"{GATEWAY_URL}/follows/followers",
            headers=auth_header(token_b),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["followers"]) >= 1

        # Unfollow
        resp = requests.delete(
            f"{GATEWAY_URL}/follows/{uid_b}",
            headers=auth_header(token_a),
        )
        assert resp.status_code == 204

        _cleanup_profile(token_a)
        _cleanup_profile(token_b)

    def test_follow_self_422(self):
        """Following yourself returns 422."""
        uid, token, _ = _create_user_with_profile()
        resp = requests.post(
            f"{GATEWAY_URL}/follows/{uid}",
            headers=auth_header(token),
        )
        assert resp.status_code == 422
        _cleanup_profile(token)

    def test_get_following_requires_auth(self):
        """GET /follows/following without auth returns 401."""
        resp = requests.get(f"{GATEWAY_URL}/follows/following")
        assert resp.status_code == 401

    def test_get_followers_requires_auth(self):
        """GET /follows/followers without auth returns 401."""
        resp = requests.get(f"{GATEWAY_URL}/follows/followers")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Feed routes through the gateway
# ─────────────────────────────────────────────────────────────────────

class TestFeedViaGateway:

    def test_feed_requires_auth(self):
        """GET /feed without auth returns 401."""
        resp = requests.get(f"{GATEWAY_URL}/feed")
        assert resp.status_code == 401

    def test_feed_shows_followed_posts(self):
        """Posts from followed users appear in the feed."""
        _, token_a, _ = _create_user_with_profile()
        uid_b, token_b, _ = _create_user_with_profile()

        # A follows B
        requests.post(
            f"{GATEWAY_URL}/follows/{uid_b}",
            headers=auth_header(token_a),
        )

        # B creates a post
        resp = requests.post(
            f"{GATEWAY_URL}/posts",
            json={"body": "Post for feed"},
            headers=auth_header(token_b),
        )
        assert resp.status_code == 201

        # A's feed should contain B's post
        resp = requests.get(
            f"{GATEWAY_URL}/feed",
            headers=auth_header(token_a),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 1
        assert any(p["body"] == "Post for feed" for p in body["items"])

        _cleanup_profile(token_a)
        _cleanup_profile(token_b)

    def test_feed_empty_for_new_user(self):
        """A new user with no follows has an empty feed."""
        _, token, _ = _create_user_with_profile()
        resp = requests.get(
            f"{GATEWAY_URL}/feed",
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        _cleanup_profile(token)


# ─────────────────────────────────────────────────────────────────────
# Reaction routes through the gateway
# ─────────────────────────────────────────────────────────────────────

class TestReactionsViaGateway:

    def test_set_reaction_requires_auth(self):
        """PUT /posts/{id}/reactions without auth returns 401."""
        resp = requests.put(
            f"{GATEWAY_URL}/posts/000000000000000000000000/reactions",
            json={"type": "fire"},
        )
        assert resp.status_code == 401

    def test_reaction_lifecycle(self):
        """Set a reaction, read it, then remove it."""
        _, token, _ = _create_user_with_profile()

        # Create a post to react to
        resp = requests.post(
            f"{GATEWAY_URL}/posts",
            json={"body": "React to me"},
            headers=auth_header(token),
        )
        post_id = resp.json()["id"]

        # Set reaction
        resp = requests.put(
            f"{GATEWAY_URL}/posts/{post_id}/reactions",
            json={"type": "fire"},
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "fire"

        # Get reactions (no auth needed)
        resp = requests.get(f"{GATEWAY_URL}/posts/{post_id}/reactions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        # Remove reaction
        resp = requests.delete(
            f"{GATEWAY_URL}/posts/{post_id}/reactions",
            headers=auth_header(token),
        )
        assert resp.status_code == 204

        _cleanup_profile(token)

    def test_get_reactions_no_auth(self):
        """GET /posts/{id}/reactions does NOT require auth."""
        resp = requests.get(
            f"{GATEWAY_URL}/posts/000000000000000000000000/reactions"
        )
        # Should succeed (empty list), not 401
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# Comment routes through the gateway
# ─────────────────────────────────────────────────────────────────────

class TestCommentsViaGateway:

    def test_create_comment_requires_auth(self):
        """POST /posts/{id}/comments without auth returns 401."""
        resp = requests.post(
            f"{GATEWAY_URL}/posts/000000000000000000000000/comments",
            json={"body": "hello"},
        )
        assert resp.status_code == 401

    def test_comment_lifecycle(self):
        """Create a comment, read it, then delete it."""
        _, token, _ = _create_user_with_profile()

        # Create a post to comment on
        resp = requests.post(
            f"{GATEWAY_URL}/posts",
            json={"body": "Comment on me"},
            headers=auth_header(token),
        )
        post_id = resp.json()["id"]

        # Create comment
        resp = requests.post(
            f"{GATEWAY_URL}/posts/{post_id}/comments",
            json={"body": "Nice post!"},
            headers=auth_header(token),
        )
        assert resp.status_code == 201
        comment_id = resp.json()["id"]
        assert resp.json()["body"] == "Nice post!"

        # Get comments (no auth needed)
        resp = requests.get(f"{GATEWAY_URL}/posts/{post_id}/comments")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        # Delete comment
        resp = requests.delete(
            f"{GATEWAY_URL}/posts/{post_id}/comments/{comment_id}",
            headers=auth_header(token),
        )
        assert resp.status_code == 204

        _cleanup_profile(token)

    def test_get_comments_no_auth(self):
        """GET /posts/{id}/comments does NOT require auth."""
        resp = requests.get(
            f"{GATEWAY_URL}/posts/000000000000000000000000/comments"
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# Event routes through the gateway
# ─────────────────────────────────────────────────────────────────────

class TestEventsViaGateway:

    def test_create_event_requires_auth(self):
        """POST /events without auth returns 401."""
        resp = requests.post(
            f"{GATEWAY_URL}/events",
            json={"title": "Workout", "startTime": "2026-04-01T10:00:00Z"},
        )
        assert resp.status_code == 401

    def test_event_crud(self):
        """Create, read, and delete an event through the gateway."""
        _, token, _ = _create_user_with_profile()

        # Create event
        resp = requests.post(
            f"{GATEWAY_URL}/events",
            json={"title": "Leg Day", "startTime": "2026-04-01T10:00:00Z"},
            headers=auth_header(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Leg Day"
        event_id = body["id"]

        # Get own events
        resp = requests.get(
            f"{GATEWAY_URL}/events",
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

        # Get event by ID (no auth needed)
        resp = requests.get(f"{GATEWAY_URL}/events/{event_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Leg Day"

        # Delete event
        resp = requests.delete(
            f"{GATEWAY_URL}/events/{event_id}",
            headers=auth_header(token),
        )
        assert resp.status_code == 204

        _cleanup_profile(token)

    def test_event_rsvp(self):
        """Invite a user and RSVP through the gateway."""
        uid_a, token_a, _ = _create_user_with_profile()
        uid_b, token_b, _ = _create_user_with_profile()

        # A creates event, invites B
        resp = requests.post(
            f"{GATEWAY_URL}/events",
            json={
                "title": "Sparring Session",
                "startTime": "2026-04-05T14:00:00Z",
                "inviteeUids": [uid_b],
            },
            headers=auth_header(token_a),
        )
        assert resp.status_code == 201
        event_id = resp.json()["id"]

        # B checks invited events
        resp = requests.get(
            f"{GATEWAY_URL}/events/invited",
            headers=auth_header(token_b),
        )
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

        # B RSVPs accepted
        resp = requests.put(
            f"{GATEWAY_URL}/events/{event_id}/rsvp",
            json={"status": "accepted"},
            headers=auth_header(token_b),
        )
        assert resp.status_code == 200
        invitees = resp.json()["invitees"]
        match = [i for i in invitees if i["uid"] == uid_b]
        assert match[0]["status"] == "accepted"

        _cleanup_profile(token_a)
        _cleanup_profile(token_b)

    def test_event_ical_export(self):
        """GET /events/{id}/ical returns an .ics file."""
        _, token, _ = _create_user_with_profile()

        resp = requests.post(
            f"{GATEWAY_URL}/events",
            json={"title": "iCal Test", "startTime": "2026-04-10T08:00:00Z"},
            headers=auth_header(token),
        )
        event_id = resp.json()["id"]

        # iCal export (no auth needed)
        resp = requests.get(f"{GATEWAY_URL}/events/{event_id}/ical")
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]
        assert b"iCal Test" in resp.content

        _cleanup_profile(token)

    def test_get_event_no_auth(self):
        """GET /events/{id} does NOT require auth."""
        resp = requests.get(
            f"{GATEWAY_URL}/events/000000000000000000000000"
        )
        # 404 is fine — the point is it's not 401
        assert resp.status_code != 401

    def test_get_ical_no_auth(self):
        """GET /events/{id}/ical does NOT require auth."""
        resp = requests.get(
            f"{GATEWAY_URL}/events/000000000000000000000000/ical"
        )
        assert resp.status_code != 401

    def test_list_events_requires_auth(self):
        """GET /events without auth returns 401."""
        resp = requests.get(f"{GATEWAY_URL}/events")
        assert resp.status_code == 401

    def test_list_invited_requires_auth(self):
        """GET /events/invited without auth returns 401."""
        resp = requests.get(f"{GATEWAY_URL}/events/invited")
        assert resp.status_code == 401

    def test_rsvp_requires_auth(self):
        """PUT /events/{id}/rsvp without auth returns 401."""
        resp = requests.put(
            f"{GATEWAY_URL}/events/000000000000000000000000/rsvp",
            json={"status": "accepted"},
        )
        assert resp.status_code == 401

    def test_delete_event_requires_auth(self):
        """DELETE /events/{id} without auth returns 401."""
        resp = requests.delete(
            f"{GATEWAY_URL}/events/000000000000000000000000"
        )
        assert resp.status_code == 401
