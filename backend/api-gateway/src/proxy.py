"""
Reverse proxy for forwarding requests to backend services.

The gateway strips the service prefix (e.g. /profile) and forwards
the remaining path to the appropriate service URL, injecting the
X-User-Id header from the authenticated Firebase UID.
"""

import os

import httpx

PROFILE_SERVICE_URL = os.getenv("PROFILE_SERVICE_URL", "http://localhost:8000")

# Shared async HTTP client — created at module level, reused across requests.
_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    """Return (and lazily create) the shared async HTTP client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client():
    """Close the shared async HTTP client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# Map of service prefix → base URL
SERVICE_MAP: dict[str, str] = {
    "profile": PROFILE_SERVICE_URL,
    "posts": PROFILE_SERVICE_URL,
    "follows": PROFILE_SERVICE_URL,
    "feed": PROFILE_SERVICE_URL,
    "events": PROFILE_SERVICE_URL,
}


async def forward_request(
    service: str,
    path: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
    query_string: str = "",
) -> httpx.Response:
    """
    Forward an HTTP request to a backend service.

    Args:
        service: Service name (e.g. "profile") — used to look up the base URL.
        path: The remaining path after the service prefix (e.g. "" or "/ironwarrior").
        method: HTTP method (GET, POST, PATCH, DELETE, PUT).
        headers: Headers to forward (including X-User-Id).
        body: Raw request body bytes (for POST/PATCH/PUT).
        query_string: Raw query string to append to the URL.

    Returns:
        The httpx.Response from the backend service.

    Raises:
        ValueError: If the service name is unknown.
    """
    base_url = SERVICE_MAP.get(service)
    if base_url is None:
        raise ValueError(f"Unknown service: {service}")

    url = f"{base_url}/{service}{path}"
    if query_string:
        url = f"{url}?{query_string}"

    # Only forward relevant headers — drop hop-by-hop headers
    forward_headers = {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("host", "connection", "transfer-encoding", "content-length")
    }

    client = await get_client()
    response = await client.request(
        method=method,
        url=url,
        headers=forward_headers,
        content=body,
    )
    return response
