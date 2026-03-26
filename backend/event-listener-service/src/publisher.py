import json
import aio_pika

QUEUES = [
    "profile.deleted",
    "post.created",
    "post.deleted",
    "follow.created",
    "follow.deleted",
]


async def connect_rabbitmq(url: str) -> aio_pika.RobustConnection:
    return await aio_pika.connect_robust(url)


async def setup_queues(channel: aio_pika.Channel) -> None:
    """Declare all queues as durable so they survive broker restarts."""
    for name in QUEUES:
        await channel.declare_queue(name, durable=True)


async def publish(channel: aio_pika.Channel, queue_name: str, payload: dict) -> None:
    """Publish a JSON-encoded, persistent message to a named queue."""
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=queue_name,
    )
