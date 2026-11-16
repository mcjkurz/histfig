"""Exporting a conversation as Markdown, plain text, or a standalone web page.

The conversation is gathered once (Conversation) and then written in the chosen format.
Answers use light Markdown (**bold**, *italic*) and cite passages as [1] or [1, 3]; each
format renders those in its own way, and lists the full passages under each answer.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

from histfig.prompts import years


@dataclass
class Message:
    role: str  # user | assistant
    content: str
    sources: list[dict] = field(default_factory=list)  # passages, numbered as the model saw them
    steps: list[str] = field(default_factory=list)  # agent search: what was looked up


@dataclass
class Conversation:
    title: str
    figure: str
    years: str  # "1881–1936" or ""
    date: str  # YYYY-MM-DD of the export
    messages: list[Message]

    @property
    def heading(self) -> str:
        return f"{self.title} — {self.figure}"

    @property
    def subtitle(self) -> str:
        who = f"{self.figure} ({self.years})" if self.years else self.figure
        return f"A conversation with {who}, exported from HistFig on {self.date}"


def gather(db, conv: dict, fig: dict, date: str) -> Conversation:
    rows = db.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conv["id"],))
    messages = [Message(r["role"], (r["content"] or "").strip(),
                        json.loads(r["sources"]) if r["sources"] else [],
                        json.loads(r["steps"]) if r["steps"] else []) for r in rows]
    return Conversation(conv["title"] or "Conversation", fig["name"],
                        years(fig.get("birth_year", ""), fig.get("death_year", "")).strip(" ()"),
                        date, messages)


def _where(source: dict) -> str:
    return f"{source['filename']} · part {source['chunk'] + 1}"


# Markdown --------------------------------------------------------------------


def _quote(text: str) -> str:
    """Markdown blockquote, keeping the passage's own line breaks."""
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.strip().splitlines())


def to_markdown(c: Conversation) -> str:
    lines = [f"# {c.heading}", "", f"*{c.subtitle}*", ""]
    for m in c.messages:
        if m.role == "user":
            lines += ["---", "", f"**You:** {m.content}", ""]
            continue
        lines += [f"**{c.figure}:** {m.content}", ""]
        if m.steps:
            lines += ["Research:", "", *(f"{i}. {step}" for i, step in enumerate(m.steps, start=1)), ""]
        if m.sources:
            lines += ["#### Sources", ""]
            for i, s in enumerate(m.sources, start=1):
                lines += [f"**[{i}] {_where(s)}**", "", _quote(s["text"]), ""]
    return "\n".join(lines)


# Plain text ------------------------------------------------------------------

_EMPHASIS = re.compile(r"\*\*(.+?)\*\*|(?<![*\w])\*([^*\n]+)\*(?![*\w])")


def _plain(text: str) -> str:
    """Without Markdown emphasis markers."""
    return _EMPHASIS.sub(lambda m: m.group(1) or m.group(2), text)


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line if line.strip() else "" for line in text.strip().splitlines())


def to_text(c: Conversation) -> str:
    rule = "=" * 72
    lines = [c.heading, rule, c.subtitle, ""]
    for m in c.messages:
        if m.role == "user":
            lines += ["-" * 72, "", "You:", _indent(m.content), ""]
            continue
        lines += [f"{c.figure}:", _indent(_plain(m.content)), ""]
        if m.steps:
            lines += ["    Research:", *(f"    {i}. {step}" for i, step in enumerate(m.steps, start=1)), ""]
        if m.sources:
            lines += ["    Sources:", ""]
            for i, s in enumerate(m.sources, start=1):
                lines += [f"    [{i}] {_where(s)}", _indent(s["text"], "        "), ""]
    return "\n".join(lines)


# HTML (also the basis of the PDF) --------------------------------------------

_CITATION = re.compile(r"\[(\d+(?:\s*[,，、]\s*\d+)*)\]")


def _rich(text: str, cite=None) -> str:
    """Safe text → HTML paragraphs with <b>, <i> and line breaks. cite(numbers_text) may
    replace the [1] / [1, 3] citations."""
    out = []
    for para in re.split(r"\n\s*\n", html.escape(text.strip(), quote=False)):
        para = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", para)
        para = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<i>\1</i>", para)
        if cite:
            para = _CITATION.sub(lambda m: cite(m.group(1)), para)
        out.append("<p>" + para.replace("\n", "<br>") + "</p>")
    return "".join(out)


_HTML_STYLE = """
:root { --bg: #fdfcfa; --text: #2a2622; --muted: #6f675e; --border: #e2dad0; --accent: #8a5a2b;
        --soft: #f3e7d8; --card: #f6f2ec; color-scheme: light dark; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #1b1916; --text: #ece6dd; --muted: #a59c90; --border: #3a352e; --accent: #d39b5f;
          --soft: #3a2e21; --card: #24211d; }
}
body { margin: 0; background: var(--bg); color: var(--text);
       font: 17px/1.65 Georgia, "Noto Serif", "Noto Serif CJK SC", "Songti SC", "SimSun", serif; }
main { max-width: 760px; margin: 0 auto; padding: 40px 20px 64px; }
h1 { font-size: 1.7rem; line-height: 1.3; margin: 0 0 4px; }
.subtitle { color: var(--muted); font-size: .9rem; margin: 0 0 32px; }
.msg { margin: 0 0 22px; }
.who { font: 600 .78rem/1.4 system-ui, sans-serif; text-transform: uppercase; letter-spacing: .05em;
       color: var(--muted); margin-bottom: 4px; }
.user { border-top: 1px solid var(--border); padding-top: 22px; }
.user .text { background: var(--soft); border-radius: 12px; padding: 10px 16px; }
.text p { margin: 0 0 .7em; } .text p:last-child { margin: 0; }
sup a { font: 600 .7rem system-ui, sans-serif; color: var(--accent); text-decoration: none;
        padding: 0 3px; margin-left: 1px; border-radius: 4px; background: var(--soft); }
.steps { color: var(--muted); font-size: .85rem; margin-top: 10px; }
.steps ol { margin: 2px 0 0; padding-left: 1.6em; }
.toggle-all { font: 600 .85rem system-ui, sans-serif; color: var(--accent); background: none; cursor: pointer;
              border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; margin: -16px 0 28px; }
.toggle-all:hover { border-color: var(--accent); }
details { margin-top: 12px; font-size: .9rem; }
summary { cursor: pointer; color: var(--accent); font: 600 .85rem system-ui, sans-serif; }
.source { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
          padding: 10px 14px; margin-top: 10px; }
.source:target { border-color: var(--accent); }
.source h4 { margin: 0 0 6px; font: 600 .82rem/1.4 system-ui, sans-serif; }
.source .n { display: inline-block; min-width: 1.5em; text-align: center; border-radius: 4px;
             background: var(--accent); color: var(--bg); margin-right: 6px; }
.source .passage { white-space: pre-wrap; }
@media print {
  body { background: #fff; color: #000; font-size: 11pt; } main { max-width: none; padding: 0; }
  details > summary, .toggle-all { display: none; } details:not([open]) > .source { display: block; }
  .source { break-inside: avoid; }
}
"""


def to_html(c: Conversation) -> str:
    """A standalone page: works offline, in light and dark, and prints with its sources."""
    parts = [f"<h1>{html.escape(c.heading)}</h1>", f'<p class="subtitle">{html.escape(c.subtitle)}</p>']
    for k, m in enumerate(c.messages):
        if m.role == "user":
            parts.append(f'<section class="msg user"><div class="who">You</div>'
                         f'<div class="text">{_rich(m.content)}</div></section>')
            continue

        def cite(numbers: str, k=k, m=m) -> str:
            links = []
            for n in re.split(r"\s*[,，、]\s*", numbers):
                ok = 1 <= int(n) <= len(m.sources)
                links.append(f'<a href="#m{k}-s{n}">{n}</a>' if ok else n)
            return "<sup>" + "".join(links) + "</sup>"

        body = _rich(m.content, cite if m.sources else None)
        extra = ""
        if m.steps:
            items = "".join(f"<li>{html.escape(step)}</li>" for step in m.steps)
            extra += f'<div class="steps">Research:<ol>{items}</ol></div>'
        if m.sources:
            cards = "".join(
                f'<div class="source" id="m{k}-s{i}"><h4><span class="n">{i}</span>{html.escape(_where(s))}</h4>'
                f'<div class="passage">{html.escape(s["text"].strip())}</div></div>'
                for i, s in enumerate(m.sources, start=1))
            extra += f'<details class="sources"><summary>Sources ({len(m.sources)})</summary>{cards}</details>'
        parts.append(f'<section class="msg"><div class="who">{html.escape(c.figure)}</div>'
                     f'<div class="text">{body}</div>{extra}</section>')
    if any(m.sources for m in c.messages):
        parts.insert(2, '<button type="button" class="toggle-all" id="toggle-all">Show all sources</button>')
    return (f'<!doctype html>\n<html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(c.heading)}</title><style>{_HTML_STYLE}</style></head>"
            f"<body><main>{''.join(parts)}</main><script>{_HTML_SCRIPT}</script></body></html>\n")


# "Show all sources" / "Hide all sources", and a clicked citation opens the passage it points to
_HTML_SCRIPT = """
const all = [...document.querySelectorAll("details.sources")], button = document.getElementById("toggle-all");
const update = () => { button.textContent = all.every((d) => d.open) ? "Hide all sources" : "Show all sources"; };
if (button) {
  button.onclick = () => { const open = !all.every((d) => d.open); all.forEach((d) => (d.open = open)); update(); };
  all.forEach((d) => d.addEventListener("toggle", update));
}
document.addEventListener("click", (e) => {
  const link = e.target.closest("sup a");
  const target = link && document.getElementById(link.getAttribute("href").slice(1));
  if (target) target.closest("details").open = true;
});
"""


# Formats ----------------------------------------------------------------------

FORMATS = {  # name: (file extension, media type)
    "md": ("md", "text/markdown; charset=utf-8"),
    "txt": ("txt", "text/plain; charset=utf-8"),
    "html": ("html", "text/html; charset=utf-8"),
}


def render(c: Conversation, fmt: str) -> bytes:
    return {"md": to_markdown, "txt": to_text, "html": to_html}[fmt](c).encode("utf-8")
