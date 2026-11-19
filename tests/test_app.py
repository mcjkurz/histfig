"""End-to-end through the HTTP API with fake providers (no network)."""

import json
import re
import time

from fastapi.testclient import TestClient

from histfig.server.app import create_app
from tests.conftest import FakeChat, FakeEmbedder

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32

RIVER = "\n\n".join([
    "I spent my childhood by the Yangtze river, watching the boats go by every morning.",
    "Later I studied classical poetry and wrote essays on the reform of education.",
    "我曾在长江边度过童年，每天早晨看着船只经过。",
    "Mountains taught me patience; the river taught me that everything flows.",
] * 3)


def wait_ready(client, fid, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        docs = client.get(f"/api/figures/{fid}/documents").json()
        if docs and all(d["status"] in ("ready", "error") for d in docs):
            return docs
        time.sleep(0.05)
    raise AssertionError(f"documents not ready: {docs}")


def sse_events(text):
    return [json.loads(line[5:]) for line in text.splitlines() if line.startswith("data:")]


def ask(client, fid, question):
    """Ask in a new conversation; returns (sources, warnings) as the chat reports them."""
    cid = client.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
    events = sse_events(client.post(f"/api/conversations/{cid}/messages", json={"content": question}).text)
    sources = next((e["sources"] for e in events if e["type"] == "sources"), [])
    return sources, [e["message"] for e in events if e["type"] == "warning"]


def make_client(cfg, tmp_path, embedder=None, chat=None):
    return TestClient(create_app(cfg, tmp_path, embedder or FakeEmbedder(), chat or FakeChat(), prefetch_models=False))


def test_full_flow(cfg, tmp_path):
    chat = FakeChat()
    embedder = FakeEmbedder()
    with make_client(cfg, tmp_path, embedder, chat) as client:
        assert client.get("/").status_code == 200
        fig = client.post("/api/figures", json={"name": "梁启超 Liang Qichao", "birth_year": "1873"}).json()
        fid = fig["id"]

        r = client.post(f"/api/figures/{fid}/documents", files=[
            ("files", ("memoir.txt", RIVER.encode("utf-8"), "text/plain")),
            ("files", ("virus.exe", b"MZ", "application/octet-stream")),
        ]).json()
        assert [a["filename"] for a in r["added"]] == ["memoir.txt"]
        assert r["skipped"][0]["filename"] == "virus.exe"

        # Same content twice is skipped
        dup = client.post(f"/api/figures/{fid}/documents",
                          files=[("files", ("copy.txt", RIVER.encode("utf-8"), "text/plain"))]).json()
        assert dup["skipped"][0]["reason"] == "already uploaded"

        docs = wait_ready(client, fid)
        assert docs[0]["status"] == "ready", docs
        assert docs[0]["chunk_count"] > 1 and docs[0]["embedded_count"] == docs[0]["chunk_count"]
        assert embedder.calls >= docs[0]["chunk_count"] / 4  # batched by 4

        fig = client.get(f"/api/figures/{fid}").json()
        assert fig["embed_model"] == "openai_compatible:fake-embed" and fig["embed_dim"] == 64
        assert not fig["needs_rebuild"]

        hits, _ = ask(client, fid, "Yangtze river boats")
        assert hits and "Yangtze" in hits[0]["text"]
        zh, _ = ask(client, fid, "长江 船只")
        assert zh and "长江" in zh[0]["text"]

        conv = client.post(f"/api/figures/{fid}/conversations", json={}).json()
        resp = client.post(f"/api/conversations/{conv['id']}/messages",
                           json={"content": "Tell me about the river", "top_k": 3})
        events = sse_events(resp.text)
        types = [e["type"] for e in events]
        assert types[0] == "sources" and types[-1] == "done" and "thinking" in types
        assert len(events[0]["sources"]) == 3
        # RAG passages go into the current user turn; persona into the system prompt
        assert chat.last_messages[0]["role"] == "system" and "Liang Qichao" in chat.last_messages[0]["content"]
        assert "Passages from your writings" in chat.last_messages[-1]["content"]

        saved = client.get(f"/api/conversations/{conv['id']}").json()
        assert saved["title"] == "Tell me about…"  # first words, at most 16 characters
        assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
        assert saved["messages"][1]["content"] == "I remember the river."
        assert len(saved["messages"][1]["sources"]) == 3

        # Second turn sends history without the old passages
        client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "And then?"})
        assert [m["role"] for m in chat.last_messages] == ["system", "user", "assistant", "user"]
        assert chat.last_messages[1]["content"] == "Tell me about the river"

        export = client.get(f"/api/conversations/{conv['id']}/export")
        md = export.text
        assert "I remember the river." in md and "**[1] memoir.txt · part" in md
        first_source = saved["messages"][1]["sources"][0]["text"].strip().splitlines()[0]
        assert f"> {first_source}" in md  # the passage text itself, quoted
        assert md.index("**You:** Tell me about the river") < md.index("#### Sources") < md.index("**You:** And then?")
        assert "Liang%20Qichao%20-%20Tell%20me%20about" in export.headers["content-disposition"]

        assert client.post("/api/settings/test/chat").json()["ok"]
        assert client.post("/api/settings/test/embedding").json()["ok"]
        assert client.post("/api/settings/test/bogus").status_code == 404
        assert "api_key" in client.get("/api/settings").json()["config"]["chat"]


def test_model_change_requires_rebuild_and_resume(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Du Fu"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents",
                    files=[("files", ("poems.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)

    # Restart with a different embedding model
    cfg.embedding.model = "other-embed"
    with make_client(cfg, tmp_path, FakeEmbedder("other-embed")) as client:
        fig = client.get(f"/api/figures/{fid}").json()
        assert fig["needs_rebuild"]
        hits, warnings = ask(client, fid, "river")
        assert warnings and hits  # keyword fallback still works

        # New uploads are refused until rebuilt
        client.post(f"/api/figures/{fid}/documents",
                    files=[("files", ("more.txt", b"Another text about autumn.", "text/plain"))])
        docs = wait_ready(client, fid)
        assert any(d["status"] == "error" and "Rebuild index" in (d["error"] or "") for d in docs)

        client.post(f"/api/figures/{fid}/rebuild")
        docs = wait_ready(client, fid)
        assert all(d["status"] == "ready" for d in docs)
        fig = client.get(f"/api/figures/{fid}").json()
        assert fig["embed_model"] == "openai_compatible:other-embed" and not fig["needs_rebuild"]


def test_rebuild_while_a_document_is_being_embedded(cfg, tmp_path):
    """Rebuilding (or retrying) mid-ingestion must re-process the document, not lose its passages."""
    import asyncio

    class SlowEmbedder(FakeEmbedder):
        async def _embed(self, texts):
            await asyncio.sleep(0.05)
            return await super()._embed(texts)

    with make_client(cfg, tmp_path, SlowEmbedder()) as client:
        fid = client.post("/api/figures", json={"name": "Wang Wei"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents",
                    files=[("files", ("a.txt", (RIVER * 3).encode(), "text/plain"))])
        deadline = time.time() + 5
        while client.get(f"/api/figures/{fid}/documents").json()[0]["status"] != "processing":
            assert time.time() < deadline
            time.sleep(0.01)
        client.post(f"/api/figures/{fid}/rebuild")
        doc = wait_ready(client, fid)[0]
        assert doc["status"] == "ready" and doc["chunk_count"] > 0
        assert doc["embedded_count"] == doc["chunk_count"]
        assert ask(client, fid, "Yangtze river")[0]


def test_chat_is_locked_while_processing_and_processing_can_be_stopped(cfg, tmp_path):
    import asyncio

    class SlowEmbedder(FakeEmbedder):
        async def _embed(self, texts):
            await asyncio.sleep(0.05)
            return await super()._embed(texts)

    embedder = SlowEmbedder()
    with make_client(cfg, tmp_path, embedder) as client:
        fid = client.post("/api/figures", json={"name": "Li Bai"}).json()["id"]
        cid = client.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
        client.post(f"/api/figures/{fid}/documents", files=[
            ("files", (f"poem{i}.txt", f"Poem {i}. ".encode() + (RIVER * 3).encode(), "text/plain"))
            for i in range(20)
        ])
        assert client.get(f"/api/figures/{fid}").json()["working"] > 0

        # Locked: no new conversation, no message (and nothing is saved)
        assert client.post(f"/api/figures/{fid}/conversations", json={}).status_code == 409
        r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Hello"})
        assert r.status_code == 409 and "still being processed" in r.json()["detail"]
        assert client.get(f"/api/conversations/{cid}").json()["messages"] == []

        stopped = client.post(f"/api/figures/{fid}/stop").json()["stopped"]
        assert stopped > 0
        docs = wait_ready(client, fid)
        calls = embedder.calls
        time.sleep(0.3)
        assert embedder.calls <= calls + 1  # at most the batch in flight finishes
        assert sum(d["status"] == "error" for d in docs) == stopped
        assert client.get(f"/api/figures/{fid}").json()["working"] == 0

        # Unlocked again
        assert client.post(f"/api/conversations/{cid}/messages", json={"content": "Hello"}).status_code == 200

        # A stopped document can be retried and continues where it stopped
        first = next(d for d in docs if d["status"] == "error")
        client.post(f"/api/documents/{first['id']}/retry")
        doc = next(d for d in wait_ready(client, fid) if d["id"] == first["id"])
        assert doc["status"] == "ready" and doc["embedded_count"] == doc["chunk_count"] > 0

        # The rest are deleted at once, files too
        deleted = client.delete(f"/api/figures/{fid}/documents/failed").json()["deleted"]
        assert deleted == stopped - 1
        left = client.get(f"/api/figures/{fid}/documents").json()
        assert left and all(d["status"] == "ready" for d in left)
        assert len(list((tmp_path / "uploads" / str(fid)).iterdir())) == len(left)


def test_settings_apply_to_the_next_uploads_without_restart(cfg, tmp_path, monkeypatch):
    from histfig.config import save_config

    save_config(cfg, tmp_path)
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Han Yu"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        small = wait_ready(client, fid)[0]["chunk_count"]
        r = client.put("/api/settings", json={"chunking": {"chunk_size": 1000, "overlap": 0}})
        assert r.status_code == 200 and r.json()["warnings"]  # existing documents keep their passages
        client.post(f"/api/figures/{fid}/documents",
                    files=[("files", ("b.txt", (RIVER + " Again.").encode(), "text/plain"))])
        docs = {d["filename"]: d for d in wait_ready(client, fid)}
        assert docs["b.txt"]["chunk_count"] < small  # bigger passages → fewer of them


def test_rebuild_all_figures(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Du Mu"}).json()["id"]
        client.post("/api/figures", json={"name": "No documents"})
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)

    cfg.embedding.model = "other-embed"
    with make_client(cfg, tmp_path, FakeEmbedder("other-embed")) as client:
        assert client.get("/api/settings").json()["figures"] == {"with_documents": 1, "outdated": 1}
        assert client.post("/api/figures/rebuild-all").json() == {"figures": 1, "queued": 1}
        assert all(d["status"] == "ready" for d in wait_ready(client, fid))
        assert client.get("/api/settings").json()["figures"]["outdated"] == 0


def test_export_formats(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "鲁迅", "birth_year": "1881", "death_year": "1936"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("memoir.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)
        cid = client.post(f"/api/figures/{fid}/conversations", json={"title": "长江 <river>"}).json()["id"]
        client.post(f"/api/conversations/{cid}/messages", json={"content": "Tell me about the *river* <b>"})
        url = f"/api/conversations/{cid}/export?format="

        md = client.get(url + "md")
        assert md.headers["content-type"].startswith("text/markdown") and "#### Sources" in md.text
        assert ".md" in md.headers["content-disposition"] and "%E9%B2%81%E8%BF%85" in md.headers["content-disposition"]

        txt = client.get(url + "txt")
        assert txt.headers["content-type"].startswith("text/plain")
        assert "鲁迅 (1881–1936)" in txt.text and "Sources:" in txt.text and "Yangtze" in txt.text

        page = client.get(url + "html")
        assert page.headers["content-type"].startswith("text/html") and "attachment" in page.headers["content-disposition"]
        assert "&lt;river&gt;" in page.text and "<river>" not in page.text  # everything typed is escaped
        assert "&lt;b&gt;" in page.text and 'class="source"' in page.text

        assert client.get(url + "pdf").status_code == 400
        assert client.get(f"/api/conversations/{cid + 99}/export").status_code == 404


def test_interrupted_ingestion_resumes(cfg, tmp_path):
    from histfig.db import Database

    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Su Shi"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents",
                    files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)

    # Simulate a crash halfway through embedding
    db = Database(tmp_path / "histfig.db")
    db.execute("UPDATE chunks SET embedding=NULL WHERE id IN (SELECT id FROM chunks ORDER BY id DESC LIMIT 2)")
    db.execute("UPDATE documents SET status='processing'")

    embedder = FakeEmbedder()
    with make_client(cfg, tmp_path, embedder) as client:
        docs = wait_ready(client, fid)
        assert docs[0]["status"] == "ready" and docs[0]["embedded_count"] == docs[0]["chunk_count"]
        assert embedder.calls == 1  # only the missing batch was embedded


def test_delete_figure_cleans_up(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Li Bai"}).json()["id"]
        client.post(f"/api/figures/{fid}/image", files={"file": ("p.png", PNG, "image/png")})
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)
        assert client.get(f"/api/figures/{fid}/image").status_code == 200
        assert client.delete(f"/api/figures/{fid}").json()["ok"]
        assert client.get(f"/api/figures/{fid}").status_code == 404
        assert not (tmp_path / "uploads" / str(fid)).exists()
        assert not list((tmp_path / "images").iterdir())


def test_portrait_upload_and_url(cfg, tmp_path, monkeypatch):
    import httpx

    def serve(request):
        if request.url.path in ("/p.png", "/wikipedia/commons/4/47/P.png"):
            return httpx.Response(200, content=PNG)
        if request.url.path == "/page.html":
            return httpx.Response(200, content=b"<html>not an image</html>")
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(serve), **kw))
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Li Bai"}).json()["id"]
        bad = client.post(f"/api/figures/{fid}/image", files={"file": ("x.png", b"hello", "image/png")})
        assert bad.status_code == 400

        fig = client.post(f"/api/figures/{fid}/image-url", json={"url": "https://example.org/p.png"}).json()
        assert fig["image"].endswith(".png") and client.get(fig["image_url"]).content == PNG
        thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/P.png/280px-P.png"
        assert client.post(f"/api/figures/{fid}/image-url", json={"url": thumb}).status_code == 200
        for url, status in [("https://example.org/page.html", 400), ("https://example.org/missing.png", 400),
                            ("file:///etc/passwd", 400)]:
            assert client.post(f"/api/figures/{fid}/image-url", json={"url": url}).status_code == status
        assert len(list((tmp_path / "images").iterdir())) == 1


def test_embedding_usage_is_recorded(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Li Bai"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        docs = wait_ready(client, fid)
        chunks = docs[0]["chunk_count"]
        assert docs[0]["embed_tokens"] == 10 * chunks
        fig = client.get(f"/api/figures/{fid}").json()
        assert fig["embed_tokens_total"] == 10 * chunks and abs(fig["embed_cost_total"] - 0.001 * chunks) < 1e-9

        client.post(f"/api/figures/{fid}/rebuild")  # a rebuild costs again: the total keeps counting
        docs = wait_ready(client, fid)
        assert docs[0]["embed_tokens"] == 10 * chunks
        assert client.get(f"/api/figures/{fid}").json()["embed_tokens_total"] == 20 * chunks
        assert client.get("/api/settings").json()["embedding_usage"]["tokens"] == 20 * chunks


def test_figure_years_are_understood_in_many_forms(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        make = lambda b, d: client.post("/api/figures", json={"name": "X", "birth_year": b, "death_year": d})
        assert make("-551", "-479").json()["birth_year"] == "-551"
        assert make("", "").status_code == 200 and make(None, None).status_code == 200
        fig = make("公元前551年", "479 BC").json()
        assert (fig["birth_year"], fig["death_year"]) == ("-551", "-479")
        fig = make("c. 1881", "１９３６年").json()
        assert (fig["birth_year"], fig["death_year"]) == ("1881", "1936")
        assert make("?", "不详").json()["birth_year"] == ""
        for bad in ("1868.5", "1881-1936", "soon", "123456"):
            r = make(bad, "")
            assert r.status_code == 422 and "not a year" in r.text, bad
        r = make("1936", "1881")  # swapped
        assert r.status_code == 422 and "before the year of birth" in r.text


def test_figure_fields_accept_any_script_and_only_require_a_name(cfg, tmp_path):
    with make_client(cfg, tmp_path) as client:
        fig = client.post("/api/figures", json={"name": "  鲁迅\n(Lu Xun)\u200b ",
                                                "description": "中国现代文学的奠基人。\r\n\x00"}).json()
        assert fig["name"] == "鲁迅 (Lu Xun)" and fig["description"] == "中国现代文学的奠基人。"
        assert fig["persona"] == "" and fig["birth_year"] == fig["death_year"] == ""
        for name in ("", "   ", "\u200b", None):
            r = client.post("/api/figures", json={"name": name})
            assert r.status_code == 422 and "Please enter a name" in r.text, name
        assert client.post("/api/figures", json={}).status_code == 422
        assert client.post("/api/figures", json={"name": "X" * 201}).status_code == 422
        fid = fig["id"]
        assert client.put(f"/api/figures/{fid}", json={"name": "孔子", "birth_year": "前551"}).json()["name"] == "孔子"
        # Free text never breaks the prompt (braces, quotes and the like are kept as written)
        client.put(f"/api/figures/{fid}", json={"name": "Odd {persona} \"name\"", "persona": "{name} says {hi}"})
        cid = client.post(f"/api/figures/{fid}/conversations", json={"title": "  a\nb  "}).json()
        assert cid["title"] == "a b"
        r = client.post(f"/api/conversations/{cid['id']}/messages", json={"content": "Hi", "documents": "off"})
        assert r.status_code == 200 and sse_events(r.text)[-1]["type"] == "done"
        assert client.post("/api/prompts", json={"name": "  ", "text": "x"}).status_code == 422


def test_prompts_general_figure_and_conversation(cfg, tmp_path):
    chat = FakeChat()
    with make_client(cfg, tmp_path, chat=chat) as client:
        send = lambda cid: client.post(f"/api/conversations/{cid}/messages",
                                       json={"content": "Hi", "documents": "off"}).text
        system = lambda: chat.last_messages[0]["content"]
        fid = client.post("/api/figures", json={"name": "Confucius", "birth_year": "-551",
                                                "death_year": "-479", "description": "A teacher."}).json()["id"]
        other = client.post("/api/figures", json={"name": "Other"}).json()["id"]

        # A seeded general "Default" prompt is used out of the box.
        listed = client.get(f"/api/prompts?figure_id={fid}").json()
        assert [p["name"] for p in listed] == ["Default"] and listed[0]["is_default"]
        cid = client.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
        send(cid)
        assert "You are Confucius (551–479 BC)." in system()

        # A figure prompt with placeholders; unknown braces stay as written.
        p = client.post("/api/prompts", json={"name": "Teacher", "figure_id": fid,
                        "text": "Be {name}, {years}. {description} Keep {braces}."}).json()
        client.patch(f"/api/conversations/{cid}", json={"prompt_id": p["id"]})
        send(cid)
        assert system() == "Be Confucius, 551–479 BC. A teacher. Keep {braces}."

        # It can't be used with another figure.
        oc = client.post(f"/api/figures/{other}/conversations", json={}).json()["id"]
        assert client.patch(f"/api/conversations/{oc}", json={"prompt_id": p["id"]}).status_code == 400

        # Figure default applies to conversations without their own choice.
        client.patch(f"/api/conversations/{cid}", json={"prompt_id": 0})
        client.put(f"/api/figures/{fid}/default-prompt", json={"prompt_id": p["id"]})
        send(cid)
        assert system().startswith("Be Confucius")

        # New general default; the old default can then be deleted, deleting falls back.
        g = client.post("/api/prompts", json={"name": "Short", "text": "You are {name}."}).json()
        default_id = listed[0]["id"]
        assert client.delete(f"/api/prompts/{default_id}").status_code == 400
        client.post(f"/api/prompts/{g['id']}/make-default")
        assert client.delete(f"/api/prompts/{default_id}").json()["ok"]
        client.delete(f"/api/prompts/{p['id']}")  # figure default disappears → general default
        send(cid)
        assert system() == "You are Confucius."
        assert client.get("/api/prompts/builtin").json()["placeholders"] == ["name", "years", "description", "persona"]


def test_settings_can_be_edited_in_the_browser(cfg, tmp_path, monkeypatch):
    from histfig.config import load_config, save_config
    from histfig.server import api

    async def fake_models(base_url, api_key="", embedding=False):
        if "down" in base_url:
            raise RuntimeError("connection refused")
        return ["qwen/qwen3-embedding-4b"] if embedding else ["z-ai/glm-5.3-flash", "vendor/chat"]

    monkeypatch.setattr(api, "available_models", fake_models)
    cfg.chat.api_key = "sk-old"
    save_config(cfg, tmp_path)
    with make_client(cfg, tmp_path) as client:
        put = lambda body: client.put("/api/settings", json=body)

        # Unknown model: refused with suggestions, nothing written
        r = put({"chat": {"model": "glm-5.3-flash"}})
        assert r.status_code == 400 and "z-ai/glm-5.3-flash" in r.json()["detail"]
        assert load_config(tmp_path).chat.model == "fake-chat"

        # Valid model: saved to config.toml and used right away; the key is kept
        r = put({"chat": {"model": "vendor/chat", "temperature": 0.3}})
        assert r.status_code == 200, r.text
        saved = load_config(tmp_path)
        assert saved.chat.model == "vendor/chat" and saved.chat.temperature == 0.3 and saved.chat.api_key == "sk-old"
        assert client.get("/api/models").json()["default"] == "vendor/chat"
        assert "sk-old" not in r.text  # keys are only ever sent back masked

        # Embedding: same key as chat, prefixes follow the new model
        r = put({"embedding": {"provider": "openai_compatible", "base_url": "https://openrouter.ai/api/v1",
                               "model": "qwen/qwen3-embedding-4b"}, "same_key_as_chat": True})
        assert r.status_code == 200, r.text
        saved = load_config(tmp_path)
        assert saved.embedding.api_key == "" and saved.embedding_key() == "sk-old"  # shared, not copied
        assert saved.embedding.query_prefix.startswith("Instruct:")
        assert r.json()["same_key"]

        # Bad values are refused
        assert put({"chunking": {"chunk_size": 500, "overlap": 400}}).status_code == 400
        assert put({"retrieval": {"top_k": "many"}}).status_code == 400

        # Model list unreachable: saved anyway, with a warning
        r = put({"chat": {"provider": "openai_compatible", "base_url": "http://down.local/v1", "model": "whatever"}})
        assert r.status_code == 200 and r.json()["warnings"]
        assert load_config(tmp_path).chat.base_url == "http://down.local/v1"


def test_first_run_needs_setup(cfg, tmp_path):
    from histfig.config import Config

    with make_client(Config(), tmp_path) as client:
        problems = client.get("/api/settings").json()["problems"]
        assert "chat.model is empty" in problems and "embedding.model is empty" in problems


def test_models_for_conversations(cfg, tmp_path, monkeypatch):
    from histfig.config import load_config, save_config
    from histfig.server import api

    async def fake_models(base_url, api_key="", embedding=False):
        return ["fake-chat", "cheap/one", "fancy/two"]

    monkeypatch.setattr(api, "available_models", fake_models)
    save_config(cfg, tmp_path)
    chat = FakeChat()
    with make_client(cfg, tmp_path, chat=chat) as client:
        # "Browse models…" for the embedding model asks the provider's embedding list
        async def embedding_list(base_url, api_key="", embedding=False):
            return ["qwen/qwen3-embedding-4b"] if embedding else ["fake-chat"]

        monkeypatch.setattr(api, "available_models", embedding_list)
        assert client.get("/api/settings/embedding-models").json()["models"] == ["qwen/qwen3-embedding-4b"]
        monkeypatch.setattr(api, "available_models", fake_models)

        # Only real models can be added
        r = client.put("/api/settings", json={"chat": {"allowed_models": ["cheap/one", "nope"]}})
        assert r.status_code == 400 and "nope" in r.json()["detail"]
        r = client.put("/api/settings", json={"chat": {"allowed_models": ["cheap/one", "fancy/two", "cheap/one"]}})
        assert r.status_code == 200, r.text
        assert load_config(tmp_path).chat.allowed_models == ["cheap/one", "fancy/two"]  # duplicates dropped
        assert client.get("/api/models").json()["allowed"] == ["cheap/one", "fancy/two"]

        fid = client.post("/api/figures", json={"name": "X"}).json()["id"]
        cid = client.post(f"/api/figures/{fid}/conversations", json={"model": "fancy/two"}).json()["id"]
        assert client.patch(f"/api/conversations/{cid}", json={"model": "other/model"}).status_code == 400

        seen = []
        original = chat.stream

        async def spy(messages, model=None, temperature=None):
            seen.append(model)
            async for part in original(messages, model, temperature):
                yield part

        chat.stream = spy
        client.post(f"/api/conversations/{cid}/messages", json={"content": "Hi", "documents": "off"})
        # Removed from the list → the conversation falls back to the default model
        client.put("/api/settings", json={"chat": {"allowed_models": ["cheap/one"]}})
        client.post(f"/api/conversations/{cid}/messages", json={"content": "Hi", "documents": "off"})
        assert seen == ["fancy/two", "fake-chat"]


def test_same_key_is_the_default_and_follows_the_chat_key(cfg, tmp_path, monkeypatch):
    from histfig.config import load_config, save_config
    from histfig.server import api

    async def fake_models(base_url, api_key="", embedding=False):
        return ["fake-chat", "fake-embed"]

    monkeypatch.setattr(api, "available_models", fake_models)
    save_config(cfg, tmp_path)  # no keys at all yet
    with make_client(cfg, tmp_path) as client:
        assert client.get("/api/settings").json()["same_key"]  # ticked by default
        client.put("/api/settings", json={"chat": {"api_key": "sk-first"}})
        assert load_config(tmp_path).embedding_key() == "sk-first"
        client.put("/api/settings", json={"chat": {"api_key": "sk-second"}})  # changed later
        assert load_config(tmp_path).embedding_key() == "sk-second"
        assert load_config(tmp_path).embedding.api_key == ""  # nothing copied that could go stale

        # An embedding key of its own is kept, and the box is then unticked
        client.put("/api/settings", json={"embedding": {"api_key": "sk-embed"}})
        client.put("/api/settings", json={"chat": {"api_key": "sk-third"}})
        assert load_config(tmp_path).embedding_key() == "sk-embed"
        assert not client.get("/api/settings").json()["same_key"]

        # Ticking it again drops the own key: back to sharing
        client.put("/api/settings", json={"embedding": {}, "same_key_as_chat": True})
        assert load_config(tmp_path).embedding_key() == "sk-third"
        assert client.get("/api/settings").json()["same_key"]


def test_embedding_requests_use_the_shared_chat_key():
    import asyncio

    import httpx

    from histfig.config import Config
    from histfig.providers.embed import make_embedder

    cfg = Config()
    cfg.chat.api_key, cfg.embedding.model = "sk-chat", "e"
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    real = httpx.AsyncClient
    httpx.AsyncClient = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    try:
        asyncio.run(make_embedder(cfg.embedding, key=cfg.embedding_key).embed_query("x"))
        cfg.chat.api_key = "sk-new"  # changing the chat key takes effect immediately
        asyncio.run(make_embedder(cfg.embedding, key=cfg.embedding_key).embed_query("x"))
    finally:
        httpx.AsyncClient = real
    assert seen == ["Bearer sk-chat", "Bearer sk-new"]

# Agent search ----------------------------------------------------------------


def call(name, **args):
    return {"id": f"call-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def agent_ask(client, fid, question):
    cid = client.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
    events = sse_events(client.post(f"/api/conversations/{cid}/messages",
                                    json={"content": question, "documents": "agent"}).text)
    return cid, events


def with_documents(client):
    fid = client.post("/api/figures", json={"name": "Lu Xun"}).json()["id"]
    client.post(f"/api/figures/{fid}/documents", files=[("files", ("memoir.txt", RIVER.encode(), "text/plain"))])
    wait_ready(client, fid)
    return fid


def test_agent_search_researches_then_answers_from_chosen_passages(cfg, tmp_path):
    chat = FakeChat()
    with make_client(cfg, tmp_path, chat=chat) as client:
        fid = with_documents(client)
        target = client.app.state.hf.db.one("SELECT id, text FROM chunks WHERE text LIKE '%长江%' LIMIT 1")
        chat.script = [
            {"tool_calls": [call("search", query="childhood river")]},
            {"tool_calls": [call("find_text", text="长江|nothing")]},
            {"tool_calls": [call("read_around", passage=f"P{target['id']}")]},
            {"tool_calls": [call("finish", passages=[f"P{target['id']}"])]},
        ]
        cid, events = agent_ask(client, fid, "Where did you grow up?")
        steps = [e["text"] for e in events if e["type"] == "step"]
        assert steps[0].startswith("Searched “childhood river”") and "Looked for “长江|nothing”" in steps[1]
        assert steps[2].startswith("Read around memoir.txt, part")
        sources = next(e["sources"] for e in events if e["type"] == "sources")
        assert [h["chunk_id"] for h in sources] == [target["id"]]
        assert target["text"] in chat.last_messages[-1]["content"]  # the answer is written from it
        assert any(m["role"] == "tool" for m in chat.tool_messages)  # results went back to the model

        saved = client.get(f"/api/conversations/{cid}").json()["messages"][1]
        assert saved["steps"] == steps and [h["chunk_id"] for h in saved["sources"]] == [target["id"]]
        md = client.get(f"/api/conversations/{cid}/export").text
        assert "Research:\n\n1. Searched “childhood river”" in md and target["text"].splitlines()[0] in md


def test_agent_search_can_skip_documents(cfg, tmp_path):
    chat = FakeChat()
    with make_client(cfg, tmp_path, chat=chat) as client:
        fid = with_documents(client)
        chat.script = [{"content": "no search needed"}]
        _, events = agent_ask(client, fid, "Hello!")
        assert not [e for e in events if e["type"] == "step"]
        assert next(e["sources"] for e in events if e["type"] == "sources") == []
        assert events[-1]["type"] == "done" and chat.last_messages[-1]["content"] == "Hello!"


def test_agent_search_falls_back_without_tool_support(cfg, tmp_path):
    from histfig.providers.chat import ProviderError

    chat = FakeChat()
    with make_client(cfg, tmp_path, chat=chat) as client:
        fid = with_documents(client)
        chat.script = [ProviderError("HTTP 404: No endpoints found that support tool use")]
        _, events = agent_ask(client, fid, "Tell me about the river")
        assert any("used simple search" in e["message"] for e in events if e["type"] == "warning")
        assert next(e["sources"] for e in events if e["type"] == "sources")  # simple search found some
        assert events[-1]["type"] == "done"


def test_agent_search_stops_after_max_steps(cfg, tmp_path):
    cfg.retrieval.agent_steps = 3
    chat = FakeChat()
    with make_client(cfg, tmp_path, chat=chat) as client:
        fid = with_documents(client)
        chat.script = [{"tool_calls": [call("search", query=f"river {i}")]} for i in range(20)]
        _, events = agent_ask(client, fid, "Tell me about the river")
        assert len([e for e in events if e["type"] == "step"]) == cfg.retrieval.agent_steps
        sources = next(e["sources"] for e in events if e["type"] == "sources")
        assert 0 < len(sources) <= cfg.retrieval.top_k  # what it found, without a finish
        assert events[-1]["type"] == "done"


def test_find_text_and_read_around(cfg, tmp_path):
    from histfig import agent

    with make_client(cfg, tmp_path) as client:
        fid = with_documents(client)
        db = client.app.state.hf.db
        hits, total = agent.find_text(db, fid, "长江")
        assert total >= 3 and all("长江" in h["text"] for h in hits)
        assert agent.find_text(db, fid, "YANGTZE")[1] >= 1  # case-insensitive
        assert agent.find_text(db, fid, "(unbalanced [")[1] == 0  # plain text, not a regex
        assert agent.find_text(db, fid + 99, "长江") == ([], 0)  # other figures' documents stay out

        first = db.one("SELECT id FROM chunks WHERE figure_id=? ORDER BY idx LIMIT 1", (fid,))["id"]
        around = agent.read_around(db, fid, first)
        assert [h["chunk"] for h in around] == [0, 1]  # nothing before the first part
        assert agent.read_around(db, fid + 99, first) == []


# Backup and restore ----------------------------------------------------------


def test_backup_and_restore_elsewhere(cfg, tmp_path):
    import io
    import zipfile

    from histfig.config import load_config, save_config

    home, other = tmp_path / "home", tmp_path / "codespace"
    cfg.chat.api_key = "sk-secret"
    save_config(cfg, home)
    with make_client(cfg, home) as client:
        fid = client.post("/api/figures", json={"name": "鲁迅"}).json()["id"]
        client.post(f"/api/figures/{fid}/image", files={"file": ("p.png", PNG, "image/png")})
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("memoir.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)
        ask(client, fid, "Tell me about the river")
        r = client.get("/api/backup")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        assert re.search(r'filename="histfig-backup-\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.zip"',
                         r.headers["content-disposition"])
        archive = r.content
    names = zipfile.ZipFile(io.BytesIO(archive)).namelist()
    assert {"histfig.db", "config.toml"} <= set(names)
    assert any(n.startswith("uploads/") for n in names) and any(n.startswith("images/") for n in names)
    assert b"sk-secret" not in zipfile.ZipFile(io.BytesIO(archive)).read("config.toml")  # no keys in backups

    # Another HistFig (say, a new Codespace) with its own key and an older figure
    cfg.chat.api_key = "sk-mine"
    save_config(cfg, other)
    with make_client(cfg, other) as client:
        client.post("/api/figures", json={"name": "To be replaced"})
        r = client.post("/api/restore", files={"file": ("backup.zip", archive, "application/zip")})
        assert r.status_code == 200 and r.json()["figures"] == 1, r.text
        figs = client.get("/api/figures").json()
        assert [f["name"] for f in figs] == ["鲁迅"] and not figs[0]["needs_rebuild"]
        fid = figs[0]["id"]
        assert client.get(f"/api/figures/{fid}/image").status_code == 200
        conv = client.get(f"/api/figures/{fid}/conversations").json()[0]
        assert len(client.get(f"/api/conversations/{conv['id']}").json()["messages"]) == 2
        assert ask(client, fid, "Yangtze river")[0]  # search works on the restored index
        # the uploaded files moved along: rebuilding reads them from this data folder
        client.post(f"/api/figures/{fid}/rebuild")
        assert all(d["status"] == "ready" for d in wait_ready(client, fid))
        assert load_config(other).chat.api_key == "sk-mine"  # this computer's key is kept
        assert (other / "previous" / "histfig.db").exists()  # the replaced data, just in case


def test_restore_refuses_what_is_not_a_good_backup(cfg, tmp_path):
    import io
    import sqlite3
    import zipfile

    def zipped(files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return buf.getvalue()

    old_db = tmp_path / "old.db"
    conn = sqlite3.connect(old_db)
    conn.execute("PRAGMA user_version = 3")
    conn.close()
    with make_client(cfg, tmp_path / "data") as client:
        client.post("/api/figures", json={"name": "Keep me"})
        restore = lambda data: client.post("/api/restore", files={"file": ("b.zip", data, "application/zip")})
        cases = {
            b"not a zip": "not a .zip",
            zipped({"notes.txt": "hi"}): "no histfig.db",
            zipped({"histfig.db": "x", "../evil.txt": "x"}): "unsafe path",
            zipped({"histfig.db": "garbage" * 100}): "can't be read",
            zipped({"histfig.db": old_db.read_bytes()}): "different version",
        }
        for data, reason in cases.items():
            r = restore(data)
            assert r.status_code == 400 and reason in r.json()["detail"], (reason, r.text)
        assert [f["name"] for f in client.get("/api/figures").json()] == ["Keep me"]  # nothing changed
        assert not list((tmp_path / "data").glob(".restore-*"))  # nothing left behind


def test_documents_stored_with_absolute_paths_still_work(cfg, tmp_path):
    """Older databases stored each file's full path; the file is found in this data folder."""
    from histfig.db import Database

    with make_client(cfg, tmp_path) as client:
        fid = client.post("/api/figures", json={"name": "Old"}).json()["id"]
        client.post(f"/api/figures/{fid}/documents", files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        wait_ready(client, fid)
        db = Database(tmp_path / "histfig.db")
        db.execute("UPDATE documents SET path = '/somewhere/else/data/uploads/' || figure_id || '/' || "
                   "replace(path, figure_id || '/', '')")
        assert db.one("SELECT path FROM documents")["path"].startswith("/somewhere/else")
        client.post(f"/api/figures/{fid}/rebuild")
        assert wait_ready(client, fid)[0]["status"] == "ready"


def test_settings_save_both_models_together_or_neither(cfg, tmp_path, monkeypatch):
    """The Settings page saves all changed cards in one request: all of it, or nothing."""
    from histfig.config import load_config, save_config
    from histfig.server import api

    async def fake_models(base_url, api_key="", embedding=False):
        return ["good/embed"] if embedding else ["fake-chat", "new/chat"]

    monkeypatch.setattr(api, "available_models", fake_models)
    save_config(cfg, tmp_path)
    with make_client(cfg, tmp_path) as client:
        both = lambda embed: client.put("/api/settings", json={
            "chat": {"model": "new/chat"}, "embedding": {"model": embed}, "same_key_as_chat": True,
            "chunking": {"chunk_size": 800, "overlap": 100}})
        r = both("missing/embed")
        assert r.status_code == 400 and "missing/embed" in r.json()["detail"]
        saved = load_config(tmp_path)
        assert saved.chat.model == "fake-chat" and saved.chunking.chunk_size == 100  # nothing half-saved
        assert both("good/embed").status_code == 200
        saved = load_config(tmp_path)
        assert (saved.chat.model, saved.embedding.model, saved.chunking.chunk_size) == ("new/chat", "good/embed", 800)
