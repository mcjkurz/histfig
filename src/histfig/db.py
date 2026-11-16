"""SQLite storage. One file holds figures, documents, chunks (with vectors) and chats.

A fresh connection is opened per unit of work; SQLite in WAL mode handles the
light concurrency of a single-user app (web requests + one ingestion worker).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from histfig.prompts import SYSTEM_PROMPT

SCHEMA = """
CREATE TABLE figures (
    id                 INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    persona            TEXT NOT NULL DEFAULT '',
    birth_year         TEXT NOT NULL DEFAULT '',   -- whole number, negative = BC; '' = unknown
    death_year         TEXT NOT NULL DEFAULT '',
    image              TEXT,
    embed_model        TEXT,          -- "provider:model" the vectors were made with
    embed_dim          INTEGER,
    created_at         TEXT NOT NULL,
    -- embedding usage reported by the provider: running total, including rebuilds
    embed_tokens_total INTEGER NOT NULL DEFAULT 0,
    embed_cost_total   REAL NOT NULL DEFAULT 0,
    default_prompt_id  INTEGER REFERENCES prompts(id) ON DELETE SET NULL
);

CREATE TABLE documents (
    id             INTEGER PRIMARY KEY,
    figure_id      INTEGER NOT NULL REFERENCES figures(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL,
    file_type      TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    path           TEXT NOT NULL,
    char_count     INTEGER NOT NULL DEFAULT 0,
    chunk_count    INTEGER NOT NULL DEFAULT 0,
    embedded_count INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | ready | error
    error          TEXT,
    created_at     TEXT NOT NULL,
    embed_tokens   INTEGER NOT NULL DEFAULT 0,       -- usage for the document's current vectors
    embed_cost     REAL NOT NULL DEFAULT 0,          -- USD, when the provider reports it
    UNIQUE (figure_id, sha256)
);

CREATE TABLE chunks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    figure_id   INTEGER NOT NULL,
    idx         INTEGER NOT NULL,
    text        TEXT NOT NULL,
    start_char  INTEGER NOT NULL,
    end_char    INTEGER NOT NULL,
    tokens      TEXT NOT NULL,    -- JSON list for BM25
    embedding   BLOB              -- float32, unit-normalised; NULL until embedded
);
CREATE INDEX chunks_figure ON chunks(figure_id);
CREATE INDEX chunks_document ON chunks(document_id);

-- Named system prompts. figure_id NULL = a general prompt usable with every figure; exactly
-- one general prompt has is_default = 1. Conversations and figures point at a prompt; when
-- it is deleted they fall back to the default.
CREATE TABLE prompts (
    id          INTEGER PRIMARY KEY,
    figure_id   INTEGER REFERENCES figures(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    text        TEXT NOT NULL,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX prompts_figure ON prompts(figure_id);

CREATE TABLE conversations (
    id          INTEGER PRIMARY KEY,
    figure_id   INTEGER NOT NULL REFERENCES figures(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    prompt_id   INTEGER REFERENCES prompts(id) ON DELETE SET NULL,
    visitor     TEXT              -- public mode: an anonymous visitor's; NULL = the owner's
);
CREATE INDEX conversations_visitor ON conversations(figure_id, visitor);

CREATE TABLE messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,   -- user | assistant
    content         TEXT NOT NULL,
    sources         TEXT,            -- JSON list of retrieved passages
    created_at      TEXT NOT NULL,
    steps           TEXT             -- agent search: JSON list of what was looked up
);
CREATE INDEX messages_conversation ON messages(conversation_id);
"""
# PRAGMA user_version of a database with this schema. (Earlier development versions built it
# in steps 1-5; databases from those are not upgraded.) If the schema ever changes, raise this
# and turn the difference into an upgrade step in Database.prepare().
SCHEMA_VERSION = 6


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._gate = threading.Condition()  # see exclusive()
        self._active = 0
        self._paused = False
        self.prepare()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def connect(self):
        """Yield a connection; commit on success, roll back on error."""
        with self._gate:
            while self._paused:
                self._gate.wait()
            self._active += 1
        try:
            conn = self._open()
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
        finally:
            with self._gate:
                self._active -= 1
                self._gate.notify_all()

    @contextmanager
    def exclusive(self):
        """Wait until no connection is open, and keep new ones waiting meanwhile: for replacing
        the database file (restoring a backup). Use self._open() inside, not connect()."""
        with self._gate:
            self._paused = True
            while self._active:
                self._gate.wait()
        try:
            yield
        finally:
            with self._gate:
                self._paused = False
                self._gate.notify_all()

    def prepare(self) -> None:
        """Create the tables in a new database; check that an existing one is current."""
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version != 0:
                raise RuntimeError(
                    f"{self.path} was made by a different version of HistFig (database version "
                    f"{version}, expected {SCHEMA_VERSION}). Start with an empty data folder "
                    "(--data-dir), or use the HistFig version that made it.")
            conn.executescript(SCHEMA)
            ts = now()
            conn.execute("INSERT INTO prompts (figure_id, name, text, is_default, created_at, updated_at) "
                         "VALUES (NULL, 'Default', ?, 1, ?, ?)", (SYSTEM_PROMPT, ts, ts))
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # Small helpers -----------------------------------------------------

    def one(self, sql: str, params=()) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, params=()) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def execute(self, sql: str, params=()) -> int:
        """Run a statement; return lastrowid (for INSERT) or rowcount."""
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount
