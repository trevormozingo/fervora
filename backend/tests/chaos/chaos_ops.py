"""
Phase 2 — Chaos operations and stress patterns.

Randomly fires API requests for CHAOS_DURATION_SECONDS, then runs
orchestrated stress patterns that target specific race conditions.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta

from .client import ApiClient
from .config import (
    CHAOS_DURATION_SECONDS,
    NUM_CONCURRENT_REQUESTS,
    OP_WEIGHTS,
    REACTION_TYPES,
    PATTERN_A_FOLLOWERS,
    PATTERN_B_FOLLOWERS,
    PATTERN_B_UNFOLLOWERS,
    PATTERN_C_TOGGLES,
    PATTERN_D_USERS,
    PATTERN_E_REACTORS,
    PATTERN_F_COMMENTERS,
    PATTERN_H_DELETIONS,
)
from .state import ChaosState

log = logging.getLogger("chaos.ops")

_counter = 0


def _next_uid() -> str:
    global _counter
    _counter += 1
    return f"chaos_new_{_counter:06d}"


def _next_username() -> str:
    return f"chaosuser_{_counter:06d}"


# ── Individual chaos operations ───────────────────────────────────────

async def op_create_profile(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = _next_uid()
    r = await api.create_profile(uid, _next_username())
    if r.status_code == 201:
        state.add_user(uid)
    state.record("create_profile", uid, ok=r.status_code == 201, status_code=r.status_code)


async def op_delete_profile(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    r = await api.delete_profile(uid)
    if r.status_code == 204:
        state.remove_user(uid)
    state.record("delete_profile", uid, ok=r.status_code == 204, status_code=r.status_code)


async def op_follow(api: ApiClient, state: ChaosState, rng: random.Random):
    users = state.random_active_users(rng, 2)
    if len(users) < 2:
        return
    follower, followed = users[0], users[1]
    r = await api.follow(follower, followed)
    if r.status_code == 201:
        state.add_follow(follower, followed)
    state.record("follow", follower, ok=r.status_code in (201, 409), status_code=r.status_code,
                 followed=followed)


async def op_unfollow(api: ApiClient, state: ChaosState, rng: random.Random):
    pair = state.random_followed_pair(rng)
    if not pair:
        return
    follower, followed = pair
    r = await api.unfollow(follower, followed)
    if r.status_code == 204:
        state.remove_follow(follower, followed)
    state.record("unfollow", follower, ok=r.status_code in (204, 404),
                 status_code=r.status_code, followed=followed)


async def op_refollow(api: ApiClient, state: ChaosState, rng: random.Random):
    pair = state.random_unfollowed_pair(rng)
    if not pair:
        return
    follower, followed = pair
    r = await api.follow(follower, followed)
    if r.status_code == 201:
        state.add_follow(follower, followed)
    state.record("refollow", follower, ok=r.status_code in (201, 409),
                 status_code=r.status_code, followed=followed)


async def op_create_post(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    r = await api.create_post(uid, f"Chaos post at {time.time():.0f}")
    if r.status_code == 201:
        state.add_post(uid, r.json()["id"])
    state.record("create_post", uid, ok=r.status_code == 201, status_code=r.status_code)


async def op_delete_post(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    pid = state.random_post(rng, author=uid)
    if not pid:
        return
    r = await api.delete_post(uid, pid)
    if r.status_code == 204:
        state.remove_post(pid)
    state.record("delete_post", uid, ok=r.status_code in (204, 404),
                 status_code=r.status_code, post_id=pid)


async def op_add_comment(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    pid = state.random_post(rng)
    if not pid:
        return
    r = await api.create_comment(uid, pid, f"Chaos comment {time.time():.0f}")
    if r.status_code == 201:
        state.add_comment(pid, r.json()["id"], uid)
    state.record("add_comment", uid, ok=r.status_code in (201, 404),
                 status_code=r.status_code, post_id=pid)


async def op_delete_comment(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    item = state.random_comment(rng, author=uid)
    if not item:
        return
    post_id, comment_id, _ = item
    r = await api.delete_comment(uid, post_id, comment_id)
    if r.status_code == 204:
        state.remove_comment(comment_id)
    state.record("delete_comment", uid, ok=r.status_code in (204, 404),
                 status_code=r.status_code, comment_id=comment_id)


async def op_add_reaction(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    pid = state.random_post(rng)
    if not pid:
        return
    rtype = rng.choice(REACTION_TYPES)
    r = await api.set_reaction(uid, pid, rtype)
    if r.status_code == 200:
        state.set_reaction(pid, uid, rtype)
    state.record("add_reaction", uid, ok=r.status_code in (200, 404),
                 status_code=r.status_code, post_id=pid, type=rtype)


async def op_change_reaction(api: ApiClient, state: ChaosState, rng: random.Random):
    item = state.random_reacted_post(rng)
    if not item:
        return
    pid, uid = item
    new_type = rng.choice(REACTION_TYPES)
    r = await api.set_reaction(uid, pid, new_type)
    if r.status_code == 200:
        state.set_reaction(pid, uid, new_type)
    state.record("change_reaction", uid, ok=r.status_code in (200, 404),
                 status_code=r.status_code, post_id=pid, type=new_type)


async def op_remove_reaction(api: ApiClient, state: ChaosState, rng: random.Random):
    item = state.random_reacted_post(rng)
    if not item:
        return
    pid, uid = item
    r = await api.remove_reaction(uid, pid)
    if r.status_code == 204:
        state.clear_reaction(pid, uid)
    state.record("remove_reaction", uid, ok=r.status_code in (204, 404),
                 status_code=r.status_code, post_id=pid)


async def op_rereact(api: ApiClient, state: ChaosState, rng: random.Random):
    item = state.random_unreacted_post(rng)
    if not item:
        return
    pid, uid = item
    rtype = rng.choice(REACTION_TYPES)
    r = await api.set_reaction(uid, pid, rtype)
    if r.status_code == 200:
        state.set_reaction(pid, uid, rtype)
    state.record("rereact", uid, ok=r.status_code in (200, 404),
                 status_code=r.status_code, post_id=pid, type=rtype)


async def op_create_event(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    start = (datetime.now(timezone.utc) + timedelta(days=rng.randint(1, 30))).isoformat()
    invitees = state.random_active_users(rng, 3)
    invitees = [i for i in invitees if i != uid]
    r = await api.create_event(uid, f"Chaos event {time.time():.0f}", start, invitees or None)
    if r.status_code == 201:
        state.add_event(uid, r.json()["id"])
    state.record("create_event", uid, ok=r.status_code == 201, status_code=r.status_code)


async def op_delete_event(api: ApiClient, state: ChaosState, rng: random.Random):
    item = state.random_event(rng)
    if not item:
        return
    eid, uid = item
    r = await api.delete_event(uid, eid)
    if r.status_code == 204:
        state.remove_event(eid)
    state.record("delete_event", uid, ok=r.status_code in (204, 404),
                 status_code=r.status_code, event_id=eid)


# ── Compound race-condition operations ────────────────────────────────

async def op_rapid_follow_unfollow(api: ApiClient, state: ChaosState, rng: random.Random):
    users = state.random_active_users(rng, 2)
    if len(users) < 2:
        return
    a, b = users[0], users[1]
    r1 = await api.follow(a, b)
    r2 = await api.unfollow(a, b)
    # Final state: unfollowed
    if r1.status_code == 201 and r2.status_code == 204:
        state.remove_follow(a, b)
    elif r1.status_code == 201:
        state.add_follow(a, b)
    state.record("rapid_follow_unfollow", a, status_code=r2.status_code, followed=b)


async def op_rapid_post_create_delete(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    r1 = await api.create_post(uid, "Ephemeral post")
    if r1.status_code != 201:
        return
    pid = r1.json()["id"]
    state.add_post(uid, pid)
    r2 = await api.delete_post(uid, pid)
    if r2.status_code == 204:
        state.remove_post(pid)
    state.record("rapid_post_create_delete", uid, status_code=r2.status_code, post_id=pid)


async def op_follow_deleted_user(api: ApiClient, state: ChaosState, rng: random.Random):
    users = state.random_active_users(rng, 3)
    if len(users) < 3:
        return
    follower, target = users[0], users[1]
    # Fire follow and delete concurrently
    r_follow, r_delete = await asyncio.gather(
        api.follow(follower, target),
        api.delete_profile(target),
    )
    if r_delete.status_code == 204:
        state.remove_user(target)
    if r_follow.status_code == 201 and r_delete.status_code != 204:
        state.add_follow(follower, target)
    state.record("follow_deleted_user", follower, status_code=r_follow.status_code, target=target)


async def op_post_by_deleted_user(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    r_post, r_delete = await asyncio.gather(
        api.create_post(uid, "Post during deletion"),
        api.delete_profile(uid),
    )
    if r_delete.status_code == 204:
        state.remove_user(uid)
    if r_post.status_code == 201:
        state.add_post(uid, r_post.json()["id"])
    state.record("post_by_deleted_user", uid, status_code=r_post.status_code)


async def op_comment_on_deleted_post(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    item = state.random_post_with_author(rng)
    if not item:
        return
    pid, author = item
    r_comment, r_delete = await asyncio.gather(
        api.create_comment(uid, pid, "Comment during deletion"),
        api.delete_post(author, pid),
    )
    if r_delete.status_code == 204:
        state.remove_post(pid)
    if r_comment.status_code == 201:
        state.add_comment(pid, r_comment.json()["id"], uid)
    state.record("comment_on_deleted_post", uid, status_code=r_comment.status_code, post_id=pid)


async def op_react_on_deleted_post(api: ApiClient, state: ChaosState, rng: random.Random):
    uid = state.random_active_user(rng)
    if not uid:
        return
    item = state.random_post_with_author(rng)
    if not item:
        return
    pid, author = item
    rtype = rng.choice(REACTION_TYPES)
    r_react, r_delete = await asyncio.gather(
        api.set_reaction(uid, pid, rtype),
        api.delete_post(author, pid),
    )
    if r_delete.status_code == 204:
        state.remove_post(pid)
    if r_react.status_code == 200:
        state.set_reaction(pid, uid, rtype)
    state.record("react_on_deleted_post", uid, status_code=r_react.status_code, post_id=pid)


# ── Operation dispatch table ─────────────────────────────────────────

_OPS = {
    "create_profile": op_create_profile,
    "delete_profile": op_delete_profile,
    "follow": op_follow,
    "unfollow": op_unfollow,
    "refollow": op_refollow,
    "create_post": op_create_post,
    "delete_post": op_delete_post,
    "add_comment": op_add_comment,
    "delete_comment": op_delete_comment,
    "add_reaction": op_add_reaction,
    "change_reaction": op_change_reaction,
    "remove_reaction": op_remove_reaction,
    "rereact": op_rereact,
    "create_event": op_create_event,
    "delete_event": op_delete_event,
    "rapid_follow_unfollow": op_rapid_follow_unfollow,
    "rapid_post_create_delete": op_rapid_post_create_delete,
    "follow_deleted_user": op_follow_deleted_user,
    "post_by_deleted_user": op_post_by_deleted_user,
    "comment_on_deleted_post": op_comment_on_deleted_post,
    "react_on_deleted_post": op_react_on_deleted_post,
}


# ── Stress patterns ──────────────────────────────────────────────────

async def pattern_a_follow_storm(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern A: many users follow User X while X deletes their profile."""
    target = state.random_active_user(rng)
    if not target:
        return
    followers = state.random_active_users(rng, PATTERN_A_FOLLOWERS)
    followers = [f for f in followers if f != target]
    if not followers:
        return
    log.info("Pattern A: %d users follow %s while %s deletes", len(followers), target, target)

    async def _follow(f):
        r = await api.follow(f, target)
        if r.status_code == 201:
            state.add_follow(f, target)

    coros = [_follow(f) for f in followers] + [api.delete_profile(target)]
    results = await asyncio.gather(*coros, return_exceptions=True)
    # Check if delete succeeded (last coroutine)
    delete_result = results[-1]
    if not isinstance(delete_result, Exception) and delete_result.status_code == 204:
        state.remove_user(target)
    state.record("pattern_a", target, status_code=0)


async def pattern_b_post_fanout_race(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern B: User X posts, some followers unfollow concurrently."""
    author = state.random_active_user(rng)
    if not author:
        return
    # Get users who follow author
    followers_of_author = []
    for uid, following_set in list(state.following.items()):
        if author in following_set and uid in state.active_users:
            followers_of_author.append(uid)
    if len(followers_of_author) < 5:
        return
    unfollowers = rng.sample(followers_of_author, min(PATTERN_B_UNFOLLOWERS, len(followers_of_author)))
    log.info("Pattern B: %s posts while %d unfollow", author, len(unfollowers))

    async def _unfollow(f):
        r = await api.unfollow(f, author)
        if r.status_code == 204:
            state.remove_follow(f, author)

    coros = [api.create_post(author, "Pattern B post")] + [_unfollow(f) for f in unfollowers]
    results = await asyncio.gather(*coros, return_exceptions=True)
    post_result = results[0]
    if not isinstance(post_result, Exception) and post_result.status_code == 201:
        state.add_post(author, post_result.json()["id"])
    state.record("pattern_b", author, status_code=0)


async def pattern_c_rapid_toggle(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern C: rapid follow/unfollow toggling."""
    users = state.random_active_users(rng, 2)
    if len(users) < 2:
        return
    a, b = users[0], users[1]
    log.info("Pattern C: %s toggles follow on %s × %d", a, b, PATTERN_C_TOGGLES)
    for _ in range(PATTERN_C_TOGGLES):
        r = await api.follow(a, b)
        if r.status_code == 201:
            state.add_follow(a, b)
        r = await api.unfollow(a, b)
        if r.status_code == 204:
            state.remove_follow(a, b)
    # End with a follow
    r = await api.follow(a, b)
    if r.status_code == 201:
        state.add_follow(a, b)
    state.record("pattern_c", a, status_code=0, target=b)


async def pattern_d_cascade_collision(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern D: multiple users who follow each other delete simultaneously."""
    users = state.random_active_users(rng, PATTERN_D_USERS)
    if len(users) < 2:
        return
    log.info("Pattern D: %d users delete simultaneously", len(users))

    async def _delete(uid):
        r = await api.delete_profile(uid)
        if r.status_code == 204:
            state.remove_user(uid)

    await asyncio.gather(*[_delete(u) for u in users])
    state.record("pattern_d", users[0], status_code=0)


async def pattern_e_reaction_storm(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern E: many users react, change, remove reactions on same post."""
    pid = state.random_post(rng)
    if not pid:
        return
    reactors = state.random_active_users(rng, PATTERN_E_REACTORS)
    if not reactors:
        return
    log.info("Pattern E: %d users react to %s", len(reactors), pid)

    async def _react(uid):
        rtype = rng.choice(REACTION_TYPES)
        r = await api.set_reaction(uid, pid, rtype)
        if r.status_code == 200:
            state.set_reaction(pid, uid, rtype)

    async def _change(uid):
        new_type = rng.choice(REACTION_TYPES)
        r = await api.set_reaction(uid, pid, new_type)
        if r.status_code == 200:
            state.set_reaction(pid, uid, new_type)

    async def _remove(uid):
        r = await api.remove_reaction(uid, pid)
        if r.status_code == 204:
            state.clear_reaction(pid, uid)

    # Phase 1: all react
    await asyncio.gather(*[_react(u) for u in reactors])
    # Phase 2: half change, quarter remove
    changers = reactors[:len(reactors) // 2]
    removers = reactors[:len(reactors) // 4]
    await asyncio.gather(
        *[_change(u) for u in changers],
        *[_remove(u) for u in removers],
    )
    state.record("pattern_e", reactors[0], status_code=0, post_id=pid)


async def pattern_f_comment_on_vanishing_post(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern F: comments while post is being deleted."""
    uid = state.random_active_user(rng)
    if not uid:
        return
    pid = state.random_post(rng, author=uid)
    if not pid:
        return
    commenters = state.random_active_users(rng, PATTERN_F_COMMENTERS)
    log.info("Pattern F: %d comment on %s while %s deletes it", len(commenters), pid, uid)

    async def _comment(c_uid):
        r = await api.create_comment(c_uid, pid, "Comment on vanishing post")
        if r.status_code == 201:
            state.add_comment(pid, r.json()["id"], c_uid)

    coros = [_comment(c) for c in commenters] + [api.delete_post(uid, pid)]
    results = await asyncio.gather(*coros, return_exceptions=True)
    delete_result = results[-1]
    if not isinstance(delete_result, Exception) and delete_result.status_code == 204:
        state.remove_post(pid)
    state.record("pattern_f", uid, status_code=0, post_id=pid)


async def pattern_h_mass_deletion(api: ApiClient, state: ChaosState, rng: random.Random):
    """Pattern H: many users delete profiles simultaneously."""
    users = state.random_active_users(rng, PATTERN_H_DELETIONS)
    if len(users) < 2:
        return
    log.info("Pattern H: %d users delete simultaneously", len(users))

    async def _delete(uid):
        r = await api.delete_profile(uid)
        if r.status_code == 204:
            state.remove_user(uid)

    await asyncio.gather(*[_delete(u) for u in users])
    state.record("pattern_h", users[0], status_code=0)


# ── Main chaos loop ──────────────────────────────────────────────────

async def run_chaos(api: ApiClient, state: ChaosState) -> None:
    """Run random operations for CHAOS_DURATION_SECONDS, then stress patterns."""
    rng = random.Random(99)

    # Build weighted operation list
    op_names = []
    for name, weight in OP_WEIGHTS.items():
        op_names.extend([name] * weight)

    sem = asyncio.Semaphore(NUM_CONCURRENT_REQUESTS)
    ops_completed = 0
    errors = 0

    async def _run_one():
        nonlocal ops_completed, errors
        op_name = rng.choice(op_names)
        fn = _OPS[op_name]
        async with sem:
            try:
                await fn(api, state, rng)
                ops_completed += 1
            except Exception as e:
                errors += 1
                log.debug("Op %s failed: %s", op_name, e)

    # ── Random chaos loop ─────────────────────────────────────────────
    log.info("Starting chaos loop for %d seconds …", CHAOS_DURATION_SECONDS)
    deadline = time.monotonic() + CHAOS_DURATION_SECONDS
    tasks: list[asyncio.Task] = []

    while time.monotonic() < deadline:
        # Launch a burst of tasks
        for _ in range(NUM_CONCURRENT_REQUESTS):
            if time.monotonic() >= deadline:
                break
            tasks.append(asyncio.create_task(_run_one()))
        # Let some complete before launching more
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=1.0)
            tasks = list(pending)

    # Wait for remaining tasks
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    log.info("Chaos loop done: %d ops, %d errors", ops_completed, errors)

    # ── Stress patterns ───────────────────────────────────────────────
    log.info("Running stress patterns …")
    patterns = [
        pattern_a_follow_storm,
        pattern_b_post_fanout_race,
        pattern_c_rapid_toggle,
        pattern_d_cascade_collision,
        pattern_e_reaction_storm,
        pattern_f_comment_on_vanishing_post,
        pattern_h_mass_deletion,
    ]
    for pat in patterns:
        try:
            await pat(api, state, rng)
        except Exception as e:
            log.error("Pattern %s failed: %s", pat.__name__, e)

    log.info("All stress patterns complete")
    log.info("Total ops logged: %d", len(state.log))
