"""Cleaning what people type into forms (figure names, descriptions, years, titles).

Lenient about form, strict about meaning: any language or script is fine, stray
whitespace and invisible control characters are removed, years can be written in
many common ways ("551 BC", "公元前551年", "c. 1881", "１８８１"), and anything that
can't be understood is refused with a message that says what to write instead.
"""

from __future__ import annotations

import re
import unicodedata

# Control characters (except tab and newline), and the Unicode "format" characters
# that are invisible but break text: zero-width spaces, direction overrides, BOM…
_INVISIBLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤﻿]")


def clean_text(value, max_length: int, label: str) -> str:
    """Multi-line text (descriptions, persona): may be empty."""
    text = _INVISIBLE.sub("", "" if value is None else str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > max_length:
        raise ValueError(f"{label} is too long ({len(text)} characters; at most {max_length}).")
    return text


def clean_line(value, max_length: int, label: str, required: bool = False) -> str:
    """One line (names, titles): whitespace and line breaks become single spaces."""
    text = " ".join(_INVISIBLE.sub("", "" if value is None else str(value)).split())
    if required and not text:
        raise ValueError(f"Please enter a {label.lower()}.")
    if len(text) > max_length:
        raise ValueError(f"{label} is too long ({len(text)} characters; at most {max_length}).")
    return text


# Ways of writing "unknown"
_UNKNOWN = {"", "?", "unknown", "n/a", "na", "-", "不详", "不詳", "未知"}
# [about] [era] [sign] number [年] [era] [?]  e.g. "c. 551 BC", "公元前551年", "AD 65", "1881?"
_YEAR = re.compile(r"""
    (?:c\.?|ca\.?|circa|about|approx\.?|大约|大約|约|約)?\s*
    (?P<before>公元前|紀元前|纪元前|前|公元|西元|ad|a\.d\.)?\s*
    (?P<sign>[+-])?\s*(?P<number>[0-9]{1,4})\s*年?\s*
    (?P<after>bce|b\.c\.e\.|bc|b\.c\.|ce|c\.e\.|ad|a\.d\.)?\s*\??
""", re.VERBOSE)
YEAR_HELP = "Write a year like 1881, 551 BC (or -551, 公元前551), or leave it empty if unknown."


def parse_year(value) -> str:
    """A year as a whole number in text ("-551" = 551 BC), or "" when unknown.
    Raises ValueError for anything that isn't recognisably one year."""
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))  # full-width → ASCII
    text = _INVISIBLE.sub("", text).strip().lower().replace("−", "-").replace("–", "-")
    if text in _UNKNOWN or set(text) <= {"?"}:
        return ""
    m = _YEAR.fullmatch(text)
    if m is None:
        raise ValueError(f"“{str(value).strip()[:30]}” is not a year. {YEAR_HELP}")
    bc = (m["sign"] == "-" or m["before"] in ("公元前", "紀元前", "纪元前", "前")
          or m["after"] in ("bce", "b.c.e.", "bc", "b.c."))
    number = int(m["number"])
    return str(-number if bc and number else number)
