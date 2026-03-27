"""Profile CRUD and query tests."""
import pytest
from .conftest import worker_cascade_profile_deleted

# ── Mutations ─────────────────────────────────────────────────────────────────

CREATE = """
mutation CreateProfile($input: CreateProfileInput!) {
  createProfile(input: $input) {
    id username displayName bio profilePhoto birthday fitnessLevel
  }
}
"""

UPDATE = """
mutation UpdateProfile($input: UpdateProfileInput!) {
  updateProfile(input: $input) {
    id username displayName bio profilePhoto fitnessLevel
  }
}
"""

DELETE = "mutation { deleteProfile }"

# ── Queries ───────────────────────────────────────────────────────────────────

ME = "query { me { id username displayName bio } }"

PROFILE_Q = """
query Profile($id: ID!) {
  profile(id: $id) {
    id username displayName viewerIsFollowing
    posts(limit: 5) { posts { id title } nextCursor }
    followers(limit: 5) { users { id username } nextCursor }
    following(limit: 5) { users { id username } nextCursor }
  }
}
"""

# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_profile_success(gql, redis):
    inp = {
        "username": "alice99",
        "displayName": "Alice",
        "profilePhoto": "https://example.com/alice.jpg",
        "birthday": "1990-06-15",
        "bio": "I lift things.",
        "fitnessLevel": "intermediate",
    }
    r = await gql(CREATE, {"input": inp}, user_id="uid1")
    assert r.errors is None
    data = r.data["createProfile"]
    assert data["username"] == "alice99"
    assert data["displayName"] == "Alice"
    assert data["bio"] == "I lift things."
    assert data["fitnessLevel"] == "intermediate"
    # Redis cache was populated
    cached = await redis.get("profile:uid1")
    assert cached is not None and cached != "__nil__"

async def test_create_profile_duplicate_user_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"username": "alice2", "displayName": "A",
                                     "profilePhoto": "x", "birthday": "1990-01-01"}}, user_id="uid1")
    assert r.errors is not None
    assert "already exists" in r.errors[0].message

async def test_create_profile_duplicate_username_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"username": "alice", "displayName": "B",
                                     "profilePhoto": "x", "birthday": "1990-01-01"}}, user_id="uid2")
    assert r.errors is not None
    assert "already taken" in r.errors[0].message

async def test_create_profile_username_case_insensitive_unique(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"username": "ALICE", "displayName": "B",
                                     "profilePhoto": "x", "birthday": "1990-01-01"}}, user_id="uid2")
    assert r.errors is not None
    assert "already taken" in r.errors[0].message

async def test_create_profile_username_too_short(gql):
    r = await gql(CREATE, {"input": {"username": "ab", "displayName": "A",
                                     "profilePhoto": "x", "birthday": "1990-01-01"}}, user_id="uid1")
    assert r.errors is not None

async def test_create_profile_username_too_long(gql):
    r = await gql(CREATE, {"input": {"username": "a" * 31, "displayName": "A",
                                     "profilePhoto": "x", "birthday": "1990-01-01"}}, user_id="uid1")
    assert r.errors is not None

async def test_create_profile_username_invalid_chars(gql):
    r = await gql(CREATE, {"input": {"username": "bad user!", "displayName": "X",
                                     "profilePhoto": "x", "birthday": "1990-01-01"}}, user_id="uid1")
    assert r.errors is not None

async def test_create_profile_birthday_too_young(gql):
    r = await gql(CREATE, {"input": {"username": "young1", "displayName": "Y",
                                     "profilePhoto": "x", "birthday": "2015-01-01"}}, user_id="uid1")
    assert r.errors is not None

async def test_create_profile_bio_too_long(gql):
    r = await gql(CREATE, {"input": {"username": "biouser", "displayName": "B",
                                     "profilePhoto": "x", "birthday": "1990-01-01",
                                     "bio": "x" * 501}}, user_id="uid1")
    assert r.errors is not None

async def test_create_profile_invalid_fitness_level(gql):
    r = await gql(CREATE, {"input": {"username": "fitbro", "displayName": "F",
                                     "profilePhoto": "x", "birthday": "1990-01-01",
                                     "fitnessLevel": "superhuman"}}, user_id="uid1")
    assert r.errors is not None

async def test_create_profile_with_location(gql):
    r = await gql(CREATE, {"input": {
        "username": "locuser",
        "displayName": "Loc",
        "profilePhoto": "x",
        "birthday": "1990-01-01",
        "location": {"coordinates": [-73.9855, 40.7484], "label": "NYC"},
    }}, user_id="uid1")
    assert r.errors is None

# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_profile_partial(gql, make_profile, mongo):
    await make_profile("uid1", "alice", {"bio": "original bio"})
    r = await gql(UPDATE, {"input": {"displayName": "Updated Alice"}}, user_id="uid1")
    assert r.errors is None
    assert r.data["updateProfile"]["displayName"] == "Updated Alice"
    # bio was UNSET — should be unchanged
    doc = await mongo.profiles.find_one({"_id": "uid1"})
    assert doc["bio"] == "original bio"

async def test_update_profile_clear_bio(gql, make_profile, mongo):
    await make_profile("uid1", "alice", {"bio": "has bio"})
    r = await gql(UPDATE, {"input": {"bio": None}}, user_id="uid1")
    assert r.errors is None
    doc = await mongo.profiles.find_one({"_id": "uid1"})
    assert doc["bio"] is None

async def test_update_profile_refreshes_cache(gql, make_profile, redis):
    await make_profile("uid1", "alice")
    await gql(UPDATE, {"input": {"displayName": "New Name"}}, user_id="uid1")
    import json
    cached = json.loads(await redis.get("profile:uid1"))
    assert cached["displayName"] == "New Name"

async def test_update_profile_no_fields_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(UPDATE, {"input": {}}, user_id="uid1")
    assert r.errors is not None

async def test_update_profile_not_found_rejected(gql):
    r = await gql(UPDATE, {"input": {"displayName": "X"}}, user_id="uid_ghost")
    assert r.errors is not None

# ── Delete ────────────────────────────────────────────────────────────────────

async def test_delete_profile_soft_deletes(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    r = await gql(DELETE, user_id="uid1")
    assert r.errors is None
    assert r.data["deleteProfile"] is True
    doc = await mongo.profiles.find_one({"_id": "uid1"})
    assert doc["isDeleted"] is True

async def test_delete_profile_tombstones_redis(gql, make_profile, redis):
    await make_profile("uid1", "alice")
    await gql(DELETE, user_id="uid1")
    assert await redis.get("profile:uid1") == "__nil__"

async def test_delete_profile_cascade_via_worker(gql, make_profile, make_post, make_comment, make_reaction, mongo, redis):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid1", pid)
    rid = await make_reaction("uid1", pid, "fire")

    # uid2 follows uid1
    await gql("mutation { followUser(userId: \"uid1\") }", user_id="uid2")

    # Delete uid1's profile then run the worker cascade
    await gql(DELETE, user_id="uid1")
    await worker_cascade_profile_deleted(mongo, redis, "uid1")

    # Post, comment, reaction, follow all soft-deleted
    from bson import ObjectId
    post_doc = await mongo.posts.find_one({"_id": ObjectId(pid)})
    assert post_doc["isDeleted"] is True

    comment_doc = await mongo.comments.find_one({"_id": ObjectId(cid)})
    assert comment_doc["isDeleted"] is True

    reaction_doc = await mongo.reactions.find_one({"_id": ObjectId(rid)})
    assert reaction_doc["isDeleted"] is True

    follow_doc = await mongo.follows.find_one({"followingUid": "uid1"})
    assert follow_doc["isDeleted"] is True

    # Redis tombstones present
    assert await redis.get(f"post:{pid}") == "__nil__"
    assert await redis.get(f"comment:{cid}") == "__nil__"

async def test_delete_profile_no_profile_returns_false(gql):
    r = await gql(DELETE, user_id="uid_nobody")
    assert r.errors is None
    assert r.data["deleteProfile"] is False

# ── Queries ───────────────────────────────────────────────────────────────────

async def test_me_query(gql, make_profile):
    await make_profile("uid1", "alice", {"bio": "test bio"})
    r = await gql(ME, user_id="uid1")
    assert r.errors is None
    assert r.data["me"]["username"] == "alice"
    assert r.data["me"]["bio"] == "test bio"

async def test_me_query_not_found(gql):
    r = await gql(ME, user_id="uid_ghost")
    assert r.errors is not None

async def test_profile_query_by_id(gql, make_profile):
    await make_profile("uid1", "alice")
    pid = r = await gql("query { me { id } }", user_id="uid1")
    profile_id = pid.data["me"]["id"]

    r2 = await gql(PROFILE_Q, {"id": profile_id}, user_id="uid2")
    assert r2.errors is None
    assert r2.data["profile"]["username"] == "alice"

async def test_profile_not_found(gql):
    r = await gql(PROFILE_Q, {"id": "uid_nobody"}, user_id="uid2")
    assert r.errors is not None

async def test_profile_posts_nested(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_post("uid1")
    await make_post("uid1")

    r = await gql("query { me { posts(limit: 10) { posts { id } nextCursor } } }", user_id="uid1")
    assert r.errors is None
    assert len(r.data["me"]["posts"]["posts"]) == 2

async def test_profile_posts_pagination(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    for _ in range(5):
        await make_post("uid1")
    # Page 1: limit 3
    r1 = await gql("query { me { posts(limit: 3) { posts { id } nextCursor } } }", user_id="uid1")
    assert r1.errors is None
    page1 = r1.data["me"]["posts"]
    assert len(page1["posts"]) == 3
    assert page1["nextCursor"] is not None

    # Page 2: use cursor from page 1
    cursor = page1["nextCursor"]
    r2 = await gql(
        "query ($c: String) { me { posts(limit: 3, cursor: $c) { posts { id } nextCursor } } }",
        {"c": cursor}, user_id="uid1",
    )
    assert r2.errors is None
    page2 = r2.data["me"]["posts"]
    assert len(page2["posts"]) == 2
    assert page2["nextCursor"] is None

async def test_profile_deleted_posts_excluded(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    from bson import ObjectId
    await mongo.posts.update_one({"_id": ObjectId(pid)}, {"$set": {"isDeleted": True}})
    r = await gql("query { me { posts(limit: 10) { posts { id } } } }", user_id="uid1")
    assert r.errors is None
    assert len(r.data["me"]["posts"]["posts"]) == 0

async def test_profile_followers_nested(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql("mutation { followUser(userId: \"uid1\") }", user_id="uid2")

    r = await gql("query { me { followers(limit: 5) { users { id username } } } }", user_id="uid1")
    assert r.errors is None
    assert any(u["username"] == "bob" for u in r.data["me"]["followers"]["users"])

async def test_profile_following_nested(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql("mutation { followUser(userId: \"uid2\") }", user_id="uid1")

    r = await gql("query { me { following(limit: 5) { users { id username } } } }", user_id="uid1")
    assert r.errors is None
    assert any(u["username"] == "bob" for u in r.data["me"]["following"]["users"])

async def test_viewer_is_following_true(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql("mutation { followUser(userId: \"uid1\") }", user_id="uid2")

    r = await gql(PROFILE_Q, {"id": "uid1"}, user_id="uid2")
    assert r.errors is None
    assert r.data["profile"]["viewerIsFollowing"] is True

async def test_viewer_is_following_false(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")

    r = await gql(PROFILE_Q, {"id": "uid1"}, user_id="uid2")
    assert r.errors is None
    assert r.data["profile"]["viewerIsFollowing"] is False

async def test_viewer_is_following_self_is_false(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(PROFILE_Q, {"id": "uid1"}, user_id="uid1")
    assert r.errors is None
    assert r.data["profile"]["viewerIsFollowing"] is False

async def test_orphaned_deleted_child_does_not_crash_profile(gql, make_profile, make_post, mongo, redis):
    """A post from a deleted author is still served (author field returns null, not a crash)."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    # Simulate uid1's profile being gone from cache/db
    await mongo.profiles.update_one({"_id": "uid1"}, {"$set": {"isDeleted": True}})
    await redis.setex("profile:uid1", 3600, "__nil__")  # invalidate stale cache

    # uid2 queries the post — author should resolve to null, not an error
    r = await gql(
        f'query {{ post(id: "{pid}") {{ id title author {{ id username }} }} }}',
        user_id="uid2",
    )
    assert r.errors is None
    assert r.data["post"]["author"] is None
