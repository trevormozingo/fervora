"""Post CRUD, pagination, and DataLoader tests."""
import pytest
from bson import ObjectId
from .conftest import worker_cascade_post_deleted


CREATE = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) { id title body createdAt }
}
"""

UPDATE = """
mutation UpdatePost($input: UpdatePostInput!) {
  updatePost(input: $input) { id title body }
}
"""

DELETE = "mutation ($id: ID!) { deletePost(id: $id) }"

POST_Q = """
query Post($id: ID!) {
  post(id: $id) {
    id title body
    author { id username }
    comments(limit: 5) { comments { id body } nextCursor }
    reactions(limit: 5) { reactions { id reactionType } nextCursor }
    reactionSummaries { reactionType count }
    viewerReaction
  }
}
"""


# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_post_title_only(gql, make_profile, redis):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "Morning Run"}}, user_id="uid1")
    assert r.errors is None
    pid = r.data["createPost"]["id"]
    # Cache populated
    cached = await redis.get(f"post:{pid}")
    assert cached is not None and cached != "__nil__"

async def test_create_post_with_workout(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {
        "title": "Leg Day",
        "workout": {
            "activityType": "weightlifting",
            "durationSeconds": 3600,
            "caloriesBurned": 400.0,
        },
    }}, user_id="uid1")
    assert r.errors is None

async def test_create_post_with_body_metrics(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {
        "title": "Weekly Check-in",
        "bodyMetrics": {"weightLbs": 175.0},
    }}, user_id="uid1")
    assert r.errors is None

async def test_create_post_with_media(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {
        "title": "Cool photo",
        "media": [{"url": "https://bucket.com/img.jpg", "mimeType": "image/jpeg"}],
    }}, user_id="uid1")
    assert r.errors is None

async def test_create_post_media_limit_exceeded(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {
        "media": [{"url": f"https://x.com/{i}.jpg", "mimeType": "image/jpeg"} for i in range(11)],
    }}, user_id="uid1")
    assert r.errors is not None
    assert "10" in r.errors[0].message

async def test_create_post_no_content_rejected(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {}}, user_id="uid1")
    assert r.errors is not None
    assert "at least one content field" in r.errors[0].message

async def test_create_post_title_too_long(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "x" * 201}}, user_id="uid1")
    assert r.errors is not None

async def test_create_post_body_too_long(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"body": "x" * 5001}}, user_id="uid1")
    assert r.errors is not None

async def test_create_post_invalid_activity_type(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"workout": {"activityType": "telekinesis"}}}, user_id="uid1")
    assert r.errors is not None

async def test_create_post_no_profile_rejected(gql):
    r = await gql(CREATE, {"input": {"title": "Should fail"}}, user_id="uid_no_profile")
    assert r.errors is not None
    assert "profile does not exist" in r.errors[0].message

async def test_create_post_idempotent_via_storage_id(gql, make_profile):
    await make_profile("uid1", "alice")
    inp = {"title": "My Post", "storagePostId": "client-uuid-123"}
    r1 = await gql(CREATE, {"input": inp}, user_id="uid1")
    r2 = await gql(CREATE, {"input": inp}, user_id="uid1")
    assert r1.errors is None
    assert r2.errors is None
    assert r1.data["createPost"]["id"] == r2.data["createPost"]["id"]

async def test_create_post_caches_in_redis(gql, make_profile, redis):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "Cache Me"}}, user_id="uid1")
    pid = r.data["createPost"]["id"]
    assert await redis.get(f"post:{pid}") is not None

# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_post_partial(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1", body="original body")
    r = await gql(UPDATE, {"input": {"id": pid, "title": "Updated Title"}}, user_id="uid1")
    assert r.errors is None
    assert r.data["updatePost"]["title"] == "Updated Title"
    doc = await mongo.posts.find_one({"_id": ObjectId(pid)})
    assert doc["body"] == "original body"

async def test_update_post_clear_workout(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1", workout={"activityType": "running"})
    r = await gql(UPDATE, {"input": {"id": pid, "workout": None}}, user_id="uid1")
    assert r.errors is None
    doc = await mongo.posts.find_one({"_id": ObjectId(pid)})
    assert doc.get("workout") is None

async def test_update_post_no_fields_rejected(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    r = await gql(UPDATE, {"input": {"id": pid}}, user_id="uid1")
    assert r.errors is not None
    assert "no valid fields" in r.errors[0].message

async def test_update_post_refreshes_cache(gql, make_profile, make_post, redis):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    await gql(UPDATE, {"input": {"id": pid, "title": "New Title"}}, user_id="uid1")
    import json
    cached = json.loads(await redis.get(f"post:{pid}"))
    assert cached["title"] == "New Title"

async def test_update_post_wrong_owner_rejected(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    r = await gql(UPDATE, {"input": {"id": pid, "title": "Hacked"}}, user_id="uid2")
    assert r.errors is not None

# ── Delete ────────────────────────────────────────────────────────────────────

async def test_delete_post_soft_deletes(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    r = await gql(DELETE, {"id": pid}, user_id="uid1")
    assert r.errors is None
    assert r.data["deletePost"] is True
    doc = await mongo.posts.find_one({"_id": ObjectId(pid)})
    assert doc["isDeleted"] is True

async def test_delete_post_tombstones_redis(gql, make_profile, make_post, redis):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1")
    await gql(DELETE, {"id": pid}, user_id="uid1")
    assert await redis.get(f"post:{pid}") == "__nil__"

async def test_delete_post_cascade_via_worker(gql, make_profile, make_post, make_comment, make_reaction, mongo, redis):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    cid = await make_comment("uid2", pid)
    rid = await make_reaction("uid2", pid)

    await gql(DELETE, {"id": pid}, user_id="uid1")
    await worker_cascade_post_deleted(mongo, redis, pid)

    assert (await mongo.comments.find_one({"_id": ObjectId(cid)}))["isDeleted"] is True
    assert (await mongo.reactions.find_one({"_id": ObjectId(rid)}))["isDeleted"] is True
    assert await redis.get(f"comment:{cid}") == "__nil__"
    assert await redis.get(f"reaction:{rid}") == "__nil__"

# ── Queries ───────────────────────────────────────────────────────────────────

async def test_post_query(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    pid = await make_post("uid1", title="Query Me")
    r = await gql(POST_Q, {"id": pid}, user_id="uid1")
    assert r.errors is None
    assert r.data["post"]["title"] == "Query Me"
    assert r.data["post"]["author"]["username"] == "alice"

async def test_post_not_found(gql):
    r = await gql(POST_Q, {"id": "000000000000000000000001"}, user_id="uid1")
    assert r.errors is not None

async def test_post_comments_page(gql, make_profile, make_post, make_comment):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    for i in range(5):
        await make_comment("uid2", pid, body=f"Comment {i}")

    r = await gql(
        """query ($id: ID!) { post(id: $id) { comments(limit: 3) { comments { id } nextCursor } } }""",
        {"id": pid}, user_id="uid1",
    )
    assert r.errors is None
    p = r.data["post"]["comments"]
    assert len(p["comments"]) == 3
    assert p["nextCursor"] is not None

async def test_post_reactions_page(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    for i in range(2, 7):
        await make_profile(f"uid{i}", f"user{i}")
    pid = await make_post("uid1")
    for i in range(2, 7):
        await gql(
            "mutation ($pid: ID!) { setReaction(input: { postId: $pid, reactionType: \"fire\" }) { id } }",
            {"pid": pid}, user_id=f"uid{i}",
        )

    r = await gql(
        """query ($id: ID!) { post(id: $id) { reactions(limit: 3) { reactions { id } nextCursor } } }""",
        {"id": pid}, user_id="uid1",
    )
    assert r.errors is None
    p = r.data["post"]["reactions"]
    assert len(p["reactions"]) == 3
    assert p["nextCursor"] is not None

async def test_post_reaction_summaries(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    for i in range(2, 5):
        await make_profile(f"uid{i}", f"user{i}")
    pid = await make_post("uid1")

    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"fire\"}){id} }", {"p": pid}, user_id="uid2")
    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"fire\"}){id} }", {"p": pid}, user_id="uid3")
    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"strong\"}){id} }", {"p": pid}, user_id="uid4")

    r = await gql(
        """query ($id: ID!) { post(id: $id) { reactionSummaries { reactionType count } } }""",
        {"id": pid}, user_id="uid1",
    )
    assert r.errors is None
    summaries = {s["reactionType"]: s["count"] for s in r.data["post"]["reactionSummaries"]}
    assert summaries["fire"] == 2
    assert summaries["strong"] == 1

async def test_post_reaction_summaries_ignore_deleted(gql, make_profile, make_post, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"fire\"}){id} }", {"p": pid}, user_id="uid2")
    await mongo.reactions.update_many({"postId": pid}, {"$set": {"isDeleted": True}})

    r = await gql(
        """query ($id: ID!) { post(id: $id) { reactionSummaries { reactionType count } } }""",
        {"id": pid}, user_id="uid1",
    )
    assert r.errors is None
    assert r.data["post"]["reactionSummaries"] == []

async def test_post_viewer_reaction(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"clap\"}){id} }", {"p": pid}, user_id="uid2")

    r = await gql(POST_Q, {"id": pid}, user_id="uid2")
    assert r.errors is None
    assert r.data["post"]["viewerReaction"] == "clap"

async def test_post_viewer_reaction_none_when_not_reacted(gql, make_profile, make_post):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")

    r = await gql(POST_Q, {"id": pid}, user_id="uid2")
    assert r.errors is None
    assert r.data["post"]["viewerReaction"] is None

async def test_dataloader_batches_reaction_summaries(gql, make_profile, make_post):
    """Two posts queried together resolve reactionSummaries in a single batch."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid1 = await make_post("uid1")
    pid2 = await make_post("uid1")
    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"fire\"}){id} }", {"p": pid1}, user_id="uid2")
    await gql("mutation ($p: ID!) { setReaction(input:{postId:$p,reactionType:\"heart\"}){id} }", {"p": pid2}, user_id="uid2")

    r = await gql(f"""
        query {{
          p1: post(id: "{pid1}") {{ reactionSummaries {{ reactionType count }} }}
          p2: post(id: "{pid2}") {{ reactionSummaries {{ reactionType count }} }}
        }}
    """, user_id="uid1")
    assert r.errors is None
    assert r.data["p1"]["reactionSummaries"][0]["reactionType"] == "fire"
    assert r.data["p2"]["reactionSummaries"][0]["reactionType"] == "heart"
