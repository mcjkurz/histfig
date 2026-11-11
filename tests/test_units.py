import io
import zlib

import pytest

from histfig.config import Config, load_config, save_config, suggested_prefixes
from histfig.db import Database
from histfig.ingest.chunk import chunk_text, measure, normalise
from histfig.ingest.extract import ExtractionError, decode_text, extract_text, file_type
from histfig.retrieval.search import rrf
from histfig.retrieval.tokenize import tokenize

# ------------------------------------------------------------------ chunking

EN = " ".join(f"This is sentence number {i}, which talks about rivers and mountains." for i in range(60))
ZH = "".join(f"这是第{i}句话，讲的是山川与河流。" for i in range(120))


@pytest.mark.parametrize("text", [EN, ZH])
def test_chunks_cover_text_with_bounded_size(text):
    chunks = chunk_text(text, size=300, overlap=50)
    norm = normalise(text)
    assert len(chunks) > 3
    assert all(measure(c.text) <= 300 for c in chunks)
    assert chunks[0].start == 0 and chunks[-1].end == len(norm)
    for a, b in zip(chunks, chunks[1:]):
        assert b.start <= a.end, "no gaps between chunks"
        assert b.start > a.start, "always progresses"


def test_chunks_end_on_sentence_boundaries():
    for c in chunk_text(ZH, size=300, overlap=50)[:-1]:
        assert c.text.endswith("。")
    for c in chunk_text(EN, size=300, overlap=50)[:-1]:
        assert c.text.endswith(".")


def test_chunks_prefer_paragraphs():
    text = ("A" * 450 + ".\n\n") + ("B" * 450 + ".")
    chunks = chunk_text(text, size=250, overlap=0)
    assert chunks[0].text == "A" * 450 + "."
    assert chunks[1].text.startswith("B")


def test_chunk_without_any_break_is_hard_cut():
    assert [len(c.text) for c in chunk_text("字" * 1000, size=300, overlap=0)] == [300, 300, 300, 100]
    assert [len(c.text) for c in chunk_text("x" * 1000, size=300, overlap=0)] == [900, 100]


def test_size_counts_a_character_as_three_letters():
    assert measure("长江") == 2 and measure("river") == 5 / 3 and measure("长江 river") == 4
    assert measure("「你好。」") == 5  # full-width punctuation counts like a character
    en = chunk_text(EN * 5, size=300, overlap=0)[0].text
    zh = chunk_text(ZH * 5, size=300, overlap=0)[0].text
    assert 600 < len(en) <= 900 and 250 < len(zh) <= 330  # similar content, not similar length


def test_short_and_empty_text():
    assert chunk_text("", 300, 50) == []
    assert [c.text for c in chunk_text("  Hello.  ", 300, 50)] == ["Hello."]


# ------------------------------------------------------------------ extraction


def test_file_types():
    assert file_type("a.TXT") == "txt" and file_type("b.pdf") == "pdf"
    assert file_type("c.docx") == "docx" and file_type("d.exe") is None


SIMPLIFIED = "天下兴亡，匹夫有责。这是一段比较长的中文文本，用来测试编码检测是否可靠。" * 3
TRADITIONAL = "天下興亡，匹夫有責。這是一段比較長的中文文本，用來測試編碼檢測是否可靠。" * 3


@pytest.mark.parametrize("encoding,text", [
    ("utf-8", SIMPLIFIED), ("utf-8-sig", SIMPLIFIED), ("utf-16", SIMPLIFIED),
    ("gb18030", SIMPLIFIED), ("big5", TRADITIONAL),
])
def test_decode_chinese_encodings(encoding, text):
    assert decode_text(text.encode(encoding)) == text


def test_decode_cp1252():
    text = "Café crème, naïve façade — déjà vu. " * 5
    assert decode_text(text.encode("cp1252")) == text


def test_extract_docx():
    import docx

    d = docx.Document()
    d.add_paragraph("First paragraph.")
    d.add_paragraph("第二段。")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "cell A", "cell B"
    buf = io.BytesIO()
    d.save(buf)
    text = extract_text(buf.getvalue(), "docx")
    assert "First paragraph." in text and "第二段。" in text and "cell A | cell B" in text


def minimal_pdf(text: str) -> bytes:
    stream = zlib.compress(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>stream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def test_extract_pdf():
    assert "Hello from a PDF" in extract_text(minimal_pdf("Hello from a PDF"), "pdf")


def test_extract_empty_raises():
    with pytest.raises(ExtractionError):
        extract_text(b"   ", "txt")


# ------------------------------------------------------------------ retrieval


def test_tokenize_mixed():
    tokens = tokenize("The Yellow River 黄河流经中国北方。")
    assert "yellow" in tokens and "river" in tokens and "黄河" in tokens
    assert "the" not in tokens and "。" not in tokens


def test_tokenize_stems_english_and_adds_word_pairs():
    tokens = tokenize("The rivers flow. Lu Xun's iron house; a house of cards.")
    assert {"river", "flow", "lu", "xun", "iron", "hous"} <= set(tokens)
    assert "s" not in tokens  # from "Xun's"
    assert "river_flow" in tokens and "lu_xun" in tokens and "iron_hous" in tokens
    assert "flow_lu" not in tokens  # not across a full stop
    assert not any(t.startswith("hous_") and "card" in t for t in tokens)  # not across "of"
    assert set(tokenize("river")) <= set(tokens)  # "river" finds "rivers"
    assert "长江_童年" in tokenize("长江童年")


def test_migration_recomputes_stored_keywords(tmp_path):
    from histfig.db import retokenize

    db = Database(tmp_path / "h.db")
    db.execute("INSERT INTO figures (name, created_at) VALUES ('F', 'x')")
    db.execute("INSERT INTO documents (figure_id, filename, file_type, sha256, path, created_at) "
               "VALUES (1, 'a.txt', 'txt', 'h', 'p', 'x')")
    db.execute("INSERT INTO chunks (document_id, figure_id, idx, text, start_char, end_char, tokens) "
               "VALUES (1, 1, 0, 'The rivers flow.', 0, 16, '[\"rivers\"]')")
    with db.connect() as conn:
        retokenize(conn)
    assert "river_flow" in db.one("SELECT tokens FROM chunks")["tokens"]


def test_rrf_prefers_items_in_both_lists():
    scores = rrf([[1, 2, 3], [3, 4, 1]], k=60)
    ranked = sorted(scores, key=scores.get, reverse=True)
    assert ranked[:2] == [1, 3]


# ------------------------------------------------------------------ config + db


def test_config_round_trip_keeps_comments(tmp_path):
    c = Config()
    c.chat.model = "m"
    c.embedding.model = "qwen/qwen3-embedding-4b"
    c.embedding.query_prefix, c.embedding.document_prefix = suggested_prefixes(c.embedding.model)
    c.embedding.api_key = 'odd "key" \\ ü'
    path = save_config(c, tmp_path)
    assert "# HistFig configuration" in path.read_text(encoding="utf-8")
    loaded = load_config(tmp_path)
    assert loaded == c
    assert loaded.validate() == []


def test_default_api_is_openrouter():
    c = Config()
    assert c.chat.base_url == c.embedding.base_url == "https://openrouter.ai/api/v1"


def test_wizard_fresh_setup(tmp_path, monkeypatch):
    from histfig import wizard

    answers = iter([
        "",                          # chat service: 1 = OpenRouter (default)
        "sk-test",                   # API key
        "",                          # model is required: empty is refused...
        "chat",                      # ...unknown model: refused, "vendor/chat" suggested...
        "",                          # ...and Enter accepts the suggestion
        "",                          # embedding service: OpenRouter
        "",                          # same API key as chat? yes
        "qwen/qwen3-embedding-4b",   # embedding model
        "", "",                      # chunking defaults
    ])
    async def fake_list(base_url, api_key="", embedding=False):
        return ["qwen/qwen3-embedding-4b"] if embedding else ["other/x", "vendor/chat"]

    monkeypatch.setattr(wizard, "fetch_models", fake_list)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    cfg = wizard.run_wizard(tmp_path)
    assert cfg.chat.base_url == "https://openrouter.ai/api/v1" and cfg.chat.model == "vendor/chat"
    assert cfg.embedding.api_key == "sk-test" and cfg.embedding.query_prefix.startswith("Instruct:")
    assert load_config(tmp_path) == cfg


def test_config_tolerates_partial_and_unknown_keys(tmp_path):
    (tmp_path / "config.toml").write_text('[chat]\nmodel = "x"\nbogus = 1\n[embedding]\nbatch_size = "8"\n',
                                          encoding="utf-8")
    c = load_config(tmp_path)
    assert c.chat.model == "x" and c.embedding.batch_size == 8 and c.server.port == 8000


def test_prefix_suggestions():
    assert suggested_prefixes("nomic-embed-text")[0] == "search_query: "
    assert suggested_prefixes("intfloat/multilingual-e5-small") == ("query: ", "passage: ")
    assert suggested_prefixes("text-embedding-3-small") == ("", "")


def test_db_migrates_once(tmp_path):
    Database(tmp_path / "x.db")
    db = Database(tmp_path / "x.db")  # second open must not re-run the schema
    from histfig.db import MIGRATIONS

    assert db.one("PRAGMA user_version")["user_version"] == len(MIGRATIONS)


def test_usage_parsing():
    from histfig.providers.embed import _usage

    u = _usage({"prompt_tokens": 6, "total_tokens": 6, "cost": 1.2e-07})
    assert u.tokens == 6 and u.cost == 1.2e-07
    assert _usage(None).tokens == 0 and _usage({"total_tokens": "x"}).tokens == 0


@pytest.mark.parametrize("birth,death,shown", [
    ("1881", "1936", " (1881–1936)"),
    ("-551", "-479", " (551–479 BC)"),
    ("-4", "65", " (4 BC–AD 65)"),
    ("", "1936", " (?–1936)"),
    ("0", "0", " (0–0)"),
    ("", "", ""),
])
def test_years_in_prompt(birth, death, shown):
    from histfig.prompts import years

    assert years(birth, death) == shown


def test_previous_server_detection(tmp_path):
    import json
    import os

    import socket

    from histfig import running

    with socket.socket() as sock:  # a port nobody listens on (port may be a real HistFig)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    assert running.previous_server(tmp_path, port) is None          # no file
    running.write_pid(tmp_path, port)
    assert running.previous_server(tmp_path, port) is None          # that's us, not a previous server
    (tmp_path / "histfig.pid").write_text(json.dumps({"pid": 999999, "port": port}))
    assert running.previous_server(tmp_path, port) is None          # dead process
    (tmp_path / "histfig.pid").write_text("garbage")
    assert running.previous_server(tmp_path, port) is None
    running.write_pid(tmp_path, port)
    running.remove_pid(tmp_path)
    assert not (tmp_path / "histfig.pid").exists()
    assert running.alive(os.getpid())


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="uses SIGSTOP")
def test_stop_a_suspended_server():
    import signal
    import socket
    import subprocess
    import sys
    import time

    from histfig import running

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    code = (f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); "
            "print('ready', flush=True); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
        proc.send_signal(signal.SIGSTOP)  # like pressing Ctrl+Z
        time.sleep(0.2)
        assert not running.port_free("127.0.0.1", port)
        assert running.stop(proc.pid, "127.0.0.1", port, timeout=3)
        assert running.port_free("127.0.0.1", port)
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="TIME_WAIT behaviour differs on Windows")
def test_port_free_right_after_a_server_stops():
    """Connections still closing after a stop (TIME_WAIT) must not block a restart."""
    import socket

    from histfig import running

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen()
    client = socket.create_connection(("127.0.0.1", port))
    conn, _ = server.accept()
    conn.close()      # the server side closes first → TIME_WAIT on the server's port
    server.close()
    assert running.port_free("127.0.0.1", port)
    client.close()

    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    assert not running.port_free("127.0.0.1", busy.getsockname()[1])  # a real listener still counts
    busy.close()



@pytest.mark.parametrize("text,title", [
    ("Tell me about the river", "Tell me about…"),
    ("Hello", "Hello"),
    ("What do you think?", "What do you…"),
    ("  lots   of   spaces  ", "lots of spaces"),
    ("Pneumonoultramicroscopic question", "Pneumonoultramic…"),
    ("你好，最近怎么样？我想问你一些关于狂人日记的问题", "你好，最近怎么样？我想问你一些关…"),
])
def test_short_conversation_titles(text, title):
    from histfig.server.api import short_title

    assert short_title(text) == title


def test_passages_are_numbered_for_citations():
    from histfig.prompts import user_message

    hit = {"filename": "a.txt", "chunk": 0, "text": "The river."}
    msg = user_message("Where?", [hit, {**hit, "chunk": 1}])
    assert "[1] (a.txt, part 1)" in msg and "[2] (a.txt, part 2)" in msg
    assert "square brackets" in msg  # asked to cite them as [n]
    assert user_message("Hello", []) == "Hello"  # no passages: no citation instructions
