from pymongo import ASCENDING, GEOSPHERE


async def init_db(db) -> None:
    profiles = db.profiles
    await profiles.create_index([("username", ASCENDING)], unique=True)
    await profiles.create_index([("isDeleted", ASCENDING)])
    await profiles.create_index([("location", GEOSPHERE)], sparse=True)

    posts = db.posts
    await posts.create_index([("authorUid", ASCENDING)])
    await posts.create_index([("createdAt", ASCENDING)])
