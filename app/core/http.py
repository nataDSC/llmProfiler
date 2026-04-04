import httpx
from typing import AsyncGenerator

# We use a global variable to hold the singleton client
_client: httpx.AsyncClient | None = None

async def get_http_client() -> httpx.AsyncClient:
    """
    FastAPI dependency to provide the shared HTTP client.
    """
    global _client
    if _client is None or _client.is_closed:
        # Initialize with production-grade limits
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(
                max_keepalive_connections=50, # Keep 50 connections warm
                max_connections=100           # Allow up to 100 concurrent requests
            ),
            # This ensures we don't follow redirects for security
            follow_redirects=False 
        )
    return _client

async def close_http_client():
    """Closes the shared client during application shutdown."""
    global _client
    if _client:
        await _client.aclose()
        _client = None

