from __future__ import annotations
import pytest
import mongomock_motor
import fakeredis.aioredis as aioredis


@pytest.fixture
def mongo():
    client = mongomock_motor.AsyncMongoMockClient()
    return client["fervora_test"]


@pytest.fixture
async def redis():
    r = aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()
