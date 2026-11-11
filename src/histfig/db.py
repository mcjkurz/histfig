"""SQLite storage. One file holds figures, documents, chunks (with vectors) and chats.

A fresh connection is opened per unit of work; SQLite in WAL mode handles the
light concurrency of a single-user app (web requests + one ingestion worker).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from histfig.prompts import SYSTEM_PROMPT

SCHEMA_V1 = """
CREATE TABLE figures (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    persona       TEXT NOT NULL DEFAULT '',
    birth_year    TEXT NOT NULL DEFAULT '',
    death_year    TEXT NOT NULL DEFAULT '',
    image         TEXT,
    embed_model   TEXT,          -- "provider:model" the vectors were made with
    embed_dim     INTEGER,
    created_at    TEXT NOT NULL
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

CREATE TABLE conversations (
    id          INTEGER PRIMARY KEY,
    figure_id   INTEGER NOT NULL REFERENCES figures(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,   -- user | assistant
    content         TEXT NOT NULL,
    sources         TEXT,            -- JSON list of retrieved passages
    created_at      TEXT NOT NULL
);
CREATE INDEX messages_conversation ON messages(conversation_id);
"""

# Embedding usage as reported by the provider (tokens, and cost in USD when known).
# documents.* = for the document's current vectors; figures.* = running total incl. rebuilds.
SCHEMA_V2 = """
ALTER TABLE documents ADD COLUMN embed_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN embed_cost REAL NOT NULL DEFAULT 0;
ALTER TABLE figures ADD COLUMN embed_tokens_total INTEGER NOT NULL DEFAULT 0;
ALTER TABLE figures ADD COLUMN embed_cost_total REAL NOT NULL DEFAULT 0;
"""

# Named system prompts. figure_id NULL = a general prompt usable with every figure;
# exactly one general prompt has is_default = 1. Conversations and figures point
# at a prompt; when it is deleted they fall back to the default.
SCHEMA_V3 = """
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
INSERT INTO prompts (figure_id, name, text, is_default, created_at, updated_at)
VALUES (NULL, 'Default', '""" + SYSTEM_PROMPT.replace("'", "''") + """', 1,
        strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'), strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));
ALTER TABLE conversations ADD COLUMN prompt_id INTEGER REFERENCES prompts(id) ON DELETE SET NULL;
ALTER TABLE figures ADD COLUMN default_prompt_id INTEGER REFERENCES prompts(id) ON DELETE SET NULL;
"""

# Public mode: conversations started by anonymous visitors (NULL = the owner's).
SCHEMA_V4 = """
ALTER TABLE conversations ADD COLUMN visitor TEXT;
CREATE INDEX conversations_visitor ON conversations(figure_id, visitor);
"""

# Agent search: what was looked up for an answer (JSON list of short texts).
SCHEMA_V5 = """
ALTER TABLE messages ADD COLUMN steps TEXT;
"""



def retokenize(conn: sqlite3.Connection) -> None:
    """Recompute the stored keywords of every passage after the tokenizer changed
    (no new embeddings needed). V6: English stemming and word pairs."""
    from histfig.retrieval.tokenize import tokenize

    rows = conn.execute("SELECT id, text FROM chunks").fetchall()
    if len(rows) > 500:
        print(f"Updating the search keywords of {len(rows)} passages (once, a few seconds)…", flush=True)
    conn.executemany("UPDATE chunks SET tokens=? WHERE id=?",
                     [(json.dumps(tokenize(r["text"]), ensure_ascii=False), r["id"]) for r in rows])


# Append new migrations here (an SQL script or a function); index + 1 == schema version.
MIGRATIONS = [SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, retokenize]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

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
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
                if callable(script):
                    script(conn)
                else:
                    conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {i}")

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
