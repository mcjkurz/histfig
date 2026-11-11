"""Chunking that prefers paragraph and sentence boundaries.

Works for both CJK (no spaces, 。！？) and space-separated languages. Sizes are
measured in Chinese-character equivalents: a Chinese, Japanese or Korean character
counts as 1, any other character (letters, spaces, punctuation) as 1/3, since a
character carries about as much as three English letters (and costs about as many
model tokens). So a size of 1000 is ~1000 Chinese characters or ~500 English words.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from itertools import accumulate
from dataclasses import dataclass

STRONG_END = "。！？；…\n"  # always a sentence end
WEAK_END = ".!?;"  # a sentence end only when followed by space/quote/end
CLOSERS = "\"'”’」』）)]】"
SOFT_BREAK = " ，,、：:\t"

# CJK characters, kana, hangul and full-width punctuation
DENSE = re.compile(r"[\u1100-\u11ff\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef\U00020000-\U0003ffff]")
OTHER_PER_UNIT = 3  # other characters per Chinese-character equivalent


def measure(text: str) -> float:
    """Size of a text in Chinese-character equivalents."""
    dense = len(DENSE.findall(text))
    return dense + (len(text) - dense) / OTHER_PER_UNIT


@dataclass
class Chunk:
    text: str
    start: int
    end: int


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t　\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_sentence_end(text: str, i: int) -> bool:
    c = text[i]
    if c in STRONG_END:
        return True
    if c in WEAK_END:
        nxt = text[i + 1] if i + 1 < len(text) else " "
        return nxt.isspace() or nxt in CLOSERS
    return False


def _after_closers(text: str, i: int, limit: int) -> int:
    while i < limit and text[i] in CLOSERS:
        i += 1
    return i


def _break_before(text: str, lo: int, hi: int) -> int:
    """Best place to end a chunk within (lo, hi]; returns hi when nothing is found."""
    para = text.rfind("\n\n", lo, hi)
    if para != -1:
        return para
    for i in range(hi - 1, lo - 1, -1):
        if _is_sentence_end(text, i):
            return _after_closers(text, i + 1, hi)
    for i in range(hi - 1, lo - 1, -1):
        if text[i] in SOFT_BREAK:
            return i + 1
    return hi


def _start_after(text: str, lo: int, hi: int) -> int:
    """Start the overlap at a sentence beginning within [lo, hi) if possible."""
    for i in range(lo, hi):
        if i > 0 and _is_sentence_end(text, i - 1):
            return _after_closers(text, i, hi)
    for i in range(lo, hi):
        if i > 0 and text[i - 1] in SOFT_BREAK:
            return i
    return lo


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[Chunk]:
    """Split into passages of at most `size` (and overlapping by about `overlap`)
    Chinese-character equivalents; see measure()."""
    text = normalise(text)
    n = len(text)
    # cum[i] = size of text[:i], in thirds of a unit (whole numbers, so no rounding trouble)
    cum = [0, *accumulate(OTHER_PER_UNIT if DENSE.match(c) else 1 for c in text)]
    size, overlap = size * OTHER_PER_UNIT, overlap * OTHER_PER_UNIT

    def at(i: int, units: int) -> int:
        """The furthest position j with size(text[i:j]) <= units (at least i + 1)."""
        return max(i + 1, bisect_right(cum, cum[i] + units) - 1)

    chunks: list[Chunk] = []
    start = 0
    while start < n:
        limit = at(start, size)
        end = n if limit >= n else _break_before(text, at(start, size // 2), limit)
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(piece, start, end))
        if end >= n:
            break
        nxt = end
        if overlap > 0:
            back = bisect_right(cum, cum[end] - overlap)  # first position within `overlap` before end
            nxt = _start_after(text, max(back, start + 1), end)
        nxt = max(nxt, start + 1)
        while nxt < n and text[nxt].isspace():
            nxt += 1
        start = nxt
    return chunks
