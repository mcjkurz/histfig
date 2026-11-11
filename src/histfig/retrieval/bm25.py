"""Small BM25 with an inverted index.

Uses the Lucene IDF ``log(1 + (N - n + 0.5) / (n + 0.5))``, which stays positive
even for words that occur in most passages — common in a single author's corpus,
where classic Okapi IDF turns negative and ranks matches *below* non-matches.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(corpus)
        self.doc_len = np.array([len(d) for d in corpus], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n and self.doc_len.sum() else 1.0
        postings: dict[str, tuple[list[int], list[int]]] = defaultdict(lambda: ([], []))
        for i, doc in enumerate(corpus):
            for term, tf in Counter(doc).items():
                docs, tfs = postings[term]
                docs.append(i)
                tfs.append(tf)
        self.postings = {
            t: (np.array(d, dtype=np.int64), np.array(f, dtype=np.float32))
            for t, (d, f) in postings.items()
        }

    def idf(self, term: str) -> float:
        n = len(self.postings[term][0]) if term in self.postings else 0
        return math.log(1 + (self.n - n + 0.5) / (n + 0.5))

    def get_scores(self, query: list[str]) -> np.ndarray:
        scores = np.zeros(self.n, dtype=np.float32)
        for term in set(query):
            if term not in self.postings:
                continue
            docs, tf = self.postings[term]
            norm = self.k1 * (1 - self.b + self.b * self.doc_len[docs] / self.avgdl)
            scores[docs] += self.idf(term) * tf * (self.k1 + 1) / (tf + norm)
        return scores
