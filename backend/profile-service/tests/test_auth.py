"""
Authentication & Authorization tests.

Verifies that:
  - All mutations reject unauthenticated callers (user_id=None).
  - Users cannot mutate resources they don't own.
"""
import pytest

# ── Mutation strings ──────────────────────────────────────────────────────────

_CREATE_PROFILE = """mutation { createProfile(input: {
  username:"testuser", displayName:"X", profilePhoto:"http://x.com/p.jpg", birthday:"1990-01-01"
}) { id } }"""

_UPDATE_PROFILE = """mutation { updateProfile(input: { displayName: "New" }) { id } }"""
_DELETE_PROFILE = """mutation { deleteProfile }"""

_CREATE_POST = """mutation { createPost(input: { title: "T" }) { id } }"""
_UPDATE_POST = """mutation ($id: ID!) { updatePost(input: { id: $id, title: "T2" }) { id } }"""
_DELETE_POST = """mutation ($id: ID!) { deletePost(id: $id) }"""

_CREATE_COMMENT = """mutation ($pid: ID!) {
  createComment(input: { postId: $pid, body: "hi" }) { id }
}"""
_DELETE_COMMENT = """mutation ($id: ID!) { deleteComment(id: $id) }"""

_SET_REACTION = """mutation ($pid: ID!) {
  setReaction(input: { postId: $pid, reactionType: "fire" }) { id }
}"""
_DELETE_REACTION = """mutation ($pid: ID!) { deleteReaction(postId: $pid) }"""

_CREATE_EVENT = """mutation {
  createEvent(input: { title: "Run", startsAt: "2026-06-01T07:00:00Z" }) { id }
}"""
_RSVP_EVENT = """mutation ($eid: ID!) {
  rsvpEvent(input: { eventId: $eid, status: "going" })
}"""
_DELETE_EVENT = """mutation ($id: ID!) { deleteEvent(id: $id) }"""

_ME = """query { me { id } }"""
_FEED = """query { feed { posts { id } nextCursor } }"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth_error(result) -> bool:
    return (
        result.errors is not None
        and any("authentication required" in str(e.message) for e in result.errors)
    )


# ── Unauthenticated rejection tests ──────────────────────────────────────────

async def test_create_profile_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_CREATE_PROFILE, user_id=None))

async def test_update_profile_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_UPDATE_PROFILE, user_id=None))

async def test_delete_profile_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_DELETE_PROFILE, user_id=None))

async def test_create_post_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_CREATE_POST, user_id=None))

async def test_update_post_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_UPDATE_POST, {"id": "000000000000000000000001"}, user_id=None))

async def test_delete_post_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_DELETE_POST, {"id": "000000000000000000000001"}, user_id=None))

async def test_create_comment_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_CREATE_COMMENT, {"pid": "000000000000000000000001"}, user_id=None))

async def test_delete_comment_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_DELETE_COMMENT, {"id": "000000000000000000000001"}, user_id=None))

async def test_set_reaction_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_SET_REACTION, {"pid": "000000000000000000000001"}, user_id=None))

async def test_delete_reaction_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_DELETE_REACTION, {"pid": "000000000000000000000001"}, user_id=None))

async def test_create_event_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_CREATE_EVENT, user_id=None))

async def test_rsvp_event_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_RSVP_EVENT, {"eid": "000000000000000000000001"}, user_id=None))

async def test_delete_event_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_DELETE_EVENT, {"id": "000000000000000000000001"}, user_id=None))

async def test_me_query_rejects_unauthenticated(gql):
    assert _auth_error(await gql(_ME, user_id=None))

async def test_follow_rejects_unauthenticated(gql):
    result = await gql("mutation { followUser(userId: \"uid2\") }", user_id=None)
    assert result.errors is not None

async def test_unfollow_rejects_unauthenticated(gql):
    result = await gql("mutation { unfollowUser(userId: \"uid2\") }", user_id=None)
    assert result.errors is not None


# ── Authorization-bounds tests ────────────────────────────────────────────────

async def test_cannot_delete_anothers_post(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    result = await gql(_DELETE_POST, {"id": pid}, user_id="uid2")
    assert result.errors is None          # no crash
    assert result.data["deletePost"] is False  # nothing modified

async def test_cannot_update_anothers_post(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    result = await gql(_UPDATE_POST, {"id": pid}, user_id="uid2")
    assert result.errors is not None
    assert "not found or unauthorized" in str(result.errors[0].message)

async def test_cannot_delete_anothers_comment(gql, make_profile, make_post, make_comment):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid1", pid)

    result = await gql(_DELETE_COMMENT, {"id": cid}, user_id="uid2")
    assert result.errors is None
    assert result.data["deleteComment"] is False

async def test_cannot_delete_anothers_event(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")

    result = await gql(_DELETE_EVENT, {"id": eid}, user_id="uid2")
    assert result.errors is None
    assert result.data["deleteEvent"] is False

async def test_cannot_delete_anothers_profile(gql, make_profile):
    await make_profile("uid1", "alice")
    # uid2 tries to delete uid1's profile — deleteProfile always deletes the caller's own profile
    # uid2 has no profile, so the update finds nothing
    result = await gql(_DELETE_PROFILE, user_id="uid2")
    assert result.errors is None
    assert result.data["deleteProfile"] is False
