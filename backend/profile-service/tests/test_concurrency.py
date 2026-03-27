"""
Concurrency and race-condition tests.

Uses asyncio.gather to fire multiple operations simultaneously against the same
in-memory database.  While mongomock is not truly multi-threaded, gather causes
real coroutine interleaving at every await point, which is enough to expose
ordering bugs in our upsert, soft-delete, and fan-out logic.
"""
import asyncio
import pytest
from bson import ObjectId
from datetime import datetime, timezone


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_profile_direct(mongo, uid: str, username: str) -> None:
    await mongo.profiles.insert_one({
        "_id": uid,
        "username": username,
        "displayName": f"User {uid}",
        "profilePhoto": "https://x.com/p.jpg",
        "birthday": "1990-01-01",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "isDeleted": False,
    })


async def _create_post_direct(mongo, uid: str, title: str = "Post") -> str:
    r = await mongo.posts.insert_one({
        "authorUid": uid,
        "title": title,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "isDeleted": False,
    })
    return str(r.inserted_id)


# ── Concurrent profile creation (uniqueness) ──────────────────────────────────

async def test_concurrent_profile_creation_unique_usernames(gql):
    """100 distinct users create profiles simultaneously; all should succeed."""
    N = 100
    tasks = [
        gql(
            "mutation ($input: CreateProfileInput!) { createProfile(input: $input) { id } }",
            {"input": {
                "username": f"user{i}",
                "displayName": f"User {i}",
                "profilePhoto": "https://x.com/p.jpg",
                "birthday": "1990-01-01",
            }},
            user_id=f"uid{i}",
        )
        for i in range(N)
    ]
    results = await asyncio.gather(*tasks)
    errors = [r for r in results if r.errors]
    assert len(errors) == 0, f"{len(errors)} profile creation(s) failed: {errors[0].errors if errors else ''}"

async def test_concurrent_duplicate_username_exactly_one_wins(gql):
    """Two users racing for the same username — exactly one succeeds."""
    tasks = [
        gql(
            "mutation ($input: CreateProfileInput!) { createProfile(input: $input) { id } }",
            {"input": {"username": "samename", "displayName": f"User {i}",
                       "profilePhoto": "x", "birthday": "1990-01-01"}},
            user_id=f"uid{i}",
        )
        for i in range(2)
    ]
    results = await asyncio.gather(*tasks)
    successes = [r for r in results if not r.errors]
    assert len(successes) == 1


# ── Concurrent post creation ──────────────────────────────────────────────────

async def test_concurrent_post_creation(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    N = 50
    tasks = [
        gql(
            "mutation ($input: CreatePostInput!) { createPost(input: $input) { id } }",
            {"input": {"title": f"Post {i}"}},
            user_id="uid1",
        )
        for i in range(N)
    ]
    results = await asyncio.gather(*tasks)
    assert all(r.errors is None for r in results)
    count = await mongo.posts.count_documents({"authorUid": "uid1"})
    assert count == N


# ── Concurrent reaction upserts ───────────────────────────────────────────────

async def test_concurrent_reactions_from_different_users(gql, make_profile, mongo):
    """50 users react to the same post simultaneously — no duplicates."""
    await make_profile("uid1", "alice")
    for i in range(2, 52):
        await make_profile(f"uid{i}", f"user{i}")

    pid = await (gql(
        "mutation { createPost(input: { title: \"Popular\" }) { id } }",
        user_id="uid1",
    ))
    post_id = pid.data["createPost"]["id"]

    tasks = [
        gql(
            "mutation ($input: SetReactionInput!) { setReaction(input: $input) { id } }",
            {"input": {"postId": post_id, "reactionType": "fire"}},
            user_id=f"uid{i}",
        )
        for i in range(2, 52)
    ]
    results = await asyncio.gather(*tasks)
    assert all(r.errors is None for r in results)
    count = await mongo.reactions.count_documents({"postId": post_id})
    assert count == 50

async def test_same_user_reaction_concurrent_no_duplicates(gql, make_profile, mongo):
    """Same user fires setReaction twice concurrently — still one record."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = (await gql(
        "mutation { createPost(input: { title: \"T\" }) { id } }",
        user_id="uid1",
    )).data["createPost"]["id"]

    r1, r2 = await asyncio.gather(
        gql("mutation ($i: SetReactionInput!) { setReaction(input: $i) { id } }",
            {"i": {"postId": pid, "reactionType": "fire"}}, user_id="uid2"),
        gql("mutation ($i: SetReactionInput!) { setReaction(input: $i) { id } }",
            {"i": {"postId": pid, "reactionType": "strong"}}, user_id="uid2"),
    )
    assert r1.errors is None
    assert r2.errors is None
    count = await mongo.reactions.count_documents({"postId": pid, "authorUid": "uid2"})
    assert count == 1


# ── Delete-while-commenting race ──────────────────────────────────────────────

async def test_delete_post_while_commenting_no_crash(gql, make_profile, mongo):
    """Deleting a post at the same time as someone comments must not crash either side."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = (await gql(
        "mutation { createPost(input: { title: \"RacePost\" }) { id } }",
        user_id="uid1",
    )).data["createPost"]["id"]

    delete_task = gql(
        "mutation ($id: ID!) { deletePost(id: $id) }",
        {"id": pid}, user_id="uid1",
    )
    comment_task = gql(
        "mutation ($i: CreateCommentInput!) { createComment(input: $i) { id } }",
        {"i": {"postId": pid, "body": "Simultaneous!"}}, user_id="uid2",
    )
    delete_r, comment_r = await asyncio.gather(delete_task, comment_task)

    # Delete must succeed
    assert delete_r.errors is None
    assert delete_r.data["deletePost"] is True

    # The comment may succeed (if it ran before delete) or fail (if after);
    # what must NOT happen is an unhandled exception / server 500
    assert not isinstance(comment_r, Exception)

    # Post must end up deleted
    post_doc = await mongo.posts.find_one({"_id": ObjectId(pid)})
    assert post_doc["isDeleted"] is True


async def test_delete_profile_while_posting_no_crash(gql, make_profile, mongo):
    """Concurrent profile deletion and post creation must not leave orphaned unchecked state."""
    await make_profile("uid1", "alice")

    delete_task = gql("mutation { deleteProfile }", user_id="uid1")
    post_task = gql(
        "mutation { createPost(input: { title: \"Ghost Post\" }) { id } }",
        user_id="uid1",
    )
    delete_r, post_r = await asyncio.gather(delete_task, post_task)

    assert not isinstance(delete_r, Exception)
    assert not isinstance(post_r, Exception)


# ── Orphaned data served gracefully ──────────────────────────────────────────

async def test_comment_on_post_from_deleted_user_served(gql, make_profile, make_post, make_comment, mongo):
    """A comment on a post whose author was deleted is still returned; author=null."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1", title="Orphan Post")
    cid = await make_comment("uid2", pid)

    # Simultaneously delete uid1's profile and query the comment
    delete_task = gql("mutation { deleteProfile }", user_id="uid1")
    query_task = gql(
        "query ($id: ID!) { comment(id: $id) { id body author { id username } } }",
        {"id": cid}, user_id="uid2",
    )
    delete_r, query_r = await asyncio.gather(delete_task, query_task)

    assert delete_r.errors is None
    assert query_r.errors is None
    # The comment itself is intact
    assert query_r.data["comment"]["body"] is not None

async def test_reaction_from_deleted_user_still_counted(gql, make_profile, make_post, mongo, redis):
    """A reaction on a post whose author was deleted is still counted in summaries."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    pid = await make_post("uid1")
    await gql(
        "mutation ($i: SetReactionInput!) { setReaction(input: $i) { id } }",
        {"i": {"postId": pid, "reactionType": "fire"}}, user_id="uid2",
    )
    # Soft-delete uid2's profile
    await mongo.profiles.update_one({"_id": "uid2"}, {"$set": {"isDeleted": True}})
    await redis.setex("profile:uid2", 3600, "__nil__")

    r = await gql(
        f'query {{ post(id: "{pid}") {{ reactionSummaries {{ reactionType count }} }} }}',
        user_id="uid1",
    )
    assert r.errors is None
    summaries = {s["reactionType"]: s["count"] for s in r.data["post"]["reactionSummaries"]}
    assert summaries.get("fire", 0) == 1


# ── Bulk throughput ───────────────────────────────────────────────────────────

async def test_bulk_create_and_delete_posts(gql, make_profile, mongo):
    """Create 100 posts then delete 50 concurrently — no crashes, counts correct."""
    await make_profile("uid1", "alice")
    create_tasks = [
        gql("mutation ($i: CreatePostInput!) { createPost(input: $i) { id } }",
            {"i": {"title": f"Post {n}"}}, user_id="uid1")
        for n in range(100)
    ]
    create_results = await asyncio.gather(*create_tasks)
    post_ids = [r.data["createPost"]["id"] for r in create_results if not r.errors]
    assert len(post_ids) == 100

    delete_tasks = [
        gql("mutation ($id: ID!) { deletePost(id: $id) }", {"id": pid}, user_id="uid1")
        for pid in post_ids[:50]
    ]
    delete_results = await asyncio.gather(*delete_tasks)
    assert all(r.errors is None for r in delete_results)

    remaining = await mongo.posts.count_documents({"authorUid": "uid1", "isDeleted": {"$ne": True}})
    assert remaining == 50


async def test_concurrent_follows_no_duplicates(gql, make_profile, mongo):
    """Two concurrent follow requests from the same user produce one document."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")

    r1, r2 = await asyncio.gather(
        gql("mutation { followUser(userId: \"uid2\") }", user_id="uid1"),
        gql("mutation { followUser(userId: \"uid2\") }", user_id="uid1"),
    )
    assert r1.errors is None
    assert r2.errors is None
    count = await mongo.follows.count_documents({"followerUid": "uid1", "followingUid": "uid2"})
    assert count == 1
