"""Transaction retry helper for MongoDB write-lock transactions."""

import asyncio
import logging

from fastapi import HTTPException
from pymongo.errors import OperationFailure

from .database import get_client

logger = logging.getLogger(__name__)

MAX_RETRIES = 10


async def run_transaction(callback):
    """Run *callback(session)* inside a transaction with up to 10 retries on WriteConflict."""
    for attempt in range(1, MAX_RETRIES + 1):
        async with await get_client().start_session() as session:
            async with session.start_transaction():
                try:
                    return await callback(session)
                except OperationFailure as exc:
                    if exc.code == 112 and attempt < MAX_RETRIES:
                        logger.debug("WriteConflict (attempt %d/%d), retrying", attempt, MAX_RETRIES)
                        await asyncio.sleep(0.01 * attempt)
                        continue
                    if exc.code == 112:
                        raise HTTPException(status_code=409, detail="Concurrent write conflict, please retry")
                    raise
