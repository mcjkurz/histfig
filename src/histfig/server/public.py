"""Public (read-only) mode: `histfig serve --public`.

Everything that changes figures, documents, prompts or settings is refused;
visitors can only chat. Each visitor is recognised by an anonymous cookie and
sees only their own conversations, which are deleted automatically when they
have not been used for [public] keep_days. Messages are limited per visitor.

When the server is not public, none of this applies: visitor is None, and the
owner's conversations are the ones without a visitor.
"""

from __future__ import annotations

import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from histfig.db import Database

COOKIE = "histfig_visitor"
_VALID = re.compile(r"[0-9a-f]{32}")


def is_public(request: Request) -> bool:
    return request.app.state.hf.public


def editable(request: Request) -> None:
    """Dependency for every endpoint that changes shared things."""
    if is_public(request):
        raise HTTPException(403, "This HistFig is read-only: you can chat, but not change figures or settings.")


def current_visitor(request: Request) -> str | None:
    """The visitor's anonymous ID in public mode; None for the owner."""
    return getattr(request.state, "visitor", None) if is_public(request) else None


async def visitor_cookie(request: Request, call_next):
    """Middleware (public mode only): give each browser a stable anonymous ID."""
    vid = request.cookies.get(COOKIE, "")
    new = not _VALID.fullmatch(vid)
    if new:
        vid = secrets.token_hex(16)
    request.state.visitor = vid
    response = await call_next(request)
    if new:
        response.set_cookie(COOKIE, vid, max_age=365 * 86400, httponly=True, samesite="lax")
    return response


class RateLimiter:
    """At most `per_hour` messages per visitor in any 60-minute window (in memory)."""

    def __init__(self, per_hour: int):
        self.per_hour = per_hour
        self.sent: dict[str, deque] = defaultdict(deque)

    def check(self, visitor: str) -> None:
        if self.per_hour <= 0:
            return
        now, window = time.monotonic(), self.sent[visitor]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= self.per_hour:
            wait = int((3600 - (now - window[0])) // 60) + 1
            raise HTTPException(429, f"You have sent {self.per_hour} messages in the last hour. "
                                     f"Please try again in about {wait} minutes.")
        window.append(now)


def delete_old_visitor_conversations(db: Database, keep_days: int) -> int:
    """Remove visitors' conversations unused for keep_days (the owner's are never touched)."""
    if keep_days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
    return db.execute("DELETE FROM conversations WHERE visitor IS NOT NULL AND updated_at < ?", (cutoff,))
