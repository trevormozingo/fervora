"""Reaction upsert, delete, and summary tests."""
import pytest
from bson import ObjectId

SET = "mutation ($input: SetReactionInput!) { setReaction(input: $input) { id reactionType } }"
DELETE = "mutation ($pid: ID!) { deleteReaction(postId: $pid) }"


async def test_set_reaction_success(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    r = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    assert r.errors is None
    assert r.data["setReaction"]["reactionType"] == "fire"

async def test_set_reaction_caches_in_redis(gql, make_profile, make_post, redis):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    rid = r.data["setReaction"]["id"]
    assert await redis.get(f"reaction:{rid}") is not None

async def test_set_reaction_upsert_changes_type(gql, make_profile, make_post, mongo):
    """Changing reaction type updates the existing record, not a new one."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    r1 = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    r2 = await gql(SET, {"input": {"postId": pid, "reactionType": "strong"}}, user_id="uid2")

    assert r1.data["setReaction"]["id"] == r2.data["setReaction"]["id"]
    assert r2.data["setReaction"]["reactionType"] == "strong"

    count = await mongo.reactions.count_documents({"postId": pid, "authorUid": "uid2"})
    assert count == 1

async def test_set_reaction_upsert_restores_deleted(gql, make_profile, make_post, mongo):
    """Re-reacting after a delete restores the reaction (isDeleted=False)."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    await gql(DELETE, {"pid": pid}, user_id="uid2")
    await gql(SET, {"input": {"postId": pid, "reactionType": "clap"}}, user_id="uid2")

    doc = await mongo.reactions.find_one({"postId": pid, "authorUid": "uid2"})
    assert doc["isDeleted"] is False
    assert doc["reactionType"] == "clap"

async def test_set_reaction_on_deleted_post_rejected(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    await mongo.posts.update_one({"_id": ObjectId(pid)}, {"$set": {"isDeleted": True}})

    r = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    assert r.errors is not None
    assert "does not exist or was deleted" in r.errors[0].message

async def test_set_reaction_no_profile_rejected(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    r = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid_ghost")
    assert r.errors is not None

async def test_set_reaction_invalid_type_rejected(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(SET, {"input": {"postId": pid, "reactionType": "meh"}}, user_id="uid2")
    assert r.errors is not None

async def test_delete_reaction_success(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")

    r = await gql(DELETE, {"pid": pid}, user_id="uid2")
    assert r.errors is None
    assert r.data["deleteReaction"] is True

async def test_delete_reaction_soft_deletes_in_mongo(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    rid = r.data["setReaction"]["id"]
    await gql(DELETE, {"pid": pid}, user_id="uid2")
    doc = await mongo.reactions.find_one({"_id": ObjectId(rid)})
    assert doc["isDeleted"] is True

async def test_delete_reaction_tombstones_redis(gql, make_profile, make_post, redis):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(SET, {"input": {"postId": pid, "reactionType": "fire"}}, user_id="uid2")
    rid = r.data["setReaction"]["id"]
    await gql(DELETE, {"pid": pid}, user_id="uid2")
    assert await redis.get(f"reaction:{rid}") == "__nil__"

async def test_delete_reaction_no_reaction_returns_false(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(DELETE, {"pid": pid}, user_id="uid2")
    assert r.errors is None
    assert r.data["deleteReaction"] is False
