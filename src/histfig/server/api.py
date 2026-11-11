"""JSON + SSE API used by the browser UI."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from urllib.parse import quote
from dataclasses import asdict
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from histfig import agent, prompts
from histfig.config import OLLAMA_URL, OPENROUTER_URL, config_path, save_config, suggested_prefixes, updated
from histfig.db import now
from histfig.ingest.extract import SUPPORTED, file_type
from histfig.providers.chat import ProviderError, available_models, similar
from histfig.server.app import AppState
from histfig.server.public import current_visitor, editable

log = logging.getLogger("histfig.api")
router = APIRouter()
EDIT = [Depends(editable)]  # endpoints that change shared things: refused in public mode

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def S(request: Request) -> AppState:
    return request.app.state.hf


def _figure_or_404(s: AppState, figure_id: int) -> dict:
    fig = s.db.one("SELECT * FROM figures WHERE id=?", (figure_id,))
    if fig is None:
        raise HTTPException(404, "Figure not found")
    return fig


def _conversation_or_404(s: AppState, conv_id: int, visitor: str | None = None) -> dict:
    """A conversation that belongs to this visitor (None = the owner's own conversations)."""
    conv = s.db.one("SELECT * FROM conversations WHERE id=? AND visitor IS ?", (conv_id, visitor))
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    return conv


def _figure_view(s: AppState, fig: dict) -> dict:
    stats = s.db.one(
        """SELECT COUNT(*) AS documents,
                  COALESCE(SUM(chunk_count), 0) AS chunks,
                  COALESCE(SUM(status IN ('pending','processing')), 0) AS working,
                  COALESCE(SUM(status = 'error'), 0) AS errors
           FROM documents WHERE figure_id=?""",
        (fig["id"],),
    )
    current = s.embedder.model_id
    return {
        **fig,
        **stats,
        "image_url": f"/api/figures/{fig['id']}/image" if fig["image"] else None,
        "needs_rebuild": bool(fig["embed_model"]) and fig["embed_model"] != current,
        "current_embed_model": current,
    }


# Figures -------------------------------------------------------------------


class FigureIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    persona: str = Field("", max_length=4000)
    birth_year: str = Field("", max_length=20)
    death_year: str = Field("", max_length=20)

    @field_validator("birth_year", "death_year", mode="before")
    @classmethod
    def whole_year(cls, v):
        """Empty (unknown) or a whole number; negative = BC."""
        text = "" if v is None else str(v).strip()
        if not text:
            return ""
        if not re.fullmatch(r"[+-]?\d{1,5}", text):
            raise ValueError("Years must be whole numbers, e.g. 1881, or -551 for 551 BC")
        return str(int(text))


@router.get("/figures")
def list_figures(s: AppState = Depends(S)):
    return [_figure_view(s, f) for f in s.db.all("SELECT * FROM figures ORDER BY name COLLATE NOCASE")]


@router.post("/figures", dependencies=EDIT)
def create_figure(body: FigureIn, s: AppState = Depends(S)):
    fid = s.db.execute(
        "INSERT INTO figures (name, description, persona, birth_year, death_year, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (body.name.strip(), body.description, body.persona, body.birth_year, body.death_year, now()),
    )
    return _figure_view(s, _figure_or_404(s, fid))


@router.get("/figures/{figure_id}")
def get_figure(figure_id: int, s: AppState = Depends(S)):
    return _figure_view(s, _figure_or_404(s, figure_id))


@router.put("/figures/{figure_id}", dependencies=EDIT)
def update_figure(figure_id: int, body: FigureIn, s: AppState = Depends(S)):
    _figure_or_404(s, figure_id)
    s.db.execute(
        "UPDATE figures SET name=?, description=?, persona=?, birth_year=?, death_year=? WHERE id=?",
        (body.name.strip(), body.description, body.persona, body.birth_year, body.death_year, figure_id),
    )
    return _figure_view(s, _figure_or_404(s, figure_id))


@router.delete("/figures/{figure_id}", dependencies=EDIT)
def delete_figure(figure_id: int, s: AppState = Depends(S)):
    fig = _figure_or_404(s, figure_id)
    s.db.execute("DELETE FROM figures WHERE id=?", (figure_id,))
    s.index.invalidate(figure_id)
    shutil.rmtree(s.uploads_dir / str(figure_id), ignore_errors=True)
    if fig["image"]:
        (s.images_dir / fig["image"]).unlink(missing_ok=True)
    return {"ok": True}


def _image_ext(data: bytes) -> str | None:
    """Recognise an image by its first bytes (more reliable than names or headers)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _store_image(s: AppState, fig: dict, data: bytes) -> dict:
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image is larger than 10 MB")
    ext = _image_ext(data)
    if ext is None:
        raise HTTPException(400, f"Not a supported image (use {', '.join(sorted(IMAGE_TYPES))})")
    if fig["image"]:
        (s.images_dir / fig["image"]).unlink(missing_ok=True)
    # Content hash in the name, so browsers never show a cached old portrait.
    name = f"{fig['id']}-{hashlib.sha256(data).hexdigest()[:10]}{ext}"
    (s.images_dir / name).write_bytes(data)
    s.db.execute("UPDATE figures SET image=? WHERE id=?", (name, fig["id"]))
    return _figure_view(s, _figure_or_404(s, fig["id"]))


@router.post("/figures/{figure_id}/image", dependencies=EDIT)
async def upload_image(figure_id: int, file: UploadFile, s: AppState = Depends(S)):
    fig = _figure_or_404(s, figure_id)
    return _store_image(s, fig, await file.read(MAX_IMAGE_BYTES + 1))


class ImageUrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


# Wikimedia (and others) require a descriptive User-Agent with a contact URL.
USER_AGENT = "HistFig/0.1 (https://github.com/mcjkurz/histfig) python-httpx"
# .../wikipedia/commons/thumb/4/47/File.png/280px-File.png -> .../wikipedia/commons/4/47/File.png
WIKIMEDIA_THUMB = re.compile(r"^(https?://upload\.wikimedia\.org/[^/]+/[^/]+/)thumb/(.+?)/[^/]+$", re.I)


async def _download_image(client: httpx.AsyncClient, url: str) -> bytes:
    async with client.stream("GET", url) as resp:
        if resp.status_code >= 400:
            raise HTTPException(400, f"The site refused the download (HTTP {resp.status_code}). "
                                     "Save the image to your computer and upload the file instead.")
        data = b""
        async for chunk in resp.aiter_bytes():
            data += chunk
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(400, "Image is larger than 10 MB")
    return data


@router.post("/figures/{figure_id}/image-url", dependencies=EDIT)
async def image_from_url(figure_id: int, body: ImageUrlIn, s: AppState = Depends(S)):
    """Download an image once and keep a local copy (works offline, survives dead links)."""
    fig = _figure_or_404(s, figure_id)
    url = body.url.strip()
    if not re.match(r"https?://", url, re.I):
        raise HTTPException(400, "The image URL must start with http:// or https://")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20,
                                     headers={"User-Agent": USER_AGENT}) as client:
            try:
                data = await _download_image(client, url)
            except HTTPException:
                # Wikimedia only serves some thumbnail widths; fall back to the original file.
                m = WIKIMEDIA_THUMB.match(url)
                if not m:
                    raise
                data = await _download_image(client, m.group(1) + m.group(2))
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Could not download the image: {e}") from e
    if _image_ext(data) is None:
        raise HTTPException(400, "That URL is not a direct link to a PNG, JPEG, GIF or WebP image")
    return _store_image(s, fig, data)


@router.get("/figures/{figure_id}/image")
def get_image(figure_id: int, s: AppState = Depends(S)):
    fig = _figure_or_404(s, figure_id)
    if not fig["image"] or not (s.images_dir / fig["image"]).exists():
        raise HTTPException(404, "No image")
    return FileResponse(s.images_dir / fig["image"])


# Documents -----------------------------------------------------------------


@router.get("/figures/{figure_id}/documents")
def list_documents(figure_id: int, s: AppState = Depends(S)):
    _figure_or_404(s, figure_id)
    return s.db.all(
        "SELECT id, filename, file_type, char_count, chunk_count, embedded_count, embed_tokens, embed_cost, "
        "status, error, "
        "created_at FROM documents WHERE figure_id=? ORDER BY id DESC",
        (figure_id,),
    )


@router.post("/figures/{figure_id}/documents", dependencies=EDIT)
async def upload_documents(figure_id: int, files: list[UploadFile], s: AppState = Depends(S)):
    _figure_or_404(s, figure_id)
    folder = s.uploads_dir / str(figure_id)
    folder.mkdir(parents=True, exist_ok=True)
    added, skipped = [], []
    for f in files:
        name = f.filename or "untitled"
        kind = file_type(name)
        if kind is None:
            skipped.append({"filename": name, "reason": f"unsupported type (use {', '.join(SUPPORTED)})"})
            continue
        data = await f.read()
        if not data:
            skipped.append({"filename": name, "reason": "empty file"})
            continue
        if len(data) > MAX_UPLOAD_BYTES:
            skipped.append({"filename": name, "reason": "larger than 100 MB"})
            continue
        digest = hashlib.sha256(data).hexdigest()
        if s.db.one("SELECT id FROM documents WHERE figure_id=? AND sha256=?", (figure_id, digest)):
            skipped.append({"filename": name, "reason": "already uploaded"})
            continue
        path = folder / (digest[:16] + "." + name.rsplit(".", 1)[-1].lower())
        path.write_bytes(data)
        doc_id = s.db.execute(
            "INSERT INTO documents (figure_id, filename, file_type, sha256, path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (figure_id, name, kind, digest, str(path), now()),
        )
        s.worker.enqueue(doc_id)
        added.append({"id": doc_id, "filename": name})
    return {"added": added, "skipped": skipped}


@router.delete("/documents/{doc_id}", dependencies=EDIT)
def delete_document(doc_id: int, s: AppState = Depends(S)):
    doc = s.db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if doc is None:
        raise HTTPException(404, "Document not found")
    s.db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    Path(doc["path"]).unlink(missing_ok=True)
    if s.db.one("SELECT 1 FROM documents WHERE figure_id=?", (doc["figure_id"],)) is None:
        s.db.execute("UPDATE figures SET embed_model=NULL, embed_dim=NULL WHERE id=?", (doc["figure_id"],))
    s.index.invalidate(doc["figure_id"])
    return {"ok": True}


@router.post("/documents/{doc_id}/retry", dependencies=EDIT)
async def retry_document(doc_id: int, s: AppState = Depends(S)):
    if s.db.execute("UPDATE documents SET status='pending', error=NULL WHERE id=?", (doc_id,)) == 0:
        raise HTTPException(404, "Document not found")
    s.worker.enqueue(doc_id)
    return {"ok": True}


@router.post("/figures/{figure_id}/rebuild", dependencies=EDIT)
async def rebuild_figure(figure_id: int, s: AppState = Depends(S)):
    _figure_or_404(s, figure_id)
    return {"queued": s.worker.rebuild_figure(figure_id)}


# Retrieval -----------------------------------------------------------------


async def retrieve(s: AppState, fig: dict, query: str, top_k: int | None = None):
    """Hybrid search for a figure. Returns (hits as dicts, warning or None)."""
    warning = None
    qvec = None
    if fig["embed_model"] and fig["embed_model"] != s.embedder.model_id:
        warning = (f"Documents were embedded with {fig['embed_model']} but the configured model "
                   f"is {s.embedder.model_id}; using keyword search only. Rebuild the figure to fix.")
    elif fig["embed_model"]:
        try:
            qvec = await s.embedder.embed_query(query)
        except Exception as e:
            warning = f"Embedding the query failed ({e}); using keyword search only."
    hits = s.index.search(fig["id"], query, qvec, s.cfg.retrieval, top_k)
    return [h.to_dict() for h in hits], warning


# Conversations -------------------------------------------------------------


class ConversationIn(BaseModel):
    title: str | None = None
    model: str | None = None
    prompt_id: int | None = None  # 0 = use the figure's default prompt


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    documents: Literal["off", "simple", "agent"] = "simple"  # how passages are found
    top_k: int | None = Field(None, ge=1, le=30)
    temperature: float | None = Field(None, ge=0, le=2)


@router.get("/figures/{figure_id}/conversations")
def list_conversations(figure_id: int, s: AppState = Depends(S), visitor=Depends(current_visitor)):
    return s.db.all(
        "SELECT * FROM conversations WHERE figure_id=? AND visitor IS ? ORDER BY updated_at DESC, id DESC",
        (figure_id, visitor),
    )


@router.post("/figures/{figure_id}/conversations")
def create_conversation(figure_id: int, body: ConversationIn, s: AppState = Depends(S),
                        visitor=Depends(current_visitor)):
    _figure_or_404(s, figure_id)
    _check_model(s, body)
    prompt_id = _check_prompt(s, body.prompt_id, figure_id)
    ts = now()
    cid = s.db.execute(
        "INSERT INTO conversations (figure_id, title, model, prompt_id, visitor, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (figure_id, body.title or "", body.model or "", prompt_id, visitor, ts, ts),
    )
    return _conversation_or_404(s, cid, visitor)


def _check_model(s: AppState, body: ConversationIn) -> None:
    """Only the chat models chosen in Settings (the default or one of the others)."""
    if body.model and not s.cfg.chat.allows(body.model):
        raise HTTPException(400, f"'{body.model}' is not one of the models available for conversations.")


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, s: AppState = Depends(S), visitor=Depends(current_visitor)):
    conv = _conversation_or_404(s, conv_id, visitor)
    msgs = s.db.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    for m in msgs:
        m["sources"] = json.loads(m["sources"]) if m["sources"] else []
        m["steps"] = json.loads(m["steps"]) if m["steps"] else []
    return {**conv, "messages": msgs}


@router.patch("/conversations/{conv_id}")
def update_conversation(conv_id: int, body: ConversationIn, s: AppState = Depends(S),
                        visitor=Depends(current_visitor)):
    conv = _conversation_or_404(s, conv_id, visitor)
    _check_model(s, body)
    if body.prompt_id is not None:
        s.db.execute("UPDATE conversations SET prompt_id=? WHERE id=?",
                     (_check_prompt(s, body.prompt_id, conv["figure_id"]), conv_id))
    if body.title is not None:
        s.db.execute("UPDATE conversations SET title=? WHERE id=?", (body.title, conv_id))
    if body.model is not None:
        s.db.execute("UPDATE conversations SET model=? WHERE id=?", (body.model, conv_id))
    return _conversation_or_404(s, conv_id, visitor)


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, s: AppState = Depends(S), visitor=Depends(current_visitor)):
    _conversation_or_404(s, conv_id, visitor)
    s.db.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    return {"ok": True}


THINK_RE = re.compile(r"<think>.*?(</think>\s*|$)", re.DOTALL)


def strip_thinking(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def short_title(text: str, limit: int = 16) -> str:
    """A conversation's automatic title: the first words of its first message, at most
    `limit` characters, with "…" when cut. Text without spaces (e.g. Chinese) is cut by characters."""
    words = text.split()
    full = " ".join(words)
    title = ""
    for word in words:
        if len(f"{title} {word}".strip()) > limit:
            break
        title = f"{title} {word}".strip()
    title = title or full[:limit]  # a first "word" longer than the limit
    return title + ("…" if len(title) < len(full) else "")


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: int, body: MessageIn, s: AppState = Depends(S),
                       visitor=Depends(current_visitor)):
    conv = _conversation_or_404(s, conv_id, visitor)
    if s.limiter and visitor:
        s.limiter.check(visitor)
    fig = _figure_or_404(s, conv["figure_id"])
    limit = max(0, s.cfg.retrieval.history_messages)
    history = s.db.all(
        "SELECT role, content FROM (SELECT * FROM messages WHERE conversation_id=? "
        "ORDER BY id DESC LIMIT ?) ORDER BY id",
        (conv_id, limit),
    ) if limit else []
    s.db.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
        (conv_id, body.content, now()),
    )
    if not conv["title"]:
        s.db.execute("UPDATE conversations SET title=? WHERE id=?", (short_title(body.content), conv_id))

    # A model removed from the list since the conversation chose it falls back to the default.
    model = conv["model"] if conv["model"] and s.cfg.chat.allows(conv["model"]) else s.cfg.chat.model

    async def events():
        hits: list[dict] = []
        steps: list[str] = []
        answer: list[str] = []
        try:
            simple = body.documents == "simple"
            if body.documents == "agent":
                try:
                    found = agent.research(
                        s.chat, s.db, fig, body.content, [{"role": m["role"], "content": m["content"]} for m in history],
                        model, body.top_k or s.cfg.retrieval.top_k, lambda q, k: retrieve(s, fig, q, k))
                    async for kind, value in found:
                        if kind == "step":
                            steps.append(value)
                            yield _sse({"type": "step", "text": value})
                        elif kind == "warning":
                            yield _sse({"type": "warning", "message": value})
                        else:
                            hits = value
                except ProviderError as e:
                    log.warning("Agent search failed, using simple search: %s", e)
                    yield _sse({"type": "warning", "message": "This model could not search on its own "
                                f"({str(e)[:120]}); used simple search instead."})
                    simple = True
            if simple:
                hits, warning = await retrieve(s, fig, body.content, body.top_k)
                if warning:
                    yield _sse({"type": "warning", "message": warning})
            yield _sse({"type": "sources", "sources": hits})

            messages = [{"role": "system", "content": prompts.system_prompt(fig, _prompt_text(s, conv, fig))}]
            messages += [{"role": m["role"], "content": m["content"]} for m in history]
            messages.append({"role": "user", "content": prompts.user_message(body.content, hits)})

            async for kind, text in s.chat.stream(messages, model, body.temperature):
                if kind == "content":
                    answer.append(text)
                yield _sse({"type": kind, "text": text})
            yield _sse({"type": "done"})
        except ProviderError as e:
            yield _sse({"type": "error", "message": str(e)})
        except Exception as e:
            log.exception("Chat failed")
            yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            # Runs on normal completion, on errors and when the user presses Stop.
            content = strip_thinking("".join(answer))
            if content:
                s.db.execute(
                    "INSERT INTO messages (conversation_id, role, content, sources, steps, created_at) "
                    "VALUES (?, 'assistant', ?, ?, ?, ?)",
                    (conv_id, content, json.dumps(hits, ensure_ascii=False),
                     json.dumps(steps, ensure_ascii=False) if steps else None, now()),
                )
            s.db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), conv_id))

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _quote(text: str) -> str:
    """Markdown blockquote, keeping the passage's own line breaks."""
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.strip().splitlines())


@router.get("/conversations/{conv_id}/export")
def export_conversation(conv_id: int, s: AppState = Depends(S), visitor=Depends(current_visitor)):
    """The conversation as Markdown, with the full text of the passages behind each answer."""
    conv = _conversation_or_404(s, conv_id, visitor)
    fig = _figure_or_404(s, conv["figure_id"])
    msgs = s.db.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    title = conv["title"] or "Conversation"
    lines = [f"# {title} — {fig['name']}", "", f"*Exported from HistFig on {now()[:10]}*", ""]
    for m in msgs:
        if m["role"] == "user":
            lines += ["---", "", f"**You:** {m['content'].strip()}", ""]
            continue
        lines += [f"**{fig['name']}:** {m['content'].strip()}", ""]
        steps = json.loads(m["steps"]) if m["steps"] else []
        if steps:
            lines += ["*Research: " + "; ".join(steps) + "*", ""]
        sources = json.loads(m["sources"]) if m["sources"] else []
        if sources:
            lines += ["#### Sources", ""]
            for i, h in enumerate(sources, start=1):  # numbered as the model saw them
                lines += [f"**[{i}] {h['filename']} · part {h['chunk'] + 1}**", "", _quote(h["text"]), ""]
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", f"{fig['name']} - {title}").strip()[:80] or "conversation"
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="conversation-{conv_id}.md"; '
                                        f"filename*=UTF-8''{quote(name)}.md"},
    )


# Prompts -------------------------------------------------------------------


class PromptIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20000)
    figure_id: int | None = None  # only used when creating; None = general prompt


class DefaultPromptIn(BaseModel):
    prompt_id: int | None = None  # None = the general default


def _check_prompt(s: AppState, prompt_id: int | None, figure_id: int) -> int | None:
    """A prompt usable for this figure (general or its own); 0/None means 'the default'."""
    if not prompt_id:
        return None
    row = s.db.one("SELECT figure_id FROM prompts WHERE id=?", (prompt_id,))
    if row is None or row["figure_id"] not in (None, figure_id):
        raise HTTPException(400, "That prompt does not exist for this figure")
    return prompt_id


def _prompt_text(s: AppState, conv: dict, fig: dict) -> str:
    """Conversation's prompt → figure's default → general default → built-in."""
    for pid in (conv.get("prompt_id"), fig.get("default_prompt_id")):
        if pid:
            row = s.db.one("SELECT text FROM prompts WHERE id=? AND (figure_id IS NULL OR figure_id=?)",
                           (pid, fig["id"]))
            if row:
                return row["text"]
    row = s.db.one("SELECT text FROM prompts WHERE figure_id IS NULL AND is_default=1")
    return row["text"] if row else prompts.SYSTEM_PROMPT


def _prompt_or_404(s: AppState, prompt_id: int) -> dict:
    row = s.db.one("SELECT * FROM prompts WHERE id=?", (prompt_id,))
    if row is None:
        raise HTTPException(404, "Prompt not found")
    return row


@router.get("/prompts")
def list_prompts(figure_id: int | None = None, s: AppState = Depends(S)):
    """General prompts (default first), then the given figure's own prompts."""
    general = s.db.all("SELECT * FROM prompts WHERE figure_id IS NULL ORDER BY is_default DESC, name COLLATE NOCASE")
    own = s.db.all("SELECT * FROM prompts WHERE figure_id=? ORDER BY name COLLATE NOCASE",
                   (figure_id,)) if figure_id else []
    return general + own


@router.get("/prompts/builtin")
def builtin_prompt():
    return {"text": prompts.SYSTEM_PROMPT, "placeholders": list(prompts.PLACEHOLDERS)}


@router.post("/prompts", dependencies=EDIT)
def create_prompt(body: PromptIn, s: AppState = Depends(S)):
    if body.figure_id is not None:
        _figure_or_404(s, body.figure_id)
    ts = now()
    pid = s.db.execute(
        "INSERT INTO prompts (figure_id, name, text, created_at, updated_at) VALUES (?,?,?,?,?)",
        (body.figure_id, body.name.strip(), body.text, ts, ts),
    )
    return _prompt_or_404(s, pid)


@router.put("/prompts/{prompt_id}", dependencies=EDIT)
def update_prompt(prompt_id: int, body: PromptIn, s: AppState = Depends(S)):
    _prompt_or_404(s, prompt_id)
    s.db.execute("UPDATE prompts SET name=?, text=?, updated_at=? WHERE id=?",
                 (body.name.strip(), body.text, now(), prompt_id))
    return _prompt_or_404(s, prompt_id)


@router.delete("/prompts/{prompt_id}", dependencies=EDIT)
def delete_prompt(prompt_id: int, s: AppState = Depends(S)):
    if _prompt_or_404(s, prompt_id)["is_default"]:
        raise HTTPException(400, "This is the default prompt. Make another prompt the default first.")
    s.db.execute("DELETE FROM prompts WHERE id=?", (prompt_id,))
    return {"ok": True}


@router.post("/prompts/{prompt_id}/make-default", dependencies=EDIT)
def make_default_prompt(prompt_id: int, s: AppState = Depends(S)):
    if _prompt_or_404(s, prompt_id)["figure_id"] is not None:
        raise HTTPException(400, "Only general prompts can be the default for all figures")
    with s.db.connect() as conn:
        conn.execute("UPDATE prompts SET is_default=0 WHERE figure_id IS NULL")
        conn.execute("UPDATE prompts SET is_default=1 WHERE id=?", (prompt_id,))
    return {"ok": True}


@router.put("/figures/{figure_id}/default-prompt", dependencies=EDIT)
def set_figure_default_prompt(figure_id: int, body: DefaultPromptIn, s: AppState = Depends(S)):
    _figure_or_404(s, figure_id)
    s.db.execute("UPDATE figures SET default_prompt_id=? WHERE id=?",
                 (_check_prompt(s, body.prompt_id, figure_id), figure_id))
    return _figure_view(s, _figure_or_404(s, figure_id))


# Settings ------------------------------------------------------------------


def _mask(key: str) -> str:
    return (key[:3] + "…" + key[-4:]) if len(key) > 10 else ("set" if key else "")


@router.get("/settings", dependencies=EDIT)
def get_settings(s: AppState = Depends(S)):
    cfg = asdict(s.cfg)
    for section in ("chat", "embedding"):
        cfg[section]["api_key"] = _mask(cfg[section]["api_key"])
        cfg[section]["key_available"] = bool(s.cfg.chat.resolved_key() if section == "chat" else s.cfg.embedding_key())
    usage = s.db.one("SELECT COALESCE(SUM(embed_tokens_total), 0) AS tokens, "
                     "COALESCE(SUM(embed_cost_total), 0) AS cost FROM figures")
    chat, emb = s.cfg.chat, s.cfg.embedding
    return {"config": cfg, "config_path": str(config_path(s.data_dir)), "data_dir": str(s.data_dir),
            "embedding_usage": usage, "problems": s.cfg.validate(),
            # Ticked = the embedding model has no key of its own and uses the chat model's key
            "same_key": not (emb.api_key or emb.api_key_env)
                        or (chat.api_key, chat.api_key_env) == (emb.api_key, emb.api_key_env),
            "urls": {"openrouter": OPENROUTER_URL, "ollama": OLLAMA_URL}}


class SettingsIn(BaseModel):
    """Partial update: only the sections (and fields) sent are changed.
    In chat/embedding, a missing api_key means "keep the saved key"."""

    chat: dict | None = None
    embedding: dict | None = None
    chunking: dict | None = None
    retrieval: dict | None = None
    same_key_as_chat: bool = False  # embedding uses the chat model's key


@router.put("/settings", dependencies=EDIT)
async def save_settings(body: SettingsIn, s: AppState = Depends(S)):
    changes = body.model_dump(exclude_none=True, exclude={"same_key_as_chat"})
    try:
        new = updated(s.cfg, changes)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"Invalid value: {e}") from e
    old = s.cfg
    copy_of_chat_key = (old.embedding.api_key, old.embedding.api_key_env) == (old.chat.api_key, old.chat.api_key_env)
    if body.same_key_as_chat or ("embedding" not in changes and copy_of_chat_key):
        # "Same key": no key of its own, so the embedding model always uses the chat key
        # (an older identical copy is turned into this, so it can't go stale)
        new.embedding.api_key, new.embedding.api_key_env = "", ""
    if new.embedding.model != old.embedding.model and \
            (new.embedding.query_prefix, new.embedding.document_prefix) == (old.embedding.query_prefix, old.embedding.document_prefix):
        new.embedding.query_prefix, new.embedding.document_prefix = suggested_prefixes(new.embedding.model)

    sent = set(changes) | ({"embedding"} if body.same_key_as_chat else set())
    problems = [p for p in new.validate() if p.split(".")[0] in sent]
    if problems:
        raise HTTPException(400, "; ".join(problems))

    warnings = []
    for section, label, is_embedding in (("chat", "chat model", False), ("embedding", "embedding model", True)):
        c, o = getattr(new, section), getattr(old, section)
        if section not in sent or not c.model or c.provider == "sentence_transformers":
            continue
        extra = c.allowed_models if section == "chat" else []
        key = new.embedding_key() if is_embedding else c.resolved_key()
        old_key = old.embedding_key() if is_embedding else o.resolved_key()
        if (c.provider, c.base_url, c.model, key, extra) == \
                (o.provider, o.base_url, o.model, old_key, o.allowed_models if section == "chat" else []):
            continue  # nothing that affects availability changed
        try:
            models = await available_models(c.base_url, key, is_embedding)
        except Exception as e:
            warnings.append(f"Could not check the {label} list ({e}); saved without checking.")
            continue
        for name in [c.model, *extra]:
            if models and name not in models and f"{name}:latest" not in models:
                close = similar(name, models)
                raise HTTPException(400, f"The {label} '{name}' is not available at {c.base_url}."
                                         + (f" Did you mean: {', '.join(close)}?" if close else ""))

    embedded = s.db.one("SELECT COUNT(*) AS n FROM figures WHERE embed_model IS NOT NULL")["n"]
    if new.embedding.model_id != old.embedding.model_id and embedded:
        warnings.append("The embedding model changed: open each figure and click “Rebuild index”.")
    if new.chunking != old.chunking and embedded:
        warnings.append("New passage sizes apply to new uploads; use “Rebuild index” on a figure to apply them there.")

    save_config(new, s.data_dir)
    s.apply_config(new)
    return {**get_settings(s), "warnings": warnings}


@router.get("/settings/embedding-models", dependencies=EDIT)
async def embedding_models(s: AppState = Depends(S)):
    """The embedding models the configured provider offers (for "Browse models…")."""
    e = s.cfg.embedding
    if e.provider == "sentence_transformers":
        return {"models": [], "error": "sentence-transformers has no model list; type a Hugging Face model name"}
    try:
        return {"models": await available_models(e.base_url, s.cfg.embedding_key(), embedding=True)}
    except Exception as ex:
        return {"models": [], "error": str(ex)}


@router.get("/info")
def info(s: AppState = Depends(S)):
    return {"public": s.public}


@router.get("/models")
async def get_models(s: AppState = Depends(S)):
    try:
        models, error = await s.models.get(), None
    except Exception as e:
        models, error = [], str(e)
    return {"models": [] if s.public else models,  # the full list is only for the owner's Settings page
            "allowed": s.cfg.chat.allowed_models, "default": s.cfg.chat.model,
            "temperature": s.cfg.chat.temperature, "error": error}


@router.post("/settings/test/{which}", dependencies=EDIT)
async def test_settings(which: str, s: AppState = Depends(S)):
    """Send one tiny request to the chat or the embedding model."""
    try:
        if which == "chat":
            reply = await s.chat.complete([{"role": "user", "content": "Reply with the single word: OK"}])
            return {"ok": True, "detail": f"replied {strip_thinking(reply)[:60].strip()!r}" if reply else "empty reply"}
        if which == "embedding":
            vec = await s.embedder.embed_query("test")
            return {"ok": True, "detail": f"{len(vec)}-dimensional vectors"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
    raise HTTPException(404, "Unknown test (use chat or embedding)")
