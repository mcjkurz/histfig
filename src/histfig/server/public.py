"""Public (read-only) mode: `histfig serve --public`.

Everything that changes figures, documents, prompts or settings is refused;
visitors can only chat. Each visitor is recognised by an anonymous cookie and
sees only their own conversations, which are deleted automatically when they
have not been used for [public] keep_days. Messages are limited per visitor and per
IP address (a script that drops the cookie is a new visitor every time, but not a new IP).

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
    """At most `per_hour` messages per visitor and `per_ip` per IP address in any 60-minute
    window (in memory). A message counts against both, and only if both allow it."""

    SWEEP_EVERY = 1000  # checks between removing visitors and IPs with no recent messages

    def __init__(self, per_hour: int, per_ip: int = 0):
        self.limits = {"visitor": per_hour, "ip": per_ip}
        self.sent: dict[tuple[str, str], deque] = defaultdict(deque)
        self.checks = 0

    def check(self, visitor: str, ip: str | None = None) -> None:
        now = time.monotonic()
        self.checks += 1
        if self.checks % self.SWEEP_EVERY == 0:
            self.sent = defaultdict(deque, {k: w for k, w in self.sent.items() if w and now - w[-1] <= 3600})
        windows = []
        for kind, key in (("visitor", visitor), ("ip", ip)):
            limit = self.limits[kind]
            if limit <= 0 or not key:
                continue
            window = self.sent[(kind, key)]
            while window and now - window[0] > 3600:
                window.popleft()
            if len(window) >= limit:
                wait = int((3600 - (now - window[0])) // 60) + 1
                who = "You have" if kind == "visitor" else "Visitors from your network have"
                raise HTTPException(429, f"{who} sent {limit} messages in the last hour. "
                                         f"Please try again in about {wait} minutes.")
            windows.append(window)
        for window in windows:
            window.append(now)


def delete_old_visitor_conversations(db: Database, keep_days: int) -> int:
    """Remove visitors' conversations unused for keep_days (the owner's are never touched)."""
    if keep_days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
    return db.execute("DELETE FROM conversations WHERE visitor IS NOT NULL AND updated_at < ?", (cutoff,))
