"""Shared test fixtures — flush Redis once at session start."""

import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def pytest_sessionstart(session):
    """Flush Redis before any test module runs to prevent stale cache entries."""
    redis.from_url(REDIS_URL).flushall()
