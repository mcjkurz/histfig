"""Background ingestion: extract → chunk → tokenise → embed in batches.

Chunks are written first with ``embedding = NULL`` and filled batch by batch,
so an interrupted job resumes where it stopped when the server restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import numpy as np

from histfig.config import Config
from histfig.db import Database
from histfig.ingest.chunk import chunk_text
from histfig.ingest.extract import extract_text
from histfig.providers.embed import Embedder, Usage
from histfig.retrieval.search import SearchIndex
from histfig.retrieval.tokenize import tokenize

log = logging.getLogger("histfig.ingest")


class JobError(RuntimeError):
    pass


class IngestWorker:
    def __init__(self, db: Database, cfg: Config, embedder: Embedder, index: SearchIndex):
        self.db = db
        self.cfg = cfg
        self.embedder = embedder
        self.index = index
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self._queued: set[int] = set()
        self._task: asyncio.Task | None = None

    # Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="histfig-ingest")
        for row in self.db.all(
            "SELECT id FROM documents WHERE status IN ('pending', 'processing') ORDER BY id"
        ):
            self.enqueue(row["id"])

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def enqueue(self, document_id: int) -> None:
        if document_id not in self._queued:
            self._queued.add(document_id)
            self.queue.put_nowait(document_id)

    async def _run(self) -> None:
        while True:
            doc_id = await self.queue.get()
            try:
                await self.process(doc_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # keep the worker alive whatever happens
                log.exception("Ingestion failed for document %s", doc_id)
                self.db.execute(
                    "UPDATE documents SET status='error', error=? WHERE id=?", (str(e), doc_id)
                )
            finally:
                self._queued.discard(doc_id)

    # Work --------------------------------------------------------------

    async def process(self, doc_id: int) -> None:
        doc = self.db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
        if doc is None or doc["status"] in ("ready", "error"):
            return
        figure_id = doc["figure_id"]
        self._check_model(figure_id)
        self.db.execute("UPDATE documents SET status='processing', error=NULL WHERE id=?", (doc_id,))

        if doc["chunk_count"] == 0:
            await self._chunk(doc)

        batch_size = max(1, self.cfg.embedding.batch_size)
        while True:
            rows = self.db.all(
                "SELECT id, text FROM chunks WHERE document_id=? AND embedding IS NULL "
                "ORDER BY idx LIMIT ?",
                (doc_id, batch_size),
            )
            if not rows:
                break
            if self.db.one("SELECT id FROM documents WHERE id=?", (doc_id,)) is None:
                return  # deleted while we were working
            vectors, usage = await self.embedder.embed_documents_with_usage([r["text"] for r in rows])
            self._store_vectors(figure_id, doc_id, rows, vectors, usage)

        self.db.execute("UPDATE documents SET status='ready' WHERE id=?", (doc_id,))
        self.index.invalidate(figure_id)
        log.info("Document %s (%s) is ready", doc_id, doc["filename"])

    def _check_model(self, figure_id: int) -> None:
        fig = self.db.one("SELECT embed_model FROM figures WHERE id=?", (figure_id,))
        current = self.embedder.model_id
        if fig and fig["embed_model"] and fig["embed_model"] != current:
            if self.db.one(
                "SELECT 1 FROM chunks WHERE figure_id=? AND embedding IS NOT NULL LIMIT 1",
                (figure_id,),
            ) is None:
                # Nothing embedded with the old model is left: just switch.
                self.db.execute(
                    "UPDATE figures SET embed_model=NULL, embed_dim=NULL WHERE id=?", (figure_id,)
                )
                return
            raise JobError(
                f"This figure was embedded with {fig['embed_model']}, but the configured "
                f"model is {current}. Use 'Re-embed all' on the figure page."
            )

    async def _chunk(self, doc: dict) -> None:
        data = Path(doc["path"]).read_bytes()
        cfg = self.cfg.chunking

        def work():
            text = extract_text(data, doc["file_type"])
            chunks = chunk_text(text, cfg.chunk_size, cfg.overlap)
            return text, [(c, tokenize(c.text)) for c in chunks]

        text, chunks = await asyncio.to_thread(work)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id=?", (doc["id"],))
            conn.executemany(
                "INSERT INTO chunks (document_id, figure_id, idx, text, start_char, end_char, tokens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (doc["id"], doc["figure_id"], i, c.text, c.start, c.end,
                     json.dumps(toks, ensure_ascii=False))
                    for i, (c, toks) in enumerate(chunks)
                ],
            )
            conn.execute(
                "UPDATE documents SET char_count=?, chunk_count=?, embedded_count=0 WHERE id=?",
                (len(text), len(chunks), doc["id"]),
            )

    def _store_vectors(self, figure_id: int, doc_id: int, rows: list[dict], vectors: np.ndarray,
                       usage: Usage | None = None):
        usage = usage or Usage()
        dim = int(vectors.shape[1])
        with self.db.connect() as conn:
            fig = conn.execute(
                "SELECT embed_model, embed_dim FROM figures WHERE id=?", (figure_id,)
            ).fetchone()
            if fig is None:
                return  # figure deleted meanwhile
            if fig["embed_model"] is None:
                conn.execute(
                    "UPDATE figures SET embed_model=?, embed_dim=? WHERE id=?",
                    (self.embedder.model_id, dim, figure_id),
                )
            elif fig["embed_dim"] != dim:
                raise JobError(f"Embedding size changed ({fig['embed_dim']} → {dim}).")
            conn.executemany(
                "UPDATE chunks SET embedding=? WHERE id=?",
                [(v.astype(np.float32).tobytes(), r["id"]) for r, v in zip(rows, vectors)],
            )
            conn.execute(
                "UPDATE documents SET embedded_count = "
                "(SELECT COUNT(*) FROM chunks WHERE document_id=? AND embedding IS NOT NULL) "
                "WHERE id=?",
                (doc_id, doc_id),
            )
            conn.execute(
                "UPDATE documents SET embed_tokens = embed_tokens + ?, embed_cost = embed_cost + ? WHERE id=?",
                (usage.tokens, usage.cost, doc_id),
            )
            conn.execute(
                "UPDATE figures SET embed_tokens_total = embed_tokens_total + ?, "
                "embed_cost_total = embed_cost_total + ? WHERE id=?",
                (usage.tokens, usage.cost, figure_id),
            )

    # Re-embedding ------------------------------------------------------

    def rebuild_figure(self, figure_id: int) -> int:
        """Re-chunk and re-embed all documents of a figure with the current settings."""
        with self.db.connect() as conn:
            conn.execute("DELETE FROM chunks WHERE figure_id=?", (figure_id,))
            conn.execute(
                "UPDATE figures SET embed_model=NULL, embed_dim=NULL WHERE id=?", (figure_id,)
            )
            conn.execute(
                "UPDATE documents SET status='pending', error=NULL, chunk_count=0, embedded_count=0, "
                "embed_tokens=0, embed_cost=0 "
                "WHERE figure_id=?",
                (figure_id,),
            )
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM documents WHERE figure_id=? ORDER BY id", (figure_id,)
            )]
        self.index.invalidate(figure_id)
        for doc_id in ids:
            self.enqueue(doc_id)
        return len(ids)
