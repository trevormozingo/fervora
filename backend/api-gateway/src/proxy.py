"""Reverse proxy — forwards requests to backend services."""

import os

from fastapi import APIRouter, Request, Response

PROFILE_SERVICE_URL = os.getenv("PROFILE_SERVICE_URL", "http://profile-service:8000")

# Routes that get proxied to profile-service
_PROFILE_PREFIXES = ("/profiles", "/posts", "/events", "/follows")

proxy_router = APIRouter()


@proxy_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(request: Request, path: str):
    target_url = _resolve_target(path)
    if target_url is None:
        return Response(status_code=404, content="Not found")

    client = request.app.state.http_client

    # Forward headers (drop host)
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    body = await request.body()

    response = await client.request(
        method=request.method,
        url=target_url,
        headers=headers,
        content=body,
        params=request.query_params,
    )

    # Strip hop-by-hop headers
    excluded = {"transfer-encoding", "connection", "keep-alive"}
    resp_headers = {k: v for k, v in response.headers.items() if k.lower() not in excluded}

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=resp_headers,
    )


def _resolve_target(path: str) -> str | None:
    """Map a request path to the appropriate backend service URL."""
    full_path = f"/{path}"
    for prefix in _PROFILE_PREFIXES:
        if full_path == prefix or full_path.startswith(prefix + "/"):
            return f"{PROFILE_SERVICE_URL}{full_path}"
    return None
