"""Public (read-only) mode: `histfig serve --public`."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from histfig.db import Database
from histfig.server.app import create_app
from histfig.server.public import COOKIE, delete_old_visitor_conversations
from tests.conftest import FakeChat, FakeEmbedder
from tests.test_app import PNG, RIVER, sse_events, wait_ready


def owner_client(cfg, tmp_path):
    return TestClient(create_app(cfg, tmp_path, FakeEmbedder(), FakeChat(), prefetch_models=False))


def public_client(cfg, tmp_path):
    return TestClient(create_app(cfg, tmp_path, FakeEmbedder(), FakeChat(), prefetch_models=False, public=True))


def prepared(cfg, tmp_path):
    """The owner sets up a figure with a document and a prompt, then locks the server."""
    with owner_client(cfg, tmp_path) as owner:
        fid = owner.post("/api/figures", json={"name": "Li Bai"}).json()["id"]
        owner.post(f"/api/figures/{fid}/documents", files=[("files", ("a.txt", RIVER.encode(), "text/plain"))])
        wait_ready(owner, fid)
        pid = owner.post("/api/prompts", json={"name": "Poet", "text": "You are {name}.", "figure_id": fid}).json()["id"]
        own_conv = owner.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
    return fid, pid, own_conv


def test_public_server_is_read_only(cfg, tmp_path):
    fid, pid, _ = prepared(cfg, tmp_path)
    with public_client(cfg, tmp_path) as c:
        assert c.get("/api/info").json() == {"public": True}
        refused = [
            c.post("/api/figures", json={"name": "X"}),
            c.put(f"/api/figures/{fid}", json={"name": "X"}),
            c.delete(f"/api/figures/{fid}"),
            c.post(f"/api/figures/{fid}/image", files={"file": ("p.png", PNG, "image/png")}),
            c.post(f"/api/figures/{fid}/image-url", json={"url": "https://example.org/p.png"}),
            c.post(f"/api/figures/{fid}/documents", files=[("files", ("b.txt", b"text", "text/plain"))]),
            c.delete("/api/documents/1"),
            c.post("/api/documents/1/retry"),
            c.post(f"/api/figures/{fid}/rebuild"),
            c.post("/api/prompts", json={"name": "X", "text": "X"}),
            c.put(f"/api/prompts/{pid}", json={"name": "X", "text": "X"}),
            c.delete(f"/api/prompts/{pid}"),
            c.post(f"/api/prompts/{pid}/make-default"),
            c.put(f"/api/figures/{fid}/default-prompt", json={"prompt_id": pid}),
            c.get("/api/settings"),
            c.put("/api/settings", json={"chat": {"model": "x"}}),
            c.post("/api/settings/test/chat"),
            c.get("/api/settings/embedding-models"),
        ]
        assert [r.status_code for r in refused] == [403] * len(refused)
        # Reading is fine
        assert c.get("/api/figures").status_code == 200
        assert c.get(f"/api/prompts?figure_id={fid}").status_code == 200
    with owner_client(cfg, tmp_path) as owner:  # and nothing changed
        assert owner.get(f"/api/figures/{fid}").json()["name"] == "Li Bai"


def test_visitors_have_their_own_conversations(cfg, tmp_path):
    fid, pid, own_conv = prepared(cfg, tmp_path)
    with public_client(cfg, tmp_path) as c:
        # Visitor A chats; the cookie identifies them
        cid = c.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
        visitor_a = c.cookies.get(COOKIE)
        assert visitor_a and len(visitor_a) == 32
        events = sse_events(c.post(f"/api/conversations/{cid}/messages", json={"content": "Hi"}).text)
        assert events[-1]["type"] == "done"
        assert c.patch(f"/api/conversations/{cid}", json={"prompt_id": pid}).status_code == 200  # may switch prompt
        assert c.patch(f"/api/conversations/{cid}", json={"model": "expensive/model"}).status_code == 400
        assert c.post(f"/api/figures/{fid}/conversations", json={"model": "expensive/model"}).status_code == 400
        assert [x["id"] for x in c.get(f"/api/figures/{fid}/conversations").json()] == [cid]  # not the owner's

        # Visitor B sees nothing of A's, and can't open, change or delete it
        c.cookies.clear()
        assert c.get(f"/api/figures/{fid}/conversations").json() == []
        assert c.get(f"/api/conversations/{cid}").status_code == 404
        assert c.patch(f"/api/conversations/{cid}", json={"title": "mine now"}).status_code == 404
        assert c.delete(f"/api/conversations/{cid}").status_code == 404
        assert c.post(f"/api/conversations/{cid}/messages", json={"content": "Hi"}).status_code == 404
        assert c.get(f"/api/conversations/{own_conv}").status_code == 404  # nor the owner's

        # A comes back (same browser) and finds the conversation
        c.cookies.set(COOKIE, visitor_a)
        assert c.get(f"/api/conversations/{cid}").json()["messages"][0]["content"] == "Hi"

    with owner_client(cfg, tmp_path) as owner:  # the owner's own list stays separate
        assert [x["id"] for x in owner.get(f"/api/figures/{fid}/conversations").json()] == [own_conv]


def test_messages_per_hour(cfg, tmp_path):
    fid, _, _ = prepared(cfg, tmp_path)
    cfg.public.messages_per_hour = 2
    with public_client(cfg, tmp_path) as c:
        cid = c.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
        send = lambda: c.post(f"/api/conversations/{cid}/messages", json={"content": "Hi", "documents": "off"})
        assert send().status_code == 200 and send().status_code == 200
        third = send()
        assert third.status_code == 429 and "2 messages" in third.json()["detail"]
        c.cookies.clear()  # another visitor has their own allowance
        cid2 = c.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
        assert c.post(f"/api/conversations/{cid2}/messages", json={"content": "Hi", "documents": "off"}).status_code == 200


def test_old_visitor_conversations_are_deleted(cfg, tmp_path):
    fid, _, own_conv = prepared(cfg, tmp_path)
    with public_client(cfg, tmp_path) as c:
        old = c.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
        recent = c.post(f"/api/figures/{fid}/conversations", json={}).json()["id"]
    db = Database(tmp_path / "histfig.db")
    long_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(timespec="seconds")
    db.execute("UPDATE conversations SET updated_at=? WHERE id IN (?, ?)", (long_ago, old, own_conv))
    assert delete_old_visitor_conversations(db, keep_days=14) == 1
    remaining = {r["id"] for r in db.all("SELECT id FROM conversations")}
    assert old not in remaining and recent in remaining and own_conv in remaining  # the owner's are kept
    assert delete_old_visitor_conversations(db, keep_days=0) == 0  # 0 = keep forever


def test_visitors_choose_from_the_owners_model_list(cfg, tmp_path):
    fid, _, _ = prepared(cfg, tmp_path)
    cfg.chat.allowed_models = ["cheap/one"]
    with public_client(cfg, tmp_path) as c:
        models = c.get("/api/models").json()
        assert models["allowed"] == ["cheap/one"] and models["models"] == []  # no full provider list for visitors
        cid = c.post(f"/api/figures/{fid}/conversations", json={"model": "cheap/one"}).json()["id"]
        assert c.get(f"/api/conversations/{cid}").json()["model"] == "cheap/one"
        assert c.patch(f"/api/conversations/{cid}", json={"model": "expensive/two"}).status_code == 400
