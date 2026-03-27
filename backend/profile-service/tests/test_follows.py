"""Follow/Unfollow tests and viewer_is_following field."""
import pytest

FOLLOW = "mutation ($uid: String!) { followUser(userId: $uid) }"
UNFOLLOW = "mutation ($uid: String!) { unfollowUser(userId: $uid) }"


async def test_follow_user_success(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    r = await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")
    assert r.errors is None
    assert r.data["followUser"] is True
    doc = await mongo.follows.find_one({"followerUid": "uid1", "followingUid": "uid2"})
    assert doc is not None
    assert doc["isDeleted"] is False

async def test_follow_upsert_refollow(gql, make_profile, mongo):
    """Un-following and re-following does not create duplicate documents."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")
    await gql(UNFOLLOW, {"uid": "uid2"}, user_id="uid1")
    await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")

    count = await mongo.follows.count_documents({"followerUid": "uid1", "followingUid": "uid2"})
    assert count == 1
    doc = await mongo.follows.find_one({"followerUid": "uid1", "followingUid": "uid2"})
    assert doc["isDeleted"] is False

async def test_follow_self_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(FOLLOW, {"uid": "uid1"}, user_id="uid1")
    assert r.errors is not None
    assert "yourself" in r.errors[0].message

async def test_follow_nonexistent_user_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(FOLLOW, {"uid": "uid_ghost"}, user_id="uid1")
    assert r.errors is not None
    assert "not found" in r.errors[0].message

async def test_follow_deleted_user_rejected(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await mongo.profiles.update_one({"_id": "uid2"}, {"$set": {"isDeleted": True}})
    r = await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")
    assert r.errors is not None

async def test_unfollow_user_success(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")
    r = await gql(UNFOLLOW, {"uid": "uid2"}, user_id="uid1")
    assert r.errors is None
    assert r.data["unfollowUser"] is True
    doc = await mongo.follows.find_one({"followerUid": "uid1", "followingUid": "uid2"})
    assert doc["isDeleted"] is True

async def test_unfollow_not_following_returns_false(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    r = await gql(UNFOLLOW, {"uid": "uid2"}, user_id="uid1")
    assert r.errors is None
    assert r.data["unfollowUser"] is False

async def test_viewer_is_following_true(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")

    r = await gql(
        "query ($id: ID!) { profile(id: $id) { viewerIsFollowing } }",
        {"id": "uid2"}, user_id="uid1",
    )
    assert r.errors is None
    assert r.data["profile"]["viewerIsFollowing"] is True

async def test_viewer_is_following_false_after_unfollow(gql, make_profile):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await gql(FOLLOW, {"uid": "uid2"}, user_id="uid1")
    await gql(UNFOLLOW, {"uid": "uid2"}, user_id="uid1")

    r = await gql(
        "query ($id: ID!) { profile(id: $id) { viewerIsFollowing } }",
        {"id": "uid2"}, user_id="uid1",
    )
    assert r.errors is None
    assert r.data["profile"]["viewerIsFollowing"] is False
