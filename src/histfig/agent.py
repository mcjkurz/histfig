"""Agent search: the model researches the figure's documents before it answers.

A short tool-calling loop over the OpenAI-compatible API (no framework needed):
the model may search by meaning, look for exact words, read the parts around a
passage, and finally pick the passages to answer from. Calling no tool at all
means the question needs no documents (e.g. a greeting). The answer itself is
written afterwards, by the normal chat code, from the chosen passages.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable

from histfig.providers.chat import ProviderError

MAX_STEPS = 5  # rounds of tool calls before we stop and use what was found
MAX_MATCHES = 10  # passages returned by one find_text

RESEARCH_PROMPT = """You prepare the answer of {name} to the user's last message by \
looking things up in {name}'s writings. {description}

Documents:
{documents}

Tools:
- search: finds passages by meaning (and keywords). Try different wordings, and the \
language of the documents, if the first results don't fit.
- find_text: finds passages containing exact words, e.g. names, titles or a phrase.
- read_around: reads the parts just before and after a passage.
- finish: ends the research with the passages that best support an answer \
(at most {top_k}).

If the message needs nothing from the writings (a greeting, small talk, a question \
about the conversation itself), call no tool and reply "no search needed". Otherwise \
search, judge the results, refine if they are not good enough, then call finish."""


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


TOOLS = [
    _tool("search", "Find passages by meaning and keywords.",
          {"query": {"type": "string", "description": "What to look for"}}, ["query"]),
    _tool("find_text", "Find passages containing exact text (case-insensitive). "
          "Separate alternatives with |, e.g. 阿Q|Ah Q.",
          {"text": {"type": "string"}}, ["text"]),
    _tool("read_around", "Read the parts just before and after a passage.",
          {"passage": {"type": "string", "description": "Passage id, e.g. P12"}}, ["passage"]),
    _tool("finish", "End the research with the passages to answer from (none if nothing fits).",
          {"passages": {"type": "array", "items": {"type": "string"},
                        "description": "Passage ids, best first, e.g. [\"P12\", \"P40\"]"}}, ["passages"]),
]

Search = Callable[[str, int], Awaitable[tuple[list[dict], str | None]]]
PASSAGE_SQL = """SELECT c.id, c.document_id, c.idx, c.text, d.filename FROM chunks c
                 JOIN documents d ON d.id = c.document_id WHERE d.status = 'ready' AND c.figure_id = ?"""


def _hit(row) -> dict:
    """The same shape as retrieval.search.Hit.to_dict(), so the Sources panel shows it."""
    return {"chunk_id": row["id"], "document_id": row["document_id"], "filename": row["filename"],
            "chunk": row["idx"], "text": row["text"], "similarity": None, "bm25": None, "score": 0}


def _show(hits: list[dict]) -> str:
    return "\n\n".join(f"P{h['chunk_id']} ({h['filename']}, part {h['chunk'] + 1}):\n{h['text']}"
                       for h in hits) or "No passages found."


def _ids(values) -> list[int]:
    """Passage ids as the model wrote them: "P12", "12", 12 or "P12, P40"."""
    if not isinstance(values, list):
        values = [values]
    return [int(n) for v in values for n in re.findall(r"\d+", str(v))]


def find_text(db, figure_id: int, text: str) -> tuple[list[dict], int]:
    """Passages containing any of the |-separated alternatives; (first matches, total)."""
    words = [w.strip().lower() for w in text.split("|") if w.strip()][:10]
    if not words:
        return [], 0
    matches = [r for r in db.all(PASSAGE_SQL + " ORDER BY d.filename, c.idx", (figure_id,))
               if any(w in r["text"].lower() for w in words)]
    return [_hit(r) for r in matches[:MAX_MATCHES]], len(matches)


def read_around(db, figure_id: int, chunk_id: int, before: int = 1, after: int = 1) -> list[dict]:
    row = db.one(PASSAGE_SQL + " AND c.id = ?", (figure_id, chunk_id))
    if row is None:
        return []
    rows = db.all(PASSAGE_SQL + " AND c.document_id = ? AND c.idx BETWEEN ? AND ? ORDER BY c.idx",
                  (figure_id, row["document_id"], row["idx"] - before, row["idx"] + after))
    return [_hit(r) for r in rows]


def _documents(db, figure_id: int) -> str:
    docs = db.all("SELECT filename, chunk_count FROM documents WHERE figure_id=? AND status='ready' "
                  "ORDER BY filename", (figure_id,))
    lines = [f"- {d['filename']} ({d['chunk_count']} parts)" for d in docs[:50]]
    if len(docs) > 50:
        lines.append(f"- … and {len(docs) - 50} more")
    return "\n".join(lines) or "(none)"


async def research(chat, db, fig: dict, question: str, history: list[dict], model: str,
                   top_k: int, search: Search) -> AsyncIterator[tuple[str, object]]:
    """Yields ("step", text) and ("warning", text) while researching, and finally
    ("hits", passages to answer from). Raises ProviderError if the very first call
    fails (e.g. the model can't use tools), so the caller can fall back to a simple search."""
    system = RESEARCH_PROMPT.format(name=fig["name"], description=(fig.get("description") or "").strip(),
                                    documents=_documents(db, fig["id"]), top_k=top_k)
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": question}]
    seen: dict[int, dict] = {}  # every passage shown to the model, in the order found
    chosen: list[int] | None = None
    warned = False

    for step in range(MAX_STEPS):
        try:
            reply = await chat.call_tools(messages, TOOLS, model)
        except ProviderError:
            if step == 0:
                raise
            break  # a later step failed: answer from what was found so far
        calls = reply.get("tool_calls") or []
        if not calls:
            break
        messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = call.get("function") or {}
            name, args = fn.get("name"), fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}

            if name == "finish":
                chosen = _ids(args.get("passages", []))
                result = "Done."
            elif name == "search" and str(args.get("query", "")).strip():
                query = str(args["query"]).strip()
                hits, warning = await search(query, top_k)
                if warning and not warned:
                    warned = True
                    yield "warning", warning
                yield "step", f"Searched “{query}” · {len(hits)} found"
                result = _show(hits)
            elif name == "find_text" and str(args.get("text", "")).strip():
                text = str(args["text"]).strip()
                hits, total = find_text(db, fig["id"], text)
                yield "step", f"Looked for “{text}” · {total} found"
                result = _show(hits) + (f"\n\n({total - len(hits)} more matches not shown)" if total > len(hits) else "")
            elif name == "read_around" and _ids(args.get("passage")):
                pid = _ids(args["passage"])[0]
                hits = read_around(db, fig["id"], pid)
                where = seen.get(pid) or next((h for h in hits if h["chunk_id"] == pid), None)
                yield "step", f"Read around {where['filename']}, part {where['chunk'] + 1}" if where \
                    else f"Read around P{pid} · not found"
                result = _show(hits)
            else:
                hits, result = [], f"Unknown tool or missing argument: {name}"
            if name != "finish":
                for h in hits:
                    seen.setdefault(h["chunk_id"], h)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
        if chosen is not None:
            break

    if chosen is None:  # stopped without choosing: the passages found, first found first
        yield "hits", list(seen.values())[:top_k]
    else:
        yield "hits", [seen[i] for i in dict.fromkeys(chosen) if i in seen][:top_k]
