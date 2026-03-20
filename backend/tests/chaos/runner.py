"""
Chaos test runner — orchestrates seed → chaos → drain → validate.

Usage:
    python -m tests.chaos.runner          # from backend/
    CHAOS_USERS=50 python -m tests.chaos.runner   # quick smoke test
"""

import asyncio
import base64
import json
import logging
import sys
import time
import urllib.request

import pymongo

from .client import ApiClient
from .config import (
    DRAIN_POLL_INTERVAL,
    DRAIN_TIMEOUT,
    MONGO_DB,
    MONGO_URI,
    RABBITMQ_API,
    SETTLE_TIME,
)
from .seed import seed
from .chaos_ops import run_chaos
from .state import ChaosState
from .validate import Validator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("chaos.runner")


def _queues_pending() -> int:
    """Total pending messages across all RabbitMQ queues."""
    creds = base64.b64encode(b"guest:guest").decode()
    req = urllib.request.Request(
        f"{RABBITMQ_API}/api/queues",
        headers={"Authorization": f"Basic {creds}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        queues = json.loads(resp.read())
        return sum(q.get("messages", 0) for q in queues)
    except Exception as e:
        log.warning("Failed to poll RabbitMQ queues: %s", e)
        return -1


def _wait_for_drain():
    """Poll RabbitMQ until all queues are empty or timeout."""
    log.info("Waiting for worker queues to drain (timeout %ds) …", DRAIN_TIMEOUT)
    deadline = time.monotonic() + DRAIN_TIMEOUT
    while time.monotonic() < deadline:
        pending = _queues_pending()
        if pending == 0:
            log.info("All queues drained")
            break
        if pending > 0:
            log.info("  %d messages still pending …", pending)
        time.sleep(DRAIN_POLL_INTERVAL)
    else:
        pending = _queues_pending()
        if pending > 0:
            log.warning("Drain timeout reached with %d messages pending", pending)

    log.info("Settling for %ds …", SETTLE_TIME)
    time.sleep(SETTLE_TIME)


def _reset_database():
    """Drop all test collections so each run starts clean."""
    log.info("Resetting database %s …", MONGO_DB)
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    for name in db.list_collection_names():
        if name == "change_stream_resume_tokens":
            continue  # preserve resume tokens
        db[name].delete_many({})
    client.close()


def _print_report(results):
    """Print the spec-format report."""
    passed = sum(1 for r in results if r.passed and not r.warn)
    warned = sum(1 for r in results if r.warn)
    failed = sum(1 for r in results if not r.passed)

    print("\n" + "=" * 72)
    print("CHAOS TEST RESULTS")
    print("=" * 72)

    for r in results:
        if r.warn:
            tag = "[WARN]"
        elif r.passed:
            tag = "[PASS]"
        else:
            tag = "[FAIL]"
        checked_str = f"(checked {r.checked:,})" if r.checked else ""
        print(f"{tag} {r.name}: {r.detail} {checked_str}")
        if r.failures:
            for f in r.failures:
                print(f"  - {f}")

    print("\n" + "-" * 72)
    print(f"Total checks: {len(results)}")
    print(f"Passed: {passed}")
    if warned:
        print(f"Warned: {warned}")
    print(f"Failed: {failed}")
    print("-" * 72)

    return failed == 0


async def _run():
    state = ChaosState()
    api = ApiClient()

    try:
        # Phase 0: Clean slate
        _reset_database()

        # Phase 1: Seed
        log.info("═══ PHASE 1: SEED ═══")
        await seed(api, state)

        # Wait for seed side-effects (feed fan-out, etc.)
        _wait_for_drain()

        # Phase 2: Chaos
        log.info("═══ PHASE 2: CHAOS ═══")
        await run_chaos(api, state)

        # Phase 3: Drain + validate
        log.info("═══ PHASE 3: DRAIN & VALIDATE ═══")
        _wait_for_drain()

    finally:
        await api.close()

    # Run validation
    validator = Validator()
    try:
        results = validator.run_all()
    finally:
        validator.close()

    all_passed = _print_report(results)

    # Write operation log
    log.info("Writing operation log (%d entries) …", len(state.log))
    with open("/tmp/chaos_ops.log", "w") as f:
        for rec in state.log:
            f.write(f"{rec.ts} {rec.op:30s} uid={rec.uid:20s} ok={rec.ok} "
                    f"status={rec.status_code} {rec.detail}\n")
    log.info("Log written to /tmp/chaos_ops.log")

    return all_passed


def main():
    success = asyncio.run(_run())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
