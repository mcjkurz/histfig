"""Prompt templates.

The system prompt is chosen per conversation from the prompts stored in the
database (editable in the app). SYSTEM_PROMPT below is the built-in text: it
seeds the "Default" prompt and is what "Reset to built-in" restores.

System prompts may use the placeholders {name}, {years}, {description} and
{persona}; any other braces are left exactly as written.
"""

import re

PLACEHOLDERS = ("name", "years", "description", "persona")
_PLACEHOLDER_RE = re.compile(r"\{(" + "|".join(PLACEHOLDERS) + r")\}")

SYSTEM_PROMPT = """{persona}

You are {name}. Answer as {name} would: in their voice, with their opinions and \
knowledge, drawing on the passages from their writings when they are relevant. \
Write as if speaking in a conversation — no tables, lists or headings. Keep the \
length proportional to the question.

Always reply in the language the user writes in, even when the passages are in \
another language. If the passages do not cover the question, answer in character \
from general knowledge of {name}'s life and views, without inventing quotations."""

DEFAULT_PERSONA = "You are {name}{years}."

RAG_USER_MESSAGE = """Passages from your writings that may be relevant:

{passages}

When a sentence or paragraph of your answer draws on a passage, put its number in \
square brackets right after it, e.g. [2] or [1, 3]. Add nothing for parts that \
don't come from the passages.

---
Question: {message}"""

PASSAGE = "[{n}] ({filename}, part {chunk})\n{text}"


def _year(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def years(birth: str, death: str) -> str:
    """" (1881–1936)", " (551–479 BC)", " (4 BC–AD 65)"; negative years are BC."""
    b, d = _year(birth), _year(death)
    if b is None and d is None:
        return ""
    if b is not None and d is not None and b < 0 and d < 0:
        return f" ({-b}–{-d} BC)"
    bc = (b or 0) < 0 or (d or 0) < 0

    def one(y):
        return "?" if y is None else f"{-y} BC" if y < 0 else f"AD {y}" if bc else str(y)

    return f" ({one(b)}–{one(d)})"


def render(template: str, figure: dict) -> str:
    """Fill in the known placeholders; leave everything else untouched."""
    y = years(figure.get("birth_year", ""), figure.get("death_year", ""))
    persona = (figure.get("persona") or "").strip() or DEFAULT_PERSONA.format(
        name=figure["name"], years=y
    )
    values = {
        "name": figure["name"],
        "years": y.strip()[1:-1] if y else "",  # "1881–1936", without the brackets
        "description": (figure.get("description") or "").strip(),
        "persona": persona,
    }
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def system_prompt(figure: dict, template: str | None = None) -> str:
    return render(template or SYSTEM_PROMPT, figure)


def user_message(message: str, hits: list[dict]) -> str:
    if not hits:
        return message
    passages = "\n\n".join(
        PASSAGE.format(n=i, filename=h["filename"], chunk=h["chunk"] + 1, text=h["text"])
        for i, h in enumerate(hits, start=1)
    )
    return RAG_USER_MESSAGE.format(passages=passages, message=message)
