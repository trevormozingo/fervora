"""Follow service integration tests.

One-way follow model:
  - POST /follows/{uid}    → follow (201), already following (409), no profile (404), self (422)
  - DELETE /follows/{uid}   → unfollow (204), not following (404)
  - GET /follows/following  → list who I follow
  - GET /follows/followers  → list who follows me
  - GET /follows/{uid}/following → list who a user follows
  - GET /follows/{uid}/followers → list who follows a user
  - Follow/unfollow events published to RabbitMQ
"""

import json
import os
import time
import uuid

import pika
import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

EXCHANGE_NAME = "events.consistent"
NUM_TEST_QUEUES = 4
TEST_QUEUE_PREFIX = "test-follows-"


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid}


def _uid() -> str:
    return f"ftest-{uuid.uuid4().hex[:12]}"


def _ensure_profile(uid: str):
    username = f"u{uid.replace('-', '')[:14]}"
    r = requests.get(_url(f"/profiles/{uid}"), headers=_headers(uid))
    if r.status_code == 404:
        body = {
            "username": username,
            "displayName": "Follow Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        }
        r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
        assert r.status_code == 201


def _rmq_connection():
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def _drain_queue(channel, queue_name, timeout=5.0):
    """Consume all messages from a queue within timeout."""
    messages = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        method, _, body = channel.basic_get(queue=queue_name, auto_ack=True)
        if method:
            messages.append(json.loads(body))
        else:
            time.sleep(0.2)
    return messages


def _drain_all_queues(channel, timeout=5.0):
    result = {}
    for i in range(NUM_TEST_QUEUES):
        q = f"{TEST_QUEUE_PREFIX}{i}"
        result[q] = _drain_queue(channel, q, timeout)
    return result


def _all_messages(queues_dict):
    msgs = []
    for v in queues_dict.values():
        msgs.extend(v)
    return msgs


def setup_module():
    """Clear follows collection and set up RabbitMQ test queues."""
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].follows.delete_many({})
    client.close()

    conn = _rmq_connection()
    ch = conn.channel()
    # Declare test queues bound to the consistent-hash exchange
    for i in range(NUM_TEST_QUEUES):
        q = f"{TEST_QUEUE_PREFIX}{i}"
        ch.queue_declare(queue=q, durable=True)
        ch.queue_bind(exchange=EXCHANGE_NAME, queue=q, routing_key="10")
        ch.queue_purge(queue=q)
    conn.close()


def teardown_module():
    """Clean up test queues."""
    try:
        conn = _rmq_connection()
        ch = conn.channel()
        for i in range(NUM_TEST_QUEUES):
            q = f"{TEST_QUEUE_PREFIX}{i}"
            ch.queue_unbind(exchange=EXCHANGE_NAME, queue=q, routing_key="10")
            ch.queue_delete(queue=q)
        conn.close()
    except Exception:
        pass


# ── Follow ────────────────────────────────────────────────────────────

def test_follow_user():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    r = requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 201
    data = r.json()
    assert data["followerUid"] == a
    assert data["followingUid"] == b


def test_follow_already_following():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r = requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 409


def test_follow_self_rejected():
    a = _uid()
    _ensure_profile(a)
    r = requests.post(_url(f"/follows/{a}"), headers=_headers(a))
    assert r.status_code == 422


def test_follow_target_no_profile():
    a = _uid()
    _ensure_profile(a)
    r = requests.post(_url(f"/follows/{_uid()}"), headers=_headers(a))
    assert r.status_code == 404


def test_follow_follower_no_profile():
    b = _uid()
    _ensure_profile(b)
    r = requests.post(_url(f"/follows/{b}"), headers=_headers(_uid()))
    assert r.status_code == 404


# ── Unfollow ──────────────────────────────────────────────────────────

def test_unfollow_user():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 204


def test_unfollow_not_following():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    r = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r.status_code == 404


def test_unfollow_idempotent():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r1 = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r1.status_code == 204
    r2 = requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    assert r2.status_code == 404


def test_unfollow_is_one_directional():
    """A follows B, then A unfollows B — B's follow of A is unaffected."""
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    requests.post(_url(f"/follows/{a}"), headers=_headers(b))
    # A unfollows B
    requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    # B should still follow A
    r = requests.get(_url("/follows/following"), headers=_headers(b))
    following_ids = [p["id"] for p in r.json()["following"]]
    assert a in following_ids


# ── List following/followers ──────────────────────────────────────────

def test_following_list():
    a, b, c = _uid(), _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    _ensure_profile(c)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    requests.post(_url(f"/follows/{c}"), headers=_headers(a))
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    assert r.status_code == 200
    data = r.json()
    following_ids = {p["id"] for p in data["following"]}
    assert following_ids == {b, c}
    assert data["count"] == 2


def test_followers_list():
    a, b, c = _uid(), _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    _ensure_profile(c)
    requests.post(_url(f"/follows/{a}"), headers=_headers(b))
    requests.post(_url(f"/follows/{a}"), headers=_headers(c))
    r = requests.get(_url("/follows/followers"), headers=_headers(a))
    assert r.status_code == 200
    data = r.json()
    follower_ids = {p["id"] for p in data["followers"]}
    assert follower_ids == {b, c}
    assert data["count"] == 2


def test_empty_following():
    a = _uid()
    _ensure_profile(a)
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    assert r.json() == {"following": [], "count": 0}


def test_empty_followers():
    a = _uid()
    _ensure_profile(a)
    r = requests.get(_url("/follows/followers"), headers=_headers(a))
    assert r.json() == {"followers": [], "count": 0}


def test_follow_is_not_mutual():
    """A follows B does NOT mean B follows A."""
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    # A follows B
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    following_ids = [p["id"] for p in r.json()["following"]]
    assert b in following_ids
    # B does NOT follow A
    r = requests.get(_url("/follows/following"), headers=_headers(b))
    following_ids = [p["id"] for p in r.json()["following"]]
    assert a not in following_ids


def test_list_other_user_following():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    # Third party can see A's following list
    r = requests.get(_url(f"/follows/{a}/following"), headers=_headers(b))
    assert r.status_code == 200
    following_ids = [p["id"] for p in r.json()["following"]]
    assert b in following_ids


def test_list_other_user_followers():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    # Third party can see B's followers list
    r = requests.get(_url(f"/follows/{b}/followers"), headers=_headers(a))
    assert r.status_code == 200
    follower_ids = [p["id"] for p in r.json()["followers"]]
    assert a in follower_ids


# ── Profile counts ────────────────────────────────────────────────────

def test_follow_updates_profile_counts():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)

    # Initially 0
    r = requests.get(_url(f"/profiles/{a}"), headers=_headers(a))
    assert r.json()["followingCount"] == 0

    requests.post(_url(f"/follows/{b}"), headers=_headers(a))

    # A's followingCount = 1, B's followersCount = 1
    r = requests.get(_url(f"/profiles/{a}"), headers=_headers(a))
    assert r.json()["followingCount"] == 1

    r = requests.get(_url(f"/profiles/{b}"), headers=_headers(b))
    assert r.json()["followersCount"] == 1


def test_unfollow_updates_profile_counts():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)

    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    requests.delete(_url(f"/follows/{b}"), headers=_headers(a))

    r = requests.get(_url(f"/profiles/{a}"), headers=_headers(a))
    assert r.json()["followingCount"] == 0

    r = requests.get(_url(f"/profiles/{b}"), headers=_headers(b))
    assert r.json()["followersCount"] == 0


# ── Resolved profiles in follow lists ────────────────────────────────

def test_following_list_has_profile_fields():
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    r = requests.get(_url("/follows/following"), headers=_headers(a))
    profile = r.json()["following"][0]
    assert "id" in profile
    assert "username" in profile
    assert "displayName" in profile
    assert "profilePhoto" in profile


# ── Change-stream events via RabbitMQ ────────────────────────────────

def test_follow_produces_change_stream_event():
    """Following a user triggers a change-stream insert event for the follows collection."""
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)

    # Drain stale messages
    conn = _rmq_connection()
    ch = conn.channel()
    _drain_all_queues(ch, timeout=1.0)

    requests.post(_url(f"/follows/{b}"), headers=_headers(a))
    time.sleep(2)

    queues = _drain_all_queues(ch, timeout=3.0)
    conn.close()
    messages = _all_messages(queues)

    follow_events = [
        m for m in messages
        if m.get("collection") == "follows" and m.get("operationType") == "insert"
    ]
    assert len(follow_events) >= 1
    evt = follow_events[0]
    assert evt["fullDocument"]["followerId"] == a
    assert evt["fullDocument"]["followedId"] == b
    assert "timestamp" in evt


def test_unfollow_produces_change_stream_event():
    """Unfollowing a user triggers a change-stream update event (soft-delete)."""
    a, b = _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b)
    requests.post(_url(f"/follows/{b}"), headers=_headers(a))

    # Drain stale messages
    conn = _rmq_connection()
    ch = conn.channel()
    _drain_all_queues(ch, timeout=1.0)

    requests.delete(_url(f"/follows/{b}"), headers=_headers(a))
    time.sleep(2)

    queues = _drain_all_queues(ch, timeout=3.0)
    conn.close()
    messages = _all_messages(queues)

    update_events = [
        m for m in messages
        if m.get("collection") == "follows" and m.get("operationType") == "update"
    ]
    assert len(update_events) >= 1
    evt = update_events[0]
    # Soft-delete: fullDocument should have isDeleted = True
    assert evt["fullDocument"]["isDeleted"] is True
    assert evt["fullDocument"]["followerId"] == a
    assert evt["fullDocument"]["followedId"] == b


def test_follow_event_routed_by_follower_uid():
    """Follow events from the same user should always land on the same queue."""
    a, b1, b2 = _uid(), _uid(), _uid()
    _ensure_profile(a)
    _ensure_profile(b1)
    _ensure_profile(b2)

    conn = _rmq_connection()
    ch = conn.channel()
    _drain_all_queues(ch, timeout=1.0)

    requests.post(_url(f"/follows/{b1}"), headers=_headers(a))
    requests.post(_url(f"/follows/{b2}"), headers=_headers(a))
    time.sleep(2)

    queues = _drain_all_queues(ch, timeout=3.0)
    conn.close()

    # Both events should land on the same queue (consistent hash by followerId)
    queues_with_follow_events = [
        q for q, msgs in queues.items()
        if any(m.get("collection") == "follows" for m in msgs)
    ]
    assert len(queues_with_follow_events) == 1
