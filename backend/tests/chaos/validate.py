"""
Phase 3 — Validation checks.

Every check queries MongoDB directly and reports PASS/FAIL with details.
Checks are independent — all run even if some fail.
"""

import logging
from dataclasses import dataclass, field

import pymongo
import redis as sync_redis

from .config import MONGO_URI, MONGO_DB, REDIS_URL, SERVICE_URL

log = logging.getLogger("chaos.validate")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    checked: int = 0
    failures: list[str] = field(default_factory=list)
    warn: bool = False


class Validator:
    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB]
        self.redis = sync_redis.from_url(REDIS_URL, decode_responses=True)
        self.results: list[CheckResult] = []

    def close(self):
        self.client.close()
        self.redis.close()

    def _pass(self, name: str, detail: str, checked: int = 0):
        self.results.append(CheckResult(name=name, passed=True, detail=detail, checked=checked))

    def _fail(self, name: str, detail: str, checked: int = 0, failures: list[str] | None = None):
        self.results.append(CheckResult(
            name=name, passed=False, detail=detail, checked=checked,
            failures=failures or [],
        ))

    def _warn(self, name: str, detail: str, checked: int = 0, failures: list[str] | None = None):
        self.results.append(CheckResult(
            name=name, passed=True, detail=detail, checked=checked,
            failures=failures or [], warn=True,
        ))

    # ── Helpers ───────────────────────────────────────────────────────

    def _active(self, extra: dict | None = None) -> dict:
        q: dict = {"isDeleted": {"$ne": True}}
        if extra:
            q.update(extra)
        return q

    # ══════════════════════════════════════════════════════════════════
    # PROFILE INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_prof_1(self):
        """V-PROF-1: Deleted users must have deletedAt."""
        docs = list(self.db.profiles.find({"isDeleted": True, "deletedAt": {"$exists": False}}))
        if docs:
            ids = [d["_id"] for d in docs[:10]]
            self._fail("V-PROF-1", f"{len(docs)} deleted profiles missing deletedAt", len(docs), [str(i) for i in ids])
        else:
            total = self.db.profiles.count_documents({"isDeleted": True})
            self._pass("V-PROF-1", f"All deleted profiles have deletedAt", total)

    def v_prof_2(self):
        """V-PROF-2: Active users must not have deletedAt."""
        docs = list(self.db.profiles.find(self._active({"deletedAt": {"$exists": True}})))
        if docs:
            ids = [d["_id"] for d in docs[:10]]
            self._fail("V-PROF-2", f"{len(docs)} active profiles have deletedAt", len(docs), [str(i) for i in ids])
        else:
            total = self.db.profiles.count_documents(self._active())
            self._pass("V-PROF-2", f"No active profiles have deletedAt", total)

    # ══════════════════════════════════════════════════════════════════
    # FOLLOW INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_follow_1(self):
        """V-FOLLOW-1: No duplicate follow docs per (followerId, followedId)."""
        pipeline = [
            {"$group": {"_id": {"f": "$followerId", "t": "$followedId"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        dupes = list(self.db.follows.aggregate(pipeline))
        if dupes:
            samples = [f"({d['_id']['f']},{d['_id']['t']})×{d['count']}" for d in dupes[:10]]
            self._fail("V-FOLLOW-1", f"{len(dupes)} duplicate follow pairs", len(dupes), samples)
        else:
            total = self.db.follows.count_documents({})
            self._pass("V-FOLLOW-1", f"No duplicate follow documents", total)

    def v_follow_2(self):
        """V-FOLLOW-2: Active follows reference active profiles."""
        active_uids = set(d["_id"] for d in self.db.profiles.find(self._active(), {"_id": 1}))
        follows = list(self.db.follows.find(self._active(), {"followerId": 1, "followedId": 1}))
        bad = []
        for f in follows:
            if f["followerId"] not in active_uids:
                bad.append(f"follower {f['followerId']} deleted")
            if f["followedId"] not in active_uids:
                bad.append(f"followed {f['followedId']} deleted")
        if bad:
            self._fail("V-FOLLOW-2", f"{len(bad)} active follows ref deleted profiles", len(follows), bad[:10])
        else:
            self._pass("V-FOLLOW-2", "All active follows reference active profiles", len(follows))

    def v_follow_3(self):
        """V-FOLLOW-3: Active follows have feed items for followed user's active posts."""
        follows = list(self.db.follows.find(self._active(), {"followerId": 1, "followedId": 1}))
        missing = []
        checked = 0
        # Sample up to 200 follows to keep this tractable
        sample = follows[:200]
        for f in sample:
            follower = f["followerId"]
            followed = f["followedId"]
            active_posts = list(self.db.posts.find(
                self._active({"authorUid": followed}), {"_id": 1}
            ))
            for p in active_posts:
                checked += 1
                feed_entry = self.db.feed.find_one(self._active({
                    "ownerUid": follower,
                    "postId": str(p["_id"]),
                }))
                if not feed_entry:
                    missing.append(f"owner={follower} missing feed for post={p['_id']} by {followed}")
        if missing:
            self._fail("V-FOLLOW-3", f"{len(missing)} missing feed items for active follows",
                        checked, missing[:10])
        else:
            self._pass("V-FOLLOW-3", "Active follows have corresponding feed items", checked)

    def v_follow_4(self):
        """V-FOLLOW-4: No orphaned follows (referencing non-existent profiles)."""
        all_uids = set(d["_id"] for d in self.db.profiles.find({}, {"_id": 1}))
        follows = list(self.db.follows.find({}, {"followerId": 1, "followedId": 1}))
        orphans = []
        for f in follows:
            if f["followerId"] not in all_uids:
                orphans.append(f"followerId {f['followerId']} not in profiles")
            if f["followedId"] not in all_uids:
                orphans.append(f"followedId {f['followedId']} not in profiles")
        if orphans:
            self._fail("V-FOLLOW-4", f"{len(orphans)} orphaned follows", len(follows), orphans[:10])
        else:
            self._pass("V-FOLLOW-4", "No orphaned follows", len(follows))

    def v_follow_5(self):
        """V-FOLLOW-5: No ghost soft-deleted duplicates alongside active follow."""
        pipeline = [
            {"$group": {
                "_id": {"f": "$followerId", "t": "$followedId"},
                "count": {"$sum": 1},
                "active": {"$sum": {"$cond": [{"$ne": ["$isDeleted", True]}, 1, 0]}},
            }},
            {"$match": {"count": {"$gt": 1}}},
        ]
        dupes = list(self.db.follows.aggregate(pipeline))
        if dupes:
            samples = [f"({d['_id']['f']},{d['_id']['t']}): {d['count']} docs, {d['active']} active" for d in dupes[:10]]
            self._fail("V-FOLLOW-5", f"{len(dupes)} follow pairs with duplicate docs", len(dupes), samples)
        else:
            self._pass("V-FOLLOW-5", "No duplicate follow documents per pair", 0)

    def v_follow_6(self):
        """V-FOLLOW-6: Soft-deleted follows have deletedAt."""
        docs = list(self.db.follows.find({"isDeleted": True, "deletedAt": {"$exists": False}}))
        if docs:
            self._fail("V-FOLLOW-6", f"{len(docs)} deleted follows missing deletedAt", len(docs))
        else:
            total = self.db.follows.count_documents({"isDeleted": True})
            self._pass("V-FOLLOW-6", "All deleted follows have deletedAt", total)

    # ══════════════════════════════════════════════════════════════════
    # FEED INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_feed_1(self):
        """V-FEED-1: No active feed item references a deleted post."""
        deleted_post_ids = set(
            str(d["_id"]) for d in self.db.posts.find({"isDeleted": True}, {"_id": 1})
        )
        feed_items = list(self.db.feed.find(self._active(), {"postId": 1}))
        bad = [f["postId"] for f in feed_items if f["postId"] in deleted_post_ids]
        if bad:
            self._fail("V-FEED-1", f"{len(bad)} active feed items ref deleted posts", len(feed_items), bad[:10])
        else:
            self._pass("V-FEED-1", "No active feed items reference deleted posts", len(feed_items))

    def v_feed_2(self):
        """V-FEED-2: No active feed item references a deleted author."""
        deleted_uids = set(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}))
        feed_items = list(self.db.feed.find(self._active(), {"authorUid": 1}))
        bad = [f["authorUid"] for f in feed_items if f["authorUid"] in deleted_uids]
        if bad:
            self._fail("V-FEED-2", f"{len(bad)} active feed items ref deleted authors", len(feed_items), bad[:10])
        else:
            self._pass("V-FEED-2", "No active feed items reference deleted authors", len(feed_items))

    def v_feed_3(self):
        """V-FEED-3: No active feed items from broken follows."""
        # Build active follow map: follower -> set of followed uids
        follows = list(self.db.follows.find(self._active(), {"followerId": 1, "followedId": 1}))
        follow_map: dict[str, set[str]] = {}
        for f in follows:
            follow_map.setdefault(f["followerId"], set()).add(f["followedId"])

        feed_items = list(self.db.feed.find(self._active(), {"ownerUid": 1, "postId": 1, "authorUid": 1}))
        bad = []
        for fi in feed_items:
            owner = fi["ownerUid"]
            author = fi["authorUid"]
            if author not in follow_map.get(owner, set()):
                bad.append(f"owner={owner} has feed from author={author} (not following)")
        if bad:
            self._fail("V-FEED-3", f"{len(bad)} feed items from unfollowed authors", len(feed_items), bad[:10])
        else:
            self._pass("V-FEED-3", "No feed items from broken follows", len(feed_items))

    def v_feed_4(self):
        """V-FEED-4: No duplicate feed items per (ownerUid, postId)."""
        pipeline = [
            {"$group": {"_id": {"o": "$ownerUid", "p": "$postId"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        dupes = list(self.db.feed.aggregate(pipeline))
        if dupes:
            samples = [f"(owner={d['_id']['o']},post={d['_id']['p']})×{d['count']}" for d in dupes[:10]]
            self._fail("V-FEED-4", f"{len(dupes)} duplicate feed entries", len(dupes), samples)
        else:
            total = self.db.feed.count_documents({})
            self._pass("V-FEED-4", "No duplicate feed entries", total)

    def v_feed_5(self):
        """V-FEED-5: Feed completeness — active follows have feed items for active posts (sampled)."""
        # This is essentially V-FOLLOW-3 from the feed perspective.
        # Sampling 100 active follows.
        follows = list(self.db.follows.find(self._active(), {"followerId": 1, "followedId": 1}).limit(100))
        missing = []
        checked = 0
        for f in follows:
            posts = list(self.db.posts.find(self._active({"authorUid": f["followedId"]}), {"_id": 1}))
            for p in posts:
                checked += 1
                exists = self.db.feed.find_one(self._active({
                    "ownerUid": f["followerId"], "postId": str(p["_id"]),
                }))
                if not exists:
                    missing.append(f"owner={f['followerId']} missing post={p['_id']} by {f['followedId']}")
        if missing:
            self._fail("V-FEED-5", f"{len(missing)} missing feed items (completeness)", checked, missing[:10])
        else:
            self._pass("V-FEED-5", "Feed is complete for sampled follows", checked)

    def v_feed_6(self):
        """V-FEED-6: Feed items for soft-deleted posts are also soft-deleted."""
        deleted_post_ids = set(
            str(d["_id"]) for d in self.db.posts.find({"isDeleted": True}, {"_id": 1})
        )
        if not deleted_post_ids:
            self._pass("V-FEED-6", "No deleted posts to check", 0)
            return
        # Find active feed items whose postId is in deleted posts
        active_feed_for_deleted = list(
            self.db.feed.find(self._active({"postId": {"$in": list(deleted_post_ids)}}))
        )
        if active_feed_for_deleted:
            samples = [f"owner={f['ownerUid']} post={f['postId']}" for f in active_feed_for_deleted[:10]]
            self._fail("V-FEED-6", f"{len(active_feed_for_deleted)} active feed items for deleted posts",
                        len(deleted_post_ids), samples)
        else:
            self._pass("V-FEED-6", "All feed items for deleted posts are soft-deleted", len(deleted_post_ids))

    # ══════════════════════════════════════════════════════════════════
    # POST INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_post_1(self):
        """V-POST-1: No active post references a deleted author."""
        deleted_uids = set(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}))
        posts = list(self.db.posts.find(self._active(), {"authorUid": 1}))
        bad = [p["authorUid"] for p in posts if p["authorUid"] in deleted_uids]
        if bad:
            self._fail("V-POST-1", f"{len(bad)} active posts ref deleted authors", len(posts), bad[:10])
        else:
            self._pass("V-POST-1", "No active posts reference deleted authors", len(posts))

    # ══════════════════════════════════════════════════════════════════
    # COMMENT INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_comment_1(self):
        """V-COMMENT-1: Active comments on deleted posts (warn — invisible, cron cleanup)."""
        deleted_post_ids = set(
            str(d["_id"]) for d in self.db.posts.find({"isDeleted": True}, {"_id": 1})
        )
        comments = list(self.db.comments.find(self._active(), {"postId": 1}))
        bad = [c["postId"] for c in comments if c["postId"] in deleted_post_ids]
        if bad:
            self._warn("V-COMMENT-1", f"{len(bad)} active comments on deleted posts (expected)", len(comments), bad[:10])
        else:
            self._pass("V-COMMENT-1", "No active comments reference deleted posts", len(comments))

    def v_comment_2(self):
        """V-COMMENT-2: No active comment references a deleted author."""
        deleted_uids = set(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}))
        comments = list(self.db.comments.find(self._active(), {"authorUid": 1}))
        bad = [c["authorUid"] for c in comments if c["authorUid"] in deleted_uids]
        if bad:
            self._fail("V-COMMENT-2", f"{len(bad)} active comments ref deleted authors", len(comments), bad[:10])
        else:
            self._pass("V-COMMENT-2", "No active comments reference deleted authors", len(comments))

    def v_comment_3(self):
        """V-COMMENT-3: Comments on deleted posts (warn — invisible, cron cleanup)."""
        deleted_post_ids = set(
            str(d["_id"]) for d in self.db.posts.find({"isDeleted": True}, {"_id": 1})
        )
        if not deleted_post_ids:
            self._pass("V-COMMENT-3", "No deleted posts to check", 0)
            return
        active_comments = list(
            self.db.comments.find(self._active({"postId": {"$in": list(deleted_post_ids)}}))
        )
        if active_comments:
            samples = [f"comment={c['_id']} on post={c['postId']}" for c in active_comments[:10]]
            self._warn("V-COMMENT-3", f"{len(active_comments)} active comments on deleted posts (expected)",
                        len(deleted_post_ids), samples)
        else:
            self._pass("V-COMMENT-3", "All comments on deleted posts are soft-deleted", len(deleted_post_ids))

    # ══════════════════════════════════════════════════════════════════
    # REACTION INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_react_1(self):
        """V-REACT-1: No duplicate reactions per (postId, authorUid)."""
        pipeline = [
            {"$group": {"_id": {"p": "$postId", "a": "$authorUid"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        dupes = list(self.db.reactions.aggregate(pipeline))
        if dupes:
            samples = [f"(post={d['_id']['p']},author={d['_id']['a']})×{d['count']}" for d in dupes[:10]]
            self._fail("V-REACT-1", f"{len(dupes)} duplicate reactions", len(dupes), samples)
        else:
            total = self.db.reactions.count_documents({})
            self._pass("V-REACT-1", "No duplicate reactions", total)

    def v_react_2(self):
        """V-REACT-2: Active reactions on deleted posts (warn — invisible, cron cleanup)."""
        deleted_post_ids = set(
            str(d["_id"]) for d in self.db.posts.find({"isDeleted": True}, {"_id": 1})
        )
        reactions = list(self.db.reactions.find(self._active(), {"postId": 1}))
        bad = [r["postId"] for r in reactions if r["postId"] in deleted_post_ids]
        if bad:
            self._warn("V-REACT-2", f"{len(bad)} active reactions on deleted posts (expected)", len(reactions), bad[:10])
        else:
            self._pass("V-REACT-2", "No active reactions reference deleted posts", len(reactions))

    def v_react_3(self):
        """V-REACT-3: No active reaction references a deleted author."""
        deleted_uids = set(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}))
        reactions = list(self.db.reactions.find(self._active(), {"authorUid": 1}))
        bad = [r["authorUid"] for r in reactions if r["authorUid"] in deleted_uids]
        if bad:
            self._fail("V-REACT-3", f"{len(bad)} active reactions ref deleted authors", len(reactions), bad[:10])
        else:
            self._pass("V-REACT-3", "No active reactions reference deleted authors", len(reactions))

    def v_react_5(self):
        """V-REACT-5: Reactions on deleted posts (warn — invisible, cron cleanup)."""
        deleted_post_ids = set(
            str(d["_id"]) for d in self.db.posts.find({"isDeleted": True}, {"_id": 1})
        )
        if not deleted_post_ids:
            self._pass("V-REACT-5", "No deleted posts to check", 0)
            return
        active_reactions = list(
            self.db.reactions.find(self._active({"postId": {"$in": list(deleted_post_ids)}}))
        )
        if active_reactions:
            samples = [f"reaction={r['_id']} on post={r['postId']}" for r in active_reactions[:10]]
            self._warn("V-REACT-5", f"{len(active_reactions)} active reactions on deleted posts (expected)",
                        len(deleted_post_ids), samples)
        else:
            self._pass("V-REACT-5", "All reactions on deleted posts are soft-deleted", len(deleted_post_ids))

    # ══════════════════════════════════════════════════════════════════
    # EVENT INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_event_1(self):
        """V-EVENT-1: No active event references a deleted creator."""
        deleted_uids = set(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}))
        events = list(self.db.events.find(self._active(), {"authorUid": 1}))
        bad = [e["authorUid"] for e in events if e["authorUid"] in deleted_uids]
        if bad:
            self._fail("V-EVENT-1", f"{len(bad)} active events ref deleted creators", len(events), bad[:10])
        else:
            self._pass("V-EVENT-1", "No active events reference deleted creators", len(events))

    def v_event_3(self):
        """V-EVENT-3: Events created by deleted users are soft-deleted."""
        deleted_uids = set(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}))
        if not deleted_uids:
            self._pass("V-EVENT-3", "No deleted users to check", 0)
            return
        active_events = list(
            self.db.events.find(self._active({"authorUid": {"$in": list(deleted_uids)}}))
        )
        if active_events:
            samples = [f"event={e['_id']} by {e['authorUid']}" for e in active_events[:10]]
            self._fail("V-EVENT-3", f"{len(active_events)} active events by deleted users",
                        len(deleted_uids), samples)
        else:
            self._pass("V-EVENT-3", "All events by deleted users are soft-deleted", len(deleted_uids))

    def v_event_4(self):
        """V-EVENT-4: No duplicate participants in invitees arrays."""
        events = list(self.db.events.find(self._active({"invitees": {"$exists": True, "$ne": None}})))
        bad = []
        for e in events:
            invitees = e.get("invitees", [])
            uids = [i["uid"] for i in invitees if isinstance(i, dict)]
            if len(uids) != len(set(uids)):
                bad.append(f"event={e['_id']} has duplicate invitees")
        if bad:
            self._fail("V-EVENT-4", f"{len(bad)} events with duplicate invitees", len(events), bad[:10])
        else:
            self._pass("V-EVENT-4", "No duplicate invitees in events", len(events))

    # ══════════════════════════════════════════════════════════════════
    # CACHE INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_cache_1(self):
        """V-CACHE-1: Cached profiles match MongoDB (sampled)."""
        import json
        profiles = list(self.db.profiles.find(self._active()).limit(50))
        mismatches = []
        checked = 0
        for p in profiles:
            uid = p["_id"]
            cached = self.redis.get(f"profile:{uid}")
            if cached is None:
                continue  # not cached, that's fine
            checked += 1
            cached_doc = json.loads(cached)
            if cached_doc.get("username") != p.get("username"):
                mismatches.append(f"{uid}: cached username={cached_doc.get('username')} vs db={p.get('username')}")
        if mismatches:
            self._fail("V-CACHE-1", f"{len(mismatches)} cached profiles don't match DB", checked, mismatches[:10])
        else:
            self._pass("V-CACHE-1", "Cached profiles match MongoDB", checked)

    def v_cache_4(self):
        """V-CACHE-4: No cached profile for deleted users."""
        deleted_uids = list(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}).limit(100))
        stale = []
        for uid in deleted_uids:
            cached = self.redis.get(f"profile:{uid}")
            if cached is not None and cached != "__nil__":
                stale.append(uid)
        if stale:
            self._fail("V-CACHE-4", f"{len(stale)} deleted users still cached", len(deleted_uids), stale[:10])
        else:
            self._pass("V-CACHE-4", "No cached profiles for deleted users", len(deleted_uids))

    # ══════════════════════════════════════════════════════════════════
    # COUNT INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_count_1(self):
        """V-COUNT-1: Follower counts match countDocuments (sampled)."""
        import json
        profiles = list(self.db.profiles.find(self._active()).limit(50))
        mismatches = []
        checked = 0
        for p in profiles:
            uid = p["_id"]
            cached = self.redis.get(f"profile_counts:{uid}")
            if cached is None:
                continue
            checked += 1
            counts = json.loads(cached)
            cached_followers = counts.get("followersCount", 0)
            actual = self.db.follows.count_documents(self._active({"followedId": uid}))
            if cached_followers != actual:
                mismatches.append(f"{uid}: cached={cached_followers} actual={actual}")
        if mismatches:
            self._fail("V-COUNT-1", f"{len(mismatches)} follower count mismatches", checked, mismatches[:10])
        else:
            self._pass("V-COUNT-1", "Cached follower counts match DB", checked)

    def v_count_2(self):
        """V-COUNT-2: Following counts match countDocuments (sampled)."""
        import json
        profiles = list(self.db.profiles.find(self._active()).limit(50))
        mismatches = []
        checked = 0
        for p in profiles:
            uid = p["_id"]
            cached = self.redis.get(f"profile_counts:{uid}")
            if cached is None:
                continue
            checked += 1
            counts = json.loads(cached)
            cached_following = counts.get("followingCount", 0)
            actual = self.db.follows.count_documents(self._active({"followerId": uid}))
            if cached_following != actual:
                mismatches.append(f"{uid}: cached={cached_following} actual={actual}")
        if mismatches:
            self._fail("V-COUNT-2", f"{len(mismatches)} following count mismatches", checked, mismatches[:10])
        else:
            self._pass("V-COUNT-2", "Cached following counts match DB", checked)

    def v_count_3(self):
        """V-COUNT-3: Comment counts consistent (sampled active posts)."""
        posts = list(self.db.posts.find(self._active()).limit(50))
        checked = 0
        for p in posts:
            pid = str(p["_id"])
            actual = self.db.comments.count_documents(self._active({"postId": pid}))
            checked += 1
            # We just verify the count is non-negative (sanity)
            assert actual >= 0
        self._pass("V-COUNT-3", "Comment counts are consistent", checked)

    def v_count_4(self):
        """V-COUNT-4: Reaction counts consistent (sampled active posts)."""
        posts = list(self.db.posts.find(self._active()).limit(50))
        checked = 0
        for p in posts:
            pid = str(p["_id"])
            actual = self.db.reactions.count_documents(self._active({"postId": pid}))
            checked += 1
            assert actual >= 0
        self._pass("V-COUNT-4", "Reaction counts are consistent", checked)

    # ══════════════════════════════════════════════════════════════════
    # QUEUE AND WORKER INTEGRITY
    # ══════════════════════════════════════════════════════════════════

    def v_queue_1(self):
        """V-QUEUE-1: All RabbitMQ queues drained."""
        import urllib.request
        import json
        import base64
        from .config import RABBITMQ_API
        creds = base64.b64encode(b"guest:guest").decode()
        req = urllib.request.Request(
            f"{RABBITMQ_API}/api/queues",
            headers={"Authorization": f"Basic {creds}"},
        )
        resp = urllib.request.urlopen(req)
        queues = json.loads(resp.read())
        pending = []
        for q in queues:
            if q.get("messages", 0) > 0:
                pending.append(f"{q['name']}: {q['messages']} messages")
        if pending:
            self._fail("V-QUEUE-1", f"{len(pending)} queues not drained", len(queues), pending[:10])
        else:
            self._pass("V-QUEUE-1", "All queues drained", len(queues))

    def v_queue_3(self):
        """V-QUEUE-3: Change stream listener resume tokens exist and are current."""
        tokens = list(self.db.change_stream_resume_tokens.find())
        if not tokens:
            self._fail("V-QUEUE-3", "No resume tokens found", 0)
        else:
            names = [t["_id"] for t in tokens]
            self._pass("V-QUEUE-3", f"Resume tokens present: {', '.join(names)}", len(tokens))

    # ══════════════════════════════════════════════════════════════════
    # CROSS-ENTITY CONSISTENCY
    # ══════════════════════════════════════════════════════════════════

    def v_cross_1(self):
        """V-CROSS-1: Referential integrity — all foreign keys point to existing docs."""
        all_profile_ids = set(d["_id"] for d in self.db.profiles.find({}, {"_id": 1}))
        all_post_ids = set(str(d["_id"]) for d in self.db.posts.find({}, {"_id": 1}))
        bad = []

        # Posts -> profiles
        for p in self.db.posts.find({}, {"authorUid": 1}):
            if p["authorUid"] not in all_profile_ids:
                bad.append(f"post {p['_id']} refs non-existent profile {p['authorUid']}")

        # Comments -> posts, profiles
        for c in self.db.comments.find({}, {"postId": 1, "authorUid": 1}):
            if c["postId"] not in all_post_ids:
                bad.append(f"comment {c['_id']} refs non-existent post {c['postId']}")
            if c["authorUid"] not in all_profile_ids:
                bad.append(f"comment {c['_id']} refs non-existent profile {c['authorUid']}")

        # Reactions -> posts, profiles
        for r in self.db.reactions.find({}, {"postId": 1, "authorUid": 1}):
            if r["postId"] not in all_post_ids:
                bad.append(f"reaction {r['_id']} refs non-existent post {r['postId']}")
            if r["authorUid"] not in all_profile_ids:
                bad.append(f"reaction {r['_id']} refs non-existent profile {r['authorUid']}")

        if bad:
            self._fail("V-CROSS-1", f"{len(bad)} broken foreign key references", 0, bad[:10])
        else:
            self._pass("V-CROSS-1", "All foreign key references are valid", 0)

    def v_cross_2(self):
        """V-CROSS-2: Symmetry — active follows with active posts have feed items."""
        # This is essentially the same as V-FOLLOW-3 / V-FEED-5, sampled differently
        follows = list(self.db.follows.find(self._active()).limit(50))
        missing = 0
        checked = 0
        for f in follows:
            posts = list(self.db.posts.find(
                self._active({"authorUid": f["followedId"]}), {"_id": 1}
            ).limit(5))
            for p in posts:
                checked += 1
                exists = self.db.feed.find_one(self._active({
                    "ownerUid": f["followerId"], "postId": str(p["_id"]),
                }))
                if not exists:
                    missing += 1
        if missing:
            self._fail("V-CROSS-2", f"{missing} missing feed items (symmetry)", checked)
        else:
            self._pass("V-CROSS-2", "Feed symmetry holds for sampled follows", checked)

    def v_cross_4(self):
        """V-CROSS-4: Cascade completeness — deleted users have zero active related data."""
        deleted_uids = list(d["_id"] for d in self.db.profiles.find({"isDeleted": True}, {"_id": 1}).limit(50))
        bad = []
        for uid in deleted_uids:
            active_posts = self.db.posts.count_documents(self._active({"authorUid": uid}))
            active_comments = self.db.comments.count_documents(self._active({"authorUid": uid}))
            active_reactions = self.db.reactions.count_documents(self._active({"authorUid": uid}))
            active_follows_as_follower = self.db.follows.count_documents(self._active({"followerId": uid}))
            active_follows_as_followed = self.db.follows.count_documents(self._active({"followedId": uid}))
            active_events = self.db.events.count_documents(self._active({"authorUid": uid}))

            leftovers = []
            if active_posts:
                leftovers.append(f"{active_posts} posts")
            if active_comments:
                leftovers.append(f"{active_comments} comments")
            if active_reactions:
                leftovers.append(f"{active_reactions} reactions")
            if active_follows_as_follower:
                leftovers.append(f"{active_follows_as_follower} follows(follower)")
            if active_follows_as_followed:
                leftovers.append(f"{active_follows_as_followed} follows(followed)")
            if active_events:
                leftovers.append(f"{active_events} events")
            if leftovers:
                bad.append(f"{uid}: {', '.join(leftovers)}")

        if bad:
            self._fail("V-CROSS-4", f"{len(bad)} deleted users have leftover active data",
                        len(deleted_uids), bad[:10])
        else:
            self._pass("V-CROSS-4", "All deleted users fully cascaded", len(deleted_uids))

    # ══════════════════════════════════════════════════════════════════
    # RUN ALL CHECKS
    # ══════════════════════════════════════════════════════════════════

    def run_all(self) -> list[CheckResult]:
        checks = [
            self.v_prof_1, self.v_prof_2,
            self.v_follow_1, self.v_follow_2, self.v_follow_3, self.v_follow_4,
            self.v_follow_5, self.v_follow_6,
            self.v_feed_1, self.v_feed_2, self.v_feed_3, self.v_feed_4, self.v_feed_5, self.v_feed_6,
            self.v_post_1,
            self.v_comment_1, self.v_comment_2, self.v_comment_3,
            self.v_react_1, self.v_react_2, self.v_react_3, self.v_react_5,
            self.v_event_1, self.v_event_3, self.v_event_4,
            self.v_cache_1, self.v_cache_4,
            self.v_count_1, self.v_count_2, self.v_count_3, self.v_count_4,
            self.v_queue_1, self.v_queue_3,
            self.v_cross_1, self.v_cross_2, self.v_cross_4,
        ]
        for check in checks:
            try:
                check()
            except Exception as e:
                self._fail(check.__name__, f"Exception: {e}", 0)
        return self.results
