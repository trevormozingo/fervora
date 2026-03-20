"""
Handler registry — dispatches events to collection-specific callbacks.

Each handler receives the full event dict and is an async function.
Register handlers by decorating with @register or calling register() directly.
"""

import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# (collection, operation_type) -> handler
Handler = Callable[[dict[str, Any]], Awaitable[None]]
_handlers: dict[tuple[str, str], Handler] = {}


def register(collection: str, operation: str):
    """Decorator to register a handler for a (collection, operationType) pair."""
    def decorator(fn: Handler) -> Handler:
        _handlers[(collection, operation)] = fn
        return fn
    return decorator


async def dispatch(event: dict[str, Any]) -> None:
    """Route an event to its registered handler."""
    collection = event.get("collection", "unknown")
    operation = event.get("operationType", "unknown")
    key = (collection, operation)

    handler = _handlers.get(key)
    if handler is None:
        logger.warning("No handler for %s.%s (key=%s)", collection, operation, event.get("documentKey"))
        return

    await handler(event)
