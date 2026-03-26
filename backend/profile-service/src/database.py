from pymongo import ASCENDING, GEOSPHERE


async def init_db(db) -> None:
    profiles = db.profiles
    await profiles.create_index([("username", ASCENDING)], unique=True)
    await profiles.create_index([("username", ASCENDING)], unique=True, collation={"locale": "en", "strength": 2})
    await profiles.create_index([("isDeleted", ASCENDING)])
    await profiles.create_index([("location", GEOSPHERE)], sparse=True)

    posts = db.posts
    await posts.create_index([("authorUid", ASCENDING)])
    await posts.create_index([("createdAt", ASCENDING)])
    await posts.create_index([("isDeleted", ASCENDING)])
    await posts.create_index([("storagePostId", ASCENDING)], unique=True, sparse=True)

    comments = db.comments
    await comments.create_index([("postId", ASCENDING)])
    await comments.create_index([("authorUid", ASCENDING)])
    await comments.create_index([("isDeleted", ASCENDING)])

    reactions = db.reactions
    await reactions.create_index([("postId", ASCENDING)])
    await reactions.create_index([("authorUid", ASCENDING)])
    await reactions.create_index([("postId", ASCENDING), ("authorUid", ASCENDING)], unique=True)
    await reactions.create_index([("isDeleted", ASCENDING)])

    events = db.events
    await events.create_index([("organizerUid", ASCENDING)])
    await events.create_index([("startsAt", ASCENDING)])
    await events.create_index([("isDeleted", ASCENDING)])

    rsvps = db.rsvps
    await rsvps.create_index([("eventId", ASCENDING)])
    await rsvps.create_index([("userId", ASCENDING)])
    await rsvps.create_index([("eventId", ASCENDING), ("userId", ASCENDING)], unique=True)
    await rsvps.create_index([("isDeleted", ASCENDING)])
