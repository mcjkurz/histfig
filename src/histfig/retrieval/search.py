"""Hybrid retrieval: cosine similarity over stored vectors + BM25, fused with RRF.

Each figure's index (vector matrix + BM25) is built from SQLite on first use and
cached in memory until that figure's documents change.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

import numpy as np
from histfig.retrieval.bm25 import BM25

from histfig.config import RetrievalConfig
from histfig.db import Database
from histfig.retrieval.tokenize import tokenize


@dataclass
class FigureIndex:
    chunk_ids: np.ndarray  # (n,)
    vectors: np.ndarray | None  # (n, dim) or None if any chunk lacks a vector
    bm25: BM25 | None


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    filename: str
    idx: int
    text: str
    similarity: float | None
    bm25: float | None
    score: float

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "chunk": self.idx,
            "text": self.text,
            "similarity": None if self.similarity is None else round(self.similarity, 4),
            "bm25": None if self.bm25 is None else round(self.bm25, 3),
            "score": round(self.score, 5),
        }


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


class SearchIndex:
    def __init__(self, db: Database):
        self.db = db
        self._cache: dict[int, FigureIndex] = {}
        self._lock = threading.Lock()

    def invalidate(self, figure_id: int) -> None:
        with self._lock:
            self._cache.pop(figure_id, None)

    def _build(self, figure_id: int) -> FigureIndex:
        rows = self.db.all(
            """SELECT c.id, c.tokens, c.embedding FROM chunks c
               JOIN documents d ON d.id = c.document_id
               WHERE c.figure_id = ? AND d.status = 'ready' ORDER BY c.id""",
            (figure_id,),
        )
        ids = np.array([r["id"] for r in rows], dtype=np.int64)
        tokens = [json.loads(r["tokens"]) for r in rows]
        bm25 = BM25(tokens) if rows and any(tokens) else None
        vectors = None
        if rows and all(r["embedding"] is not None for r in rows):
            vectors = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
        return FigureIndex(ids, vectors, bm25)

    def get(self, figure_id: int) -> FigureIndex:
        with self._lock:
            index = self._cache.get(figure_id)
        if index is None:
            index = self._build(figure_id)
            with self._lock:
                self._cache[figure_id] = index
        return index

    def search(
        self,
        figure_id: int,
        query: str,
        query_vector: np.ndarray | None,
        cfg: RetrievalConfig,
        top_k: int | None = None,
    ) -> list[Hit]:
        top_k = top_k or cfg.top_k
        index = self.get(figure_id)
        n = len(index.chunk_ids)
        if n == 0:
            return []
        m = min(cfg.candidates, n)

        sims = None
        vector_rank: list[int] = []
        if query_vector is not None and index.vectors is not None:
            if index.vectors.shape[1] == query_vector.shape[0]:
                sims = index.vectors @ query_vector
                vector_rank = list(np.argsort(-sims)[:m])

        bm25_scores = None
        bm25_rank: list[int] = []
        q_tokens = tokenize(query)
        if index.bm25 is not None and q_tokens:
            bm25_scores = index.bm25.get_scores(q_tokens)
            order = np.argsort(-bm25_scores)[:m]
            bm25_rank = [int(i) for i in order if bm25_scores[i] > 0]

        fused = rrf([[int(i) for i in vector_rank], bm25_rank], cfg.rrf_k)
        in_bm25 = set(bm25_rank)

        def keep(i: int) -> bool:
            if sims is None:
                return True
            # Keyword matches get a looser similarity floor than vector-only hits.
            floor = cfg.min_similarity / 2 if i in in_bm25 else cfg.min_similarity
            return float(sims[i]) >= floor

        best = [i for i in sorted(fused, key=fused.get, reverse=True) if keep(i)][:top_k]
        if not best:
            return []

        id_list = [int(index.chunk_ids[i]) for i in best]
        placeholders = ",".join("?" * len(id_list))
        rows = self.db.all(
            f"""SELECT c.id, c.document_id, c.idx, c.text, d.filename FROM chunks c
                JOIN documents d ON d.id = c.document_id WHERE c.id IN ({placeholders})""",
            id_list,
        )
        by_id = {r["id"]: r for r in rows}
        hits = []
        for i in best:
            row = by_id.get(int(index.chunk_ids[i]))
            if row is None:  # deleted meanwhile
                continue
            hits.append(
                Hit(
                    chunk_id=row["id"],
                    document_id=row["document_id"],
                    filename=row["filename"],
                    idx=row["idx"],
                    text=row["text"],
                    similarity=None if sims is None else float(sims[i]),
                    bm25=None if bm25_scores is None else float(bm25_scores[i]),
                    score=fused[i],
                )
            )
        return hits
