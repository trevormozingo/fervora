"""
Shared mutable state tracker for the chaos test.

Every API operation records its result here so that:
  - chaos ops can pick random existing entities to act on
  - validation can check final state against the operation log
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class OpRecord:
    """A single logged operation."""
    ts: str
    op: str
    uid: str
    detail: dict = field(default_factory=dict)
    ok: bool = True
    status_code: int = 0


class ChaosState:
    """Thread-safe (and asyncio-safe via locks) state tracker."""

    def __init__(self):
        self._lock = threading.Lock()

        # Active entity registries
        self.active_users: set[str] = set()
        self.deleted_users: set[str] = set()

        # uid -> list[post_id]
        self.posts_by_user: dict[str, list[str]] = {}
        self.deleted_posts: set[str] = set()

        # uid -> set[target_uid]   (active follows only)
        self.following: dict[str, set[str]] = {}
        self.unfollowed_pairs: set[tuple[str, str]] = set()

        # post_id -> list[{comment_id, author_uid}]
        self.comments_by_post: dict[str, list[dict]] = {}
        self.deleted_comments: set[str] = set()

        # (post_id, author_uid) -> reaction_type | None
        self.reactions: dict[tuple[str, str], str | None] = {}

        # uid -> list[event_id]
        self.events_by_user: dict[str, list[str]] = {}
        self.deleted_events: set[str] = set()

        # Full operation log
        self.log: list[OpRecord] = []

    # ── Helpers ───────────────────────────────────────────────────────

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def record(self, op: str, uid: str, ok: bool = True, status_code: int = 0, **detail):
        with self._lock:
            self.log.append(OpRecord(
                ts=self._now(), op=op, uid=uid, detail=detail,
                ok=ok, status_code=status_code,
            ))

    # ── User management ───────────────────────────────────────────────

    def add_user(self, uid: str):
        with self._lock:
            self.active_users.add(uid)
            self.posts_by_user.setdefault(uid, [])
            self.following.setdefault(uid, set())
            self.events_by_user.setdefault(uid, [])

    def remove_user(self, uid: str):
        with self._lock:
            self.active_users.discard(uid)
            self.deleted_users.add(uid)

    # ── Post management ───────────────────────────────────────────────

    def add_post(self, uid: str, post_id: str):
        with self._lock:
            self.posts_by_user.setdefault(uid, []).append(post_id)

    def remove_post(self, post_id: str):
        with self._lock:
            self.deleted_posts.add(post_id)

    # ── Follow management ─────────────────────────────────────────────

    def add_follow(self, follower: str, followed: str):
        with self._lock:
            self.following.setdefault(follower, set()).add(followed)
            self.unfollowed_pairs.discard((follower, followed))

    def remove_follow(self, follower: str, followed: str):
        with self._lock:
            s = self.following.get(follower)
            if s:
                s.discard(followed)
            self.unfollowed_pairs.add((follower, followed))

    # ── Comment management ────────────────────────────────────────────

    def add_comment(self, post_id: str, comment_id: str, author_uid: str):
        with self._lock:
            self.comments_by_post.setdefault(post_id, []).append(
                {"comment_id": comment_id, "author_uid": author_uid}
            )

    def remove_comment(self, comment_id: str):
        with self._lock:
            self.deleted_comments.add(comment_id)

    # ── Reaction management ───────────────────────────────────────────

    def set_reaction(self, post_id: str, author_uid: str, reaction_type: str):
        with self._lock:
            self.reactions[(post_id, author_uid)] = reaction_type

    def clear_reaction(self, post_id: str, author_uid: str):
        with self._lock:
            self.reactions[(post_id, author_uid)] = None

    # ── Event management ──────────────────────────────────────────────

    def add_event(self, uid: str, event_id: str):
        with self._lock:
            self.events_by_user.setdefault(uid, []).append(event_id)

    def remove_event(self, event_id: str):
        with self._lock:
            self.deleted_events.add(event_id)

    # ── Random selectors ──────────────────────────────────────────────

    def random_active_user(self, rng) -> str | None:
        with self._lock:
            users = list(self.active_users)
        return rng.choice(users) if users else None

    def random_active_users(self, rng, n: int) -> list[str]:
        with self._lock:
            users = list(self.active_users)
        if len(users) <= n:
            return users
        return rng.sample(users, n)

    def random_post(self, rng, author: str | None = None) -> str | None:
        with self._lock:
            if author:
                posts = [p for p in self.posts_by_user.get(author, []) if p not in self.deleted_posts]
            else:
                posts = [
                    p for uid in self.active_users
                    for p in self.posts_by_user.get(uid, [])
                    if p not in self.deleted_posts
                ]
        return rng.choice(posts) if posts else None

    def random_post_with_author(self, rng) -> tuple[str, str] | None:
        with self._lock:
            pairs = [
                (p, uid)
                for uid in self.active_users
                for p in self.posts_by_user.get(uid, [])
                if p not in self.deleted_posts
            ]
        return rng.choice(pairs) if pairs else None

    def random_followed_pair(self, rng) -> tuple[str, str] | None:
        """Return (follower, followed) for an active follow."""
        with self._lock:
            pairs = [
                (f, t)
                for f in self.active_users
                for t in self.following.get(f, set())
                if t in self.active_users
            ]
        return rng.choice(pairs) if pairs else None

    def random_unfollowed_pair(self, rng) -> tuple[str, str] | None:
        with self._lock:
            pairs = [
                (f, t)
                for f, t in self.unfollowed_pairs
                if f in self.active_users and t in self.active_users
            ]
        return rng.choice(pairs) if pairs else None

    def random_comment(self, rng, author: str | None = None) -> tuple[str, str, str] | None:
        """Return (post_id, comment_id, author_uid) or None."""
        with self._lock:
            items = []
            for post_id, comments in self.comments_by_post.items():
                for c in comments:
                    if c["comment_id"] not in self.deleted_comments:
                        if author is None or c["author_uid"] == author:
                            items.append((post_id, c["comment_id"], c["author_uid"]))
        return rng.choice(items) if items else None

    def random_reacted_post(self, rng) -> tuple[str, str] | None:
        """(post_id, author_uid) for an active reaction."""
        with self._lock:
            items = [(pid, uid) for (pid, uid), rt in self.reactions.items() if rt is not None]
        return rng.choice(items) if items else None

    def random_unreacted_post(self, rng) -> tuple[str, str] | None:
        """(post_id, author_uid) for a removed reaction."""
        with self._lock:
            items = [(pid, uid) for (pid, uid), rt in self.reactions.items() if rt is None]
        return rng.choice(items) if items else None

    def random_event(self, rng, author: str | None = None) -> tuple[str, str] | None:
        """Return (event_id, author_uid) or None."""
        with self._lock:
            items = []
            for uid, events in self.events_by_user.items():
                if uid in self.active_users and (author is None or uid == author):
                    for eid in events:
                        if eid not in self.deleted_events:
                            items.append((eid, uid))
        return rng.choice(items) if items else None
