import os
from contextlib import asynccontextmanager
import strawberry
from fastapi import FastAPI, Request, HTTPException
from strawberry.fastapi import GraphQLRouter
from strawberry.tools import merge_types
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from .database import init_db
from .resolvers.profiles import ProfileQuery, ProfileMutation
from .resolvers.posts import PostQuery, PostMutation
from .resolvers.comments import CommentQuery, CommentMutation
from .resolvers.reactions import ReactionQuery, ReactionMutation
from .resolvers.events import EventQuery, EventMutation
from .loaders import make_profile_loader, make_post_loader

_mongo_client: AsyncIOMotorClient | None = None
_redis: Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mongo_client, _redis
    _mongo_client = AsyncIOMotorClient(os.environ["MONGO_URI"])
    _redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await init_db(_mongo_client[os.environ.get("MONGO_DB", "fervora")])
    yield
    _mongo_client.close()
    await _redis.aclose()


def get_context(request: Request):
    user_id = request.headers.get("x-user-id")
    if not user_id and request.method != "GET":
        raise HTTPException(status_code=401, detail="x-user-id header is required")
    db = _mongo_client[os.environ.get("MONGO_DB", "fervora")]
    return {
        "user_id": user_id,
        "db": db,
        "redis": _redis,
        "profile_loader": make_profile_loader(db, _redis),
        "post_loader": make_post_loader(db, _redis),
    }


Query = merge_types("Query", (ProfileQuery, PostQuery, CommentQuery, ReactionQuery, EventQuery))
Mutation = merge_types("Mutation", (ProfileMutation, PostMutation, CommentMutation, ReactionMutation, EventMutation))

schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
def health():
    return {"status": "ok"}
