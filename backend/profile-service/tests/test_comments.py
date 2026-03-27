"""Comment CRUD and query tests."""
import pytest
from bson import ObjectId

CREATE = """
mutation CreateComment($input: CreateCommentInput!) {
  createComment(input: $input) { id body }
}
"""
DELETE = "mutation ($id: ID!) { deleteComment(id: $id) }"
COMMENT_Q = "query ($id: ID!) { comment(id: $id) { id body author { id username } } }"


async def test_create_comment_success(gql, make_profile, make_post, redis):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    r = await gql(CREATE, {"input": {"postId": pid, "body": "Great workout!"}}, user_id="uid2")
    assert r.errors is None
    cid = r.data["createComment"]["id"]
    cached = await redis.get(f"comment:{cid}")
    assert cached is not None and cached != "__nil__"

async def test_create_comment_empty_body_rejected(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(CREATE, {"input": {"postId": pid, "body": ""}}, user_id="uid2")
    assert r.errors is not None

async def test_create_comment_body_too_long(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(CREATE, {"input": {"postId": pid, "body": "x" * 1001}}, user_id="uid2")
    assert r.errors is not None

async def test_create_comment_on_missing_post_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"postId": "000000000000000000000001", "body": "hi"}}, user_id="uid1")
    assert r.errors is not None
    assert "does not exist or was deleted" in r.errors[0].message

async def test_create_comment_on_deleted_post_rejected(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    await mongo.posts.update_one({"_id": ObjectId(pid)}, {"$set": {"isDeleted": True}})

    r = await gql(CREATE, {"input": {"postId": pid, "body": "Late comment"}}, user_id="uid2")
    assert r.errors is not None
    assert "does not exist or was deleted" in r.errors[0].message

async def test_create_comment_no_profile_rejected(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    r = await gql(CREATE, {"input": {"postId": pid, "body": "Who am I?"}}, user_id="uid_ghost")
    assert r.errors is not None
    assert "profile does not exist" in r.errors[0].message

async def test_delete_comment_success(gql, make_profile, make_post, make_comment):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)

    r = await gql(DELETE, {"id": cid}, user_id="uid2")
    assert r.errors is None
    assert r.data["deleteComment"] is True

async def test_delete_comment_soft_deletes_in_mongo(gql, make_profile, make_post, make_comment, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)
    await gql(DELETE, {"id": cid}, user_id="uid2")
    doc = await mongo.comments.find_one({"_id": ObjectId(cid)})
    assert doc["isDeleted"] is True

async def test_delete_comment_tombstones_redis(gql, make_profile, make_post, make_comment, redis):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)
    await gql(DELETE, {"id": cid}, user_id="uid2")
    assert await redis.get(f"comment:{cid}") == "__nil__"

async def test_delete_comment_wrong_owner(gql, make_profile, make_post, make_comment):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)
    r = await gql(DELETE, {"id": cid}, user_id="uid1")
    assert r.errors is None
    assert r.data["deleteComment"] is False

async def test_delete_comment_already_deleted(gql, make_profile, make_post, make_comment):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)
    await gql(DELETE, {"id": cid}, user_id="uid2")
    r = await gql(DELETE, {"id": cid}, user_id="uid2")
    assert r.errors is None
    assert r.data["deleteComment"] is False

async def test_comment_query_author_resolves(gql, make_profile, make_post, make_comment):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)

    r = await gql(COMMENT_Q, {"id": cid}, user_id="uid1")
    assert r.errors is None
    assert r.data["comment"]["author"]["username"] == "bob"

async def test_comment_author_deleted_returns_null_not_crash(gql, make_profile, make_post, make_comment, mongo, redis):
    """Comment is still served even after the author's profile is deleted."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)

    await mongo.profiles.update_one({"_id": "uid2"}, {"$set": {"isDeleted": True}})
    await redis.setex("profile:uid2", 3600, "__nil__")  # invalidate stale cache

    r = await gql(COMMENT_Q, {"id": cid}, user_id="uid1")
    assert r.errors is None
    assert r.data["comment"]["body"] is not None
    assert r.data["comment"]["author"] is None
