"""
Phase 1 — Seed deterministic starting state.

Creates users, posts, follows, comments, reactions, and events
via the live API, then waits for workers to drain.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta

from .client import ApiClient
from .config import (
    NUM_USERS,
    NUM_POSTS_PER_USER,
    FOLLOWS_PER_USER,
    COMMENTS_PER_USER,
    REACTIONS_PER_USER,
    EVENTS_PER_USER_FRAC,
    NUM_CONCURRENT_REQUESTS,
    REACTION_TYPES,
)
from .state import ChaosState

log = logging.getLogger("chaos.seed")


def _uid(i: int) -> str:
    return f"chaos_{i:05d}"


async def _batch(coros, concurrency: int):
    """Run coroutines in batches of *concurrency*."""
    sem = asyncio.Semaphore(concurrency)

    async def _wrap(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*[_wrap(c) for c in coros], return_exceptions=True)


async def seed(api: ApiClient, state: ChaosState) -> None:
    """Create all seed data and populate state tracker."""
    rng = random.Random(42)  # deterministic seed

    # ── 1. Create profiles ────────────────────────────────────────────
    log.info("Creating %d profiles …", NUM_USERS)

    async def _create_profile(i: int):
        uid = _uid(i)
        r = await api.create_profile(uid, f"user_{i:05d}")
        if r.status_code == 201:
            state.add_user(uid)
            state.record("create_profile", uid, status_code=201)
        else:
            log.warning("Profile create failed for %s: %d %s", uid, r.status_code, r.text)
            state.record("create_profile", uid, ok=False, status_code=r.status_code)

    await _batch([_create_profile(i) for i in range(NUM_USERS)], NUM_CONCURRENT_REQUESTS)
    log.info("Created %d profiles", len(state.active_users))

    # ── 2. Create posts ───────────────────────────────────────────────
    log.info("Creating %d posts per user …", NUM_POSTS_PER_USER)

    async def _create_post(uid: str, j: int):
        r = await api.create_post(uid, f"Post {j} by {uid}")
        if r.status_code == 201:
            post_id = r.json()["id"]
            state.add_post(uid, post_id)
            state.record("create_post", uid, status_code=201, post_id=post_id)
        else:
            state.record("create_post", uid, ok=False, status_code=r.status_code)

    post_coros = [
        _create_post(uid, j)
        for uid in list(state.active_users)
        for j in range(NUM_POSTS_PER_USER)
    ]
    await _batch(post_coros, NUM_CONCURRENT_REQUESTS)
    total_posts = sum(len(p) for p in state.posts_by_user.values())
    log.info("Created %d posts", total_posts)

    # ── 3. Create follows ─────────────────────────────────────────────
    log.info("Creating ~%d follows per user …", FOLLOWS_PER_USER)
    users = list(state.active_users)

    async def _create_follow(follower: str, followed: str):
        r = await api.follow(follower, followed)
        if r.status_code == 201:
            state.add_follow(follower, followed)
            state.record("follow", follower, status_code=201, followed=followed)
        elif r.status_code == 409:
            pass  # already following, fine
        else:
            state.record("follow", follower, ok=False, status_code=r.status_code)

    follow_coros = []
    for u in users:
        targets = rng.sample([x for x in users if x != u], min(FOLLOWS_PER_USER, len(users) - 1))
        for t in targets:
            follow_coros.append(_create_follow(u, t))
    await _batch(follow_coros, NUM_CONCURRENT_REQUESTS)
    total_follows = sum(len(f) for f in state.following.values())
    log.info("Created %d follows", total_follows)

    # ── 4. Create comments ────────────────────────────────────────────
    log.info("Creating ~%d comments per user …", COMMENTS_PER_USER)

    async def _create_comment(uid: str, post_id: str):
        r = await api.create_comment(uid, post_id, f"Comment by {uid}")
        if r.status_code == 201:
            cid = r.json()["id"]
            state.add_comment(post_id, cid, uid)
            state.record("add_comment", uid, status_code=201, post_id=post_id, comment_id=cid)
        else:
            state.record("add_comment", uid, ok=False, status_code=r.status_code)

    comment_coros = []
    for u in users:
        for _ in range(COMMENTS_PER_USER):
            pid = state.random_post(rng)
            if pid:
                comment_coros.append(_create_comment(u, pid))
    await _batch(comment_coros, NUM_CONCURRENT_REQUESTS)
    total_comments = sum(len(c) for c in state.comments_by_post.values())
    log.info("Created %d comments", total_comments)

    # ── 5. Create reactions ───────────────────────────────────────────
    log.info("Creating ~%d reactions per user …", REACTIONS_PER_USER)

    async def _create_reaction(uid: str, post_id: str, rtype: str):
        r = await api.set_reaction(uid, post_id, rtype)
        if r.status_code == 200:
            state.set_reaction(post_id, uid, rtype)
            state.record("add_reaction", uid, status_code=200, post_id=post_id, type=rtype)
        else:
            state.record("add_reaction", uid, ok=False, status_code=r.status_code)

    reaction_coros = []
    for u in users:
        for _ in range(REACTIONS_PER_USER):
            pid = state.random_post(rng)
            if pid:
                reaction_coros.append(_create_reaction(u, pid, rng.choice(REACTION_TYPES)))
    await _batch(reaction_coros, NUM_CONCURRENT_REQUESTS)
    log.info("Created %d reactions", len([v for v in state.reactions.values() if v]))

    # ── 6. Create events ──────────────────────────────────────────────
    event_users = rng.sample(users, int(len(users) * EVENTS_PER_USER_FRAC))
    log.info("Creating events for %d users …", len(event_users))

    async def _create_event(uid: str):
        start = (datetime.now(timezone.utc) + timedelta(days=rng.randint(1, 30))).isoformat()
        invitees = rng.sample([x for x in users if x != uid], min(3, len(users) - 1))
        r = await api.create_event(uid, f"Event by {uid}", start, invitees)
        if r.status_code == 201:
            eid = r.json()["id"]
            state.add_event(uid, eid)
            state.record("create_event", uid, status_code=201, event_id=eid)
        else:
            state.record("create_event", uid, ok=False, status_code=r.status_code)

    await _batch([_create_event(u) for u in event_users], NUM_CONCURRENT_REQUESTS)
    total_events = sum(len(e) for e in state.events_by_user.values())
    log.info("Created %d events", total_events)

    log.info("Seed complete: %d users, %d posts, %d follows, %d comments, %d reactions, %d events",
             len(state.active_users), total_posts, total_follows, total_comments,
             len([v for v in state.reactions.values() if v]), total_events)
