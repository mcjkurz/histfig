"""Tokenisation for BM25 keyword search.

jieba splits Chinese into words (and other languages at spaces and punctuation).
English words are stemmed (rivers → river, flows → flow), and pairs of neighbouring
words are added as phrases (iron_house, 铁屋_呐喊), so passages that share a whole
phrase with the question score higher.

Changing this changes the stored keywords: add a migration that runs
db.retokenize() again, so existing passages get the new keywords.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from importlib import resources

import jieba
import snowballstemmer

jieba.setLogLevel(logging.WARNING)

_WORD = re.compile(r"\w", re.UNICODE)
_ENGLISH = re.compile(r"[a-z]+(?:'[a-z]+)?")
_stem = snowballstemmer.stemmer("english").stemWord


@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    words: set[str] = set()
    folder = resources.files("histfig") / "resources" / "stopwords"
    for entry in folder.iterdir():
        if entry.name.endswith(".txt"):
            for line in entry.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    words.add(line.strip().lower())
    return frozenset(words)


def _word(token: str, stop: frozenset[str]) -> str | None:
    """The keyword for one jieba token, or None if it isn't one (stopword, punctuation…)."""
    token = token.strip()
    if not token or len(token) > 24 or token in stop or not _WORD.search(token):
        return None
    if token.isdigit() and len(token) > 4:
        return None
    if _ENGLISH.fullmatch(token):
        if len(token) == 1:  # "s" from "Mao's", "t" from "don't"
            return None
        return _stem(token)
    return token


def tokenize(text: str) -> list[str]:
    """Keywords of a text: words, then the pairs of neighbouring words."""
    stop = stopwords()
    words = [_word(t, stop) for t in jieba.lcut(text.lower()) if not t.isspace()]
    unigrams = [w for w in words if w]
    # A stopword or punctuation between two words breaks the pair ("house of cards" → no pair)
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:]) if a and b]
    return unigrams + bigrams
