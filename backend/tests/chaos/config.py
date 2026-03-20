"""Chaos test configuration — all tuneable knobs in one place."""

import os

# ── Scale ─────────────────────────────────────────────────────────────
NUM_USERS = int(os.getenv("CHAOS_USERS", "1000"))
NUM_POSTS_PER_USER = int(os.getenv("CHAOS_POSTS_PER_USER", "10"))
FOLLOWS_PER_USER = int(os.getenv("CHAOS_FOLLOWS_PER_USER", "10"))
COMMENTS_PER_USER = int(os.getenv("CHAOS_COMMENTS_PER_USER", "10"))
REACTIONS_PER_USER = int(os.getenv("CHAOS_REACTIONS_PER_USER", "10"))
EVENTS_PER_USER_FRAC = float(os.getenv("CHAOS_EVENTS_FRAC", "0.3"))  # 30% of users create events

# ── Chaos phase ───────────────────────────────────────────────────────
CHAOS_DURATION_SECONDS = int(os.getenv("CHAOS_DURATION", "60"))
NUM_CONCURRENT_REQUESTS = int(os.getenv("CHAOS_CONCURRENCY", "50"))

# ── Stress pattern sizes ─────────────────────────────────────────────
PATTERN_A_FOLLOWERS = int(os.getenv("PATTERN_A_FOLLOWERS", "200"))
PATTERN_B_FOLLOWERS = int(os.getenv("PATTERN_B_FOLLOWERS", "200"))
PATTERN_B_UNFOLLOWERS = int(os.getenv("PATTERN_B_UNFOLLOWERS", "200"))
PATTERN_C_TOGGLES = int(os.getenv("PATTERN_C_TOGGLES", "100"))
PATTERN_D_USERS = int(os.getenv("PATTERN_D_USERS", "100"))
PATTERN_E_REACTORS = int(os.getenv("PATTERN_E_REACTORS", "100"))
PATTERN_F_COMMENTERS = int(os.getenv("PATTERN_F_COMMENTERS", "100"))
PATTERN_H_DELETIONS = int(os.getenv("PATTERN_H_DELETIONS", "100"))

# ── Chaos operation weights (higher = more frequent) ─────────────────
OP_WEIGHTS = {
    "create_profile": 2,
    "delete_profile": 1,
    "follow": 10,
    "unfollow": 5,
    "refollow": 3,
    "create_post": 8,
    "delete_post": 3,
    "add_comment": 8,
    "delete_comment": 2,
    "add_reaction": 8,
    "change_reaction": 4,
    "remove_reaction": 3,
    "rereact": 2,
    "create_event": 3,
    "delete_event": 1,
    "rapid_follow_unfollow": 2,
    "rapid_post_create_delete": 2,
    "follow_deleted_user": 1,
    "post_by_deleted_user": 1,
    "comment_on_deleted_post": 1,
    "react_on_deleted_post": 1,
}

# ── Infrastructure ────────────────────────────────────────────────────
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
RABBITMQ_API = os.getenv("RABBITMQ_API", "http://rabbitmq:15672")

# ── Drain / settle ───────────────────────────────────────────────────
DRAIN_POLL_INTERVAL = 2          # seconds between queue-depth polls
DRAIN_TIMEOUT = 120              # seconds max to wait for drain
SETTLE_TIME = 10                 # extra seconds after drain

# ── Reaction types ────────────────────────────────────────────────────
REACTION_TYPES = ["strong", "fire", "heart", "smile", "laugh", "thumbsup", "thumbsdown", "angry"]
