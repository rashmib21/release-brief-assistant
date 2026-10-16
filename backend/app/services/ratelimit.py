"""Tiny in-memory sliding-window limiter to protect the LLM API key (single instance only)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from ..config import get_settings

_hits: dict[str, deque] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def limit_analyze(request: Request) -> None:
    limit = get_settings().analyze_rate_limit_per_minute
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail=f"Too many analysis runs. Limit is {limit} per minute.")
    window.append(now)
