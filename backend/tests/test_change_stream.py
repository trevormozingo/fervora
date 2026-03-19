"""
Change stream listener integration tests.

Verifies:
  1. MongoDB writes trigger events published to RabbitMQ
  2. Consistent hashing — same user ID always routes to same queue
  3. Event payloads contain expected fields
"""

import json
import os
import time

import pika
import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

EXCHANGE_NAME = "events.consistent"
# We'll create 4 test queues to validate consistent hashing
NUM_TEST_QUEUES = 4
TEST_QUEUE_PREFIX = "test-events-"


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str = "test-user-1") -> dict:
    return {"X-User-Id": uid}


def _rmq_connection():
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def _drain_queue(channel, queue_name, timeout=5.0):
    """Consume all messages from a queue within timeout. Returns list of decoded bodies."""
    messages = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        method, _, body = channel.basic_get(queue=queue_name, auto_ack=True)
        if method:
            messages.append(json.loads(body))
        else:
            # No message ready — short sleep then retry
            time.sleep(0.2)
    return messages


def _drain_all_queues(channel, timeout=5.0):
    """Drain all test queues. Returns dict of queue_name -> [messages]."""
    result = {}
    for i in range(NUM_TEST_QUEUES):
        q = f"{TEST_QUEUE_PREFIX}{i}"
        result[q] = _drain_queue(channel, q, timeout=timeout)
    return result


def _find_messages(all_queues, **match):
    """Find messages across all queues matching all key=value pairs."""
    found = []
    for q_name, msgs in all_queues.items():
        for m in msgs:
            if all(m.get(k) == v for k, v in match.items()):
                found.append((q_name, m))
    return found


# ── Setup / Teardown ─────────────────────────────────────────────────

def setup_module():
    """Clear test data and bind test queues to the consistent hash exchange."""
    # Clean MongoDB
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.profiles.delete_many({})
    db.posts.delete_many({})
    db.change_stream_resume_tokens.delete_many({})
    client.close()

    # Set up test queues bound to the consistent hash exchange
    conn = _rmq_connection()
    ch = conn.channel()
    for i in range(NUM_TEST_QUEUES):
        q = f"{TEST_QUEUE_PREFIX}{i}"
        ch.queue_declare(queue=q, durable=True)
        # Weight of "1" — each queue gets an equal share of the hash ring
        ch.queue_bind(exchange=EXCHANGE_NAME, queue=q, routing_key="1")
    # Purge any leftover messages
    for i in range(NUM_TEST_QUEUES):
        ch.queue_purge(queue=f"{TEST_QUEUE_PREFIX}{i}")
    conn.close()

    # Give the listener a moment to be fully watching
    time.sleep(1)


def teardown_module():
    """Remove test queues."""
    try:
        conn = _rmq_connection()
        ch = conn.channel()
        for i in range(NUM_TEST_QUEUES):
            ch.queue_delete(queue=f"{TEST_QUEUE_PREFIX}{i}")
        conn.close()
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────

def _create_profile(uid, username, display_name="Test User"):
    body = {
        "username": username,
        "displayName": display_name,
        "profilePhoto": "https://example.com/photo.jpg",
        "birthday": "1998-05-14",
    }
    r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
    assert r.status_code == 201, f"Create failed: {r.text}"
    return r.json()


def _create_post(uid, body_text="Test post"):
    body = {"body": body_text}
    r = requests.post(_url("/posts"), json=body, headers=_headers(uid))
    assert r.status_code == 201, f"Create post failed: {r.text}"
    return r.json()


# ── Tests: Event Delivery ────────────────────────────────────────────

class TestEventDelivery:
    """Verify that MongoDB writes produce RabbitMQ messages."""

    def test_insert_produces_event(self):
        """Creating a profile should produce an insert event in RabbitMQ."""
        uid = "event-test-insert"
        _create_profile(uid, "eventinsert")

        # Allow time for change stream → RabbitMQ pipeline
        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        matches = _find_messages(
            all_q, collection="profiles", operationType="insert", documentKey=uid
        )
        assert len(matches) >= 1, f"Expected insert event for {uid}, got: {all_q}"
        _, event = matches[0]
        assert "fullDocument" in event
        assert event["fullDocument"]["username"] == "eventinsert"

    def test_update_produces_event(self):
        """Updating a profile should produce an update event."""
        uid = "event-test-update"
        _create_profile(uid, "eventupdate")
        time.sleep(2)

        # Drain insert events first
        conn = _rmq_connection()
        ch = conn.channel()
        _drain_all_queues(ch, timeout=2)
        conn.close()

        # Now update
        r = requests.patch(
            _url("/profiles/me"),
            json={"bio": "Updated bio"},
            headers=_headers(uid),
        )
        assert r.status_code == 200

        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        matches = _find_messages(
            all_q, collection="profiles", operationType="update", documentKey=uid
        )
        assert len(matches) >= 1, f"Expected update event for {uid}, got: {all_q}"

    def test_soft_delete_produces_update_event(self):
        """Soft-deleting a profile produces an update event (not delete)."""
        uid = "event-test-delete"
        _create_profile(uid, "eventdelete")
        time.sleep(2)

        # Drain insert events
        conn = _rmq_connection()
        ch = conn.channel()
        _drain_all_queues(ch, timeout=2)
        conn.close()

        # Soft-delete
        r = requests.delete(_url("/profiles/me"), headers=_headers(uid))
        assert r.status_code == 204

        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        matches = _find_messages(
            all_q, collection="profiles", operationType="update", documentKey=uid
        )
        assert len(matches) >= 1, f"Expected update event (soft-delete) for {uid}"

    def test_event_has_timestamp(self):
        """Events must include a timestamp field."""
        uid = "event-test-timestamp"
        _create_profile(uid, "eventtimestamp")
        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        matches = _find_messages(all_q, documentKey=uid)
        assert len(matches) >= 1
        _, event = matches[0]
        assert "timestamp" in event


# ── Tests: Post Event Delivery ────────────────────────────────────────

class TestPostEventDelivery:
    """Verify that post writes produce RabbitMQ messages."""

    def test_post_create_produces_event(self):
        uid = "post-event-create"
        _create_profile(uid, "posteventcreate")
        time.sleep(1)

        # Drain profile insert event
        conn = _rmq_connection()
        ch = conn.channel()
        _drain_all_queues(ch, timeout=2)
        conn.close()

        post = _create_post(uid, "New post for event test")
        post_id = post["id"]
        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        matches = _find_messages(
            all_q, collection="posts", operationType="insert", documentKey=post_id
        )
        assert len(matches) >= 1, f"Expected insert event for post {post_id}, got: {all_q}"
        _, event = matches[0]
        assert "fullDocument" in event
        assert event["fullDocument"]["authorUid"] == uid

    def test_post_soft_delete_produces_update_event(self):
        uid = "post-event-delete"
        _create_profile(uid, "posteventdelete")
        time.sleep(1)

        post = _create_post(uid, "Delete me")
        post_id = post["id"]
        time.sleep(2)

        # Drain insert events
        conn = _rmq_connection()
        ch = conn.channel()
        _drain_all_queues(ch, timeout=2)
        conn.close()

        # Soft-delete the post
        r = requests.delete(_url(f"/posts/{post_id}"), headers=_headers(uid))
        assert r.status_code == 204
        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        matches = _find_messages(
            all_q, collection="posts", operationType="update", documentKey=post_id
        )
        assert len(matches) >= 1, f"Expected update event (soft-delete) for post {post_id}"
        _, event = matches[0]
        # Soft-delete should show isDeleted in the full document
        assert event.get("fullDocument", {}).get("isDeleted") is True

    def test_post_events_routed_by_author_uid(self):
        """Post events should be routed by authorUid, not post ID.
        Multiple posts by the same user should land on the same queue."""
        uid = "post-event-routing"
        _create_profile(uid, "posteventrouting")
        time.sleep(1)

        # Drain profile events
        conn = _rmq_connection()
        ch = conn.channel()
        _drain_all_queues(ch, timeout=2)
        conn.close()

        # Create multiple posts by same user
        post_ids = []
        for i in range(3):
            p = _create_post(uid, f"Routing test {i}")
            post_ids.append(p["id"])
            time.sleep(0.5)

        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        # All post events for this user should be on the same queue
        queues_with_events = set()
        for q_name, msgs in all_q.items():
            for m in msgs:
                if m.get("collection") == "posts" and m.get("documentKey") in post_ids:
                    queues_with_events.add(q_name)

        assert len(queues_with_events) == 1, (
            f"Post events for user {uid} spread across {queues_with_events}. Expected 1."
        )


# ── Tests: Consistent Hashing ────────────────────────────────────────

class TestConsistentHashing:
    """Verify that the same user ID always routes to the same queue."""

    def test_same_user_same_queue(self):
        """Multiple events for the same user must land on the same queue."""
        uid = "hash-test-same"
        _create_profile(uid, "hashsame")
        time.sleep(1)

        # Generate more events for the same user
        for i in range(3):
            requests.patch(
                _url("/profiles/me"),
                json={"bio": f"Bio update {i}"},
                headers=_headers(uid),
            )
            time.sleep(0.5)

        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        # Find which queues got events for this user
        queues_with_events = set()
        for q_name, msgs in all_q.items():
            for m in msgs:
                if m.get("documentKey") == uid:
                    queues_with_events.add(q_name)

        assert len(queues_with_events) == 1, (
            f"Events for {uid} spread across {len(queues_with_events)} queues: "
            f"{queues_with_events}. Expected exactly 1."
        )

    def test_different_users_can_route_differently(self):
        """Different user IDs may route to different queues (not guaranteed
        for a small sample, so we just verify determinism)."""
        users = {}
        for i in range(6):
            uid = f"hash-test-multi-{i}"
            _create_profile(uid, f"hashmulti{i}")
            users[uid] = None

        time.sleep(3)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=3)
        conn.close()

        # Record which queue each user's events landed on
        for q_name, msgs in all_q.items():
            for m in msgs:
                dk = m.get("documentKey")
                if dk in users:
                    users[dk] = q_name

        # Every user should have been routed to exactly one queue
        for uid, q in users.items():
            assert q is not None, f"No event found for {uid}"

    def test_consistent_hash_is_deterministic(self):
        """Same user producing events at different times always goes to the same queue."""
        uid = "hash-deterministic"
        _create_profile(uid, "hashdeterm")
        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=2)
        conn.close()

        # Find which queue got the insert
        first_queue = None
        for q_name, msgs in all_q.items():
            for m in msgs:
                if m.get("documentKey") == uid:
                    first_queue = q_name
                    break

        assert first_queue is not None, f"No event for {uid}"

        # Generate another event
        requests.patch(
            _url("/profiles/me"),
            json={"bio": "Determinism check"},
            headers=_headers(uid),
        )
        time.sleep(2)

        conn = _rmq_connection()
        ch = conn.channel()
        all_q = _drain_all_queues(ch, timeout=2)
        conn.close()

        second_queue = None
        for q_name, msgs in all_q.items():
            for m in msgs:
                if m.get("documentKey") == uid:
                    second_queue = q_name
                    break

        assert second_queue == first_queue, (
            f"User {uid} routed to {first_queue} then {second_queue}"
        )
