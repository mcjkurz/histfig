# HistFig Portable: status

Last updated: 2026-11-09. The design is in [PLAN.md](PLAN.md) and user docs are in [README.md](README.md).

## State
**First complete version.** Milestones 1–6 are built and `pytest` passes 26 tests.

Verified:
- The backend works end to end over real HTTP against a stub OpenAI-compatible server. That covered `doctor`, upload, batched embedding, hybrid search, the streamed chat, and saved history with `<think>` stripped.
- A fresh `uv sync` from `uv.lock` installs everything, and the tests pass in that environment.

Not yet verified:
- **The browser UI has not been looked at.** The JS passes `node --check`, but no page has been loaded.
- **No real models yet.** Nothing has been tested with real Ollama or OpenAI models, or on Windows or Codespaces.
- The CI workflow has never run, because the project isn't a git repo yet.

The old code is in `reference/histfig-original/`.

## What exists
| Area | Files |
|---|---|
| CLI, settings and wizard | Settings are edited in the browser (`PUT /api/settings`, applied live, saved to `config.toml`); `cli.py` (`histfig [serve]`, `setup`, `doctor`; `--data-dir` or `$HISTFIG_DATA`), `wizard.py` (simple and re-runnable: OpenRouter / Ollama / other API, no pre-filled suggestions, fills in known embedding prefixes, checks both models). `config.toml` is written from a commented template, so the comments survive saves |
| Config | `config.py`, which reads `data/config.toml` |
| Storage | `db.py`: SQLite with WAL and migrations via `user_version` |
| Providers | `providers/chat.py` (OpenAI-compatible streaming, which also covers Ollama `/v1`), `providers/embed.py` (HTTP or sentence-transformers) |
| Ingestion | `ingest/extract.py`, `ingest/chunk.py`, `ingest/jobs.py` (a background queue that resumes after a restart, with batched embedding and the model-mismatch guard) |
| Retrieval | `retrieval/tokenize.py` (jieba plus stopwords), `retrieval/bm25.py`, `retrieval/search.py` (vector + BM25 merged with RRF) |
| Server | `server/app.py` (factory; providers can be injected for tests), `server/api.py` (figures, portraits, documents, rebuild, search, conversations with an SSE chat, Markdown export, settings and connection test) |
| UI | `static/` (vanilla JS with hash routing): figures grid; figure page with drag-and-drop upload, progress, retrieval test and rebuild; chat with conversation sidebar, sources panel, collapsible thinking and per-conversation model; settings page |
| Packaging | `pyproject.toml`, `uv.lock`, `.devcontainer/`, `.github/workflows/tests.yml` (Linux, macOS and Windows × Python 3.11 and 3.13) |

## Decisions made while building
- **rank_bm25 replaced by our own `bm25.py`.** Okapi IDF goes negative when a word appears in most passages, which is common in one author's corpus, and that hid real matches. Lucene IDF stays positive.
- **Legacy encodings.** charset-normalizer, preferring cp1252 when the text is ambiguous Latin; GB18030 and Big5 are detected correctly.
- **No upload SSE.** The UI polls the document list every 1.5 seconds while work is running.
- **Markdown export only**, no PDF. NLTK is dropped.
- **"Rebuild index"** both re-chunks and re-embeds, so it applies new chunking settings too.
- When the embedding model doesn't match, chat and search fall back to keyword search with a warning, and new uploads to that figure fail until it is rebuilt.

## Next steps
1. **Check the UI in a browser:** `uv run histfig`, then create a figure, upload, chat and stop mid-answer. Fix whatever looks off.
2. **Test with real models:** Ollama (`qwen2.5:7b` + `nomic-embed-text`) and one API provider. Check that the persona prompts in `prompts.py` give good answers.
3. **`git init`, push, and watch CI** on all three operating systems, especially Windows file paths and SQLite.
4. **Try a Codespace.** Check the devcontainer setup with `uv` and the forwarded port.
5. **Possible additions:**
   - a "regenerate answer" button (the API `DELETE /conversations/{id}/messages/last` already exists)
   - query rewriting (the old `query_augmentation`)
   - PDF export
   - import/export of a figure as a zip, for sharing figures between users
   - OCR hint for scanned PDFs
