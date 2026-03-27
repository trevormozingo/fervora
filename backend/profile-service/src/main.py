from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager
import strawberry
from fastapi import FastAPI, Request, HTTPException
from strawberry.fastapi import GraphQLRouter
from strawberry.tools import merge_types
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis
import firebase_admin
from firebase_admin import auth as firebase_auth

from .database import init_db
from .resolvers.profiles import ProfileQuery, ProfileMutation
from .resolvers.posts import PostQuery, PostMutation
from .resolvers.comments import CommentQuery, CommentMutation
from .resolvers.reactions import ReactionQuery, ReactionMutation
from .resolvers.events import EventQuery, EventMutation
from .resolvers.feed import FeedQuery
from .resolvers.follows import FollowMutation
from .loaders import (
    make_profile_loader,
    make_post_loader,
    make_reaction_summary_loader,
    make_viewer_reaction_loader,
    make_rsvp_summary_loader,
    make_viewer_rsvp_loader,
)

_mongo_client: AsyncIOMotorClient | None = None
_redis: Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mongo_client, _redis

    # Initialize Firebase Admin SDK (uses FIREBASE_AUTH_EMULATOR_HOST env var automatically)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={
            "projectId": os.environ.get("FIREBASE_PROJECT_ID", "fervora-local"),
            "storageBucket": f"{os.environ.get('FIREBASE_PROJECT_ID', 'fervora-local')}.appspot.com",
        })

    _mongo_client = AsyncIOMotorClient(os.environ["MONGO_URI"])
    _redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await init_db(_mongo_client[os.environ.get("MONGO_DB", "fervora")])
    yield
    _mongo_client.close()
    await _redis.aclose()


async def _get_user_id(request: Request) -> str | None:
    """Extract and verify the Firebase ID token from the Authorization header."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:]
    try:
        decoded = await asyncio.to_thread(firebase_auth.verify_id_token, token)
        return decoded["uid"]
    except Exception:
        return None


async def get_context(request: Request):
    user_id = await _get_user_id(request)
    db = _mongo_client[os.environ.get("MONGO_DB", "fervora")]
    return {
        "user_id": user_id,
        "db": db,
        "redis": _redis,
        "profile_loader": make_profile_loader(db, _redis),
        "post_loader": make_post_loader(db, _redis),
        "reaction_summary_loader": make_reaction_summary_loader(db),
        "viewer_reaction_loader": make_viewer_reaction_loader(db, user_id),
        "rsvp_summary_loader": make_rsvp_summary_loader(db),
        "viewer_rsvp_loader": make_viewer_rsvp_loader(db, user_id),
    }


Query = merge_types("Query", (ProfileQuery, PostQuery, CommentQuery, ReactionQuery, EventQuery, FeedQuery))
Mutation = merge_types("Mutation", (ProfileMutation, PostMutation, CommentMutation, ReactionMutation, EventMutation, FollowMutation))

schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
def health():
    return {"status": "ok"}
