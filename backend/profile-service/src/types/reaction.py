from __future__ import annotations
from typing import Optional
import strawberry
from strawberry.types import Info
from .profile import Profile


VALID_REACTION_TYPES = {"like", "fire", "strong", "clap", "heart"}


def _parse_reaction_type(value: str) -> str:
    if value not in VALID_REACTION_TYPES:
        raise ValueError(f"reactionType must be one of {sorted(VALID_REACTION_TYPES)}")
    return value


ReactionType = strawberry.scalar(str, name="ReactionType", parse_value=_parse_reaction_type)


# ── Output types ──────────────────────────────────────────────────────────────

@strawberry.type
class ReactionSummary:
    reaction_type: str
    count: int


@strawberry.type
class Reaction:
    id: strawberry.ID
    author_uid: strawberry.Private[str]
    post_id: str
    reaction_type: str
    created_at: str

    @strawberry.field
    async def author(self, info: Info) -> Optional[Profile]:
        return await info.context["profile_loader"].load(self.author_uid)


# ── Input types ───────────────────────────────────────────────────────────────

@strawberry.input
class SetReactionInput:
    post_id: strawberry.ID
    reaction_type: ReactionType
