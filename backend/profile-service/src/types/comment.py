from __future__ import annotations
from typing import Optional
import strawberry
from strawberry.types import Info
from .profile import Profile


def _parse_comment_body(value: str) -> str:
    if not (1 <= len(value) <= 1000):
        raise ValueError("body must be between 1 and 1000 characters")
    return value


CommentBody = strawberry.scalar(str, name="CommentBody", parse_value=_parse_comment_body)


# ── Output types ──────────────────────────────────────────────────────────────

@strawberry.type
class Comment:
    id: strawberry.ID
    author_uid: strawberry.Private[str]
    post_id: str
    body: str
    created_at: str

    @strawberry.field
    async def author(self, info: Info) -> Optional[Profile]:
        return await info.context["profile_loader"].load(self.author_uid)


# ── Input types ───────────────────────────────────────────────────────────────

@strawberry.input
class CreateCommentInput:
    post_id: strawberry.ID
    body: CommentBody
