# HistFig Portable: plan

## Context
Today's histfig (`./histfig/`, FastAPI + ChromaDB) is built as a hosted server. An admin with a password uploads texts, many users chat through in-memory sessions with rate limits, and config lives in env vars. The new version is **single-user and local**. Someone clones the repo, runs a simple wizard that can be re-run later (provider, embedding model, generative model), opens `http://localhost:8000`, creates figures, uploads txt/pdf/docx, and chats with RAG. It must work on Windows, macOS, Linux and GitHub Codespaces. It is a **clean rewrite**: we take ideas from the old code but not its structure, and we fix the known bugs along the way.

## Key decisions
- **Python 3.11+, managed with `uv`.** uv works on Windows, macOS and Linux and gives one lockfile. `pip install -e .` stays as a fallback.
- **Config is one readable `config.toml`** in `./data/` (gitignored). The wizard writes it from a commented template and the user can also edit it by hand. OpenRouter is the default API. An API key can be written directly into the file, or the file can name an env var to read it from (`api_key_env = "OPENROUTER_API_KEY"`), which suits Codespaces secrets.
- **Everything lives in one SQLite file**, `data/histfig.db`: figures, documents, chunks, embeddings (float32 BLOBs) and conversations. Vector search is brute-force cosine in numpy, loaded per figure and cached in memory.
  - A figure's corpus is usually up to tens of thousands of chunks, so a search takes milliseconds.
  - This drops ChromaDB, which is heavy and fragile on Windows. Backing up means copying `data/`.
- **Providers:** the old code already covers both "local" and OpenAI-compatible APIs through one client, because Ollama serves an OpenAI-compatible `/v1` API.
  - Generation: `ollama` or `openai_compatible` (OpenAI, OpenRouter, LM Studio, vLLM and similar).
  - Embeddings: `ollama`, `openai_compatible`, or `sentence_transformers`. The last is an optional extra (`uv sync --extra local`) so that users who don't need it never install torch.
- **Each figure records the embedding model and vector size it was built with.** If the configured model changes, the UI marks the figure as "needs re-embedding" and offers a button for it, so vectors from different models never get mixed.
- **Keep hybrid retrieval** (BM25 + vector, merged with reciprocal rank fusion) and the jieba/English tokenisation, which matter for Chinese texts. The BM25 index is rebuilt in memory from stored tokens, with no pickle files.
- **Frontend uses vanilla JS with no build step**, served by FastAPI. Admin and chat become one app with no logins.

## Layout
```
pyproject.toml            deps: fastapi, uvicorn, httpx, numpy, rank-bm25, jieba, pypdf,
                          python-docx, nltk(optional lemmatiser); extra "local": sentence-transformers
.devcontainer/devcontainer.json   installs uv, runs `uv sync`, forwards port 8000
src/histfig/
  __main__.py, cli.py     `histfig` (serve; runs setup first if no config), `histfig setup`, `histfig doctor`
  config.py               load/validate config.toml, save it via a commented template (dataclasses, tomllib)
  wizard.py               plain input() prompts, only existing values as defaults, checks both models
  db.py                   sqlite3 (WAL), schema + `PRAGMA user_version` migrations
  providers/chat.py       async httpx streaming of /chat/completions; list_models (/v1/models, Ollama /api/tags)
  providers/embed.py      common interface `embed(list[str]) -> np.ndarray`; 3 backends; query/doc prefixes per model
  ingest/extract.py       txt (utf-8-sig → utf-16 → gb18030 → cp1252 → latin-1), pdf (pypdf), docx (paragraphs + tables)
  ingest/chunk.py         character chunking that respects CJK sentence ends and paragraphs; size/overlap from config
  ingest/jobs.py          background ingestion queue, resumable, with progress events
  retrieval/tokenize.py   jieba + stopwords (ported from data/stopwords/)
  retrieval/search.py     vector top-k, BM25 top-k, RRF fusion, threshold applied after fusion
  prompts.py              persona system prompt, RAG user-turn template
  server/app.py + routes_{figures,documents,chat,settings}.py
  static/ index.html, app.js, style.css (hash-routed SPA)
tests/
```
Move the old code to `reference/histfig-original/` (or delete it once the port is done) so that it doesn't shadow the `histfig` package name.

## Data model
- `figures(id, name, description, persona_prompt, birth_year, death_year, image, embed_provider, embed_model, embed_dim, created_at)`. Names are free text, Chinese included. Ids are integers, which fixes the old letters-only rule.
- `documents(id, figure_id, filename, file_type, sha256, char_count, status[pending|processing|ready|error], error, created_at)`. The same file uploaded twice to one figure is skipped by matching sha256.
- `chunks(id, document_id, figure_id, idx, text, start_char, end_char, tokens_json, embedding BLOB NULL)`
- `conversations(id, figure_id, title, model, created_at, updated_at)`
- `messages(id, conversation_id, role, content, sources_json, created_at)`

## Ingestion flow
1. Upload (multipart, several files at once): save to `data/uploads/`, insert a `documents` row with status `pending`, and return right away.
2. A worker (one asyncio task) for each document runs: extract → chunk → tokenise → insert chunks with `embedding = NULL`. It then embeds chunks in batches of `embedding.batch_size` from the config (default 16; 1 sends "one by one"). Each batch is committed as soon as its vectors arrive.
   - Retries with backoff on 429/5xx errors.
   - sentence-transformers runs via `asyncio.to_thread`.
3. Progress goes to the UI through `GET /api/figures/{id}/jobs` (SSE).
   - When the server restarts, any chunks with `embedding IS NULL` are picked up again, so an interrupted upload resumes on its own.
4. When a document finishes: mark it `ready` and clear that figure's cached vectors and BM25 index.

## Retrieval + chat
- `POST /api/conversations/{id}/messages` streams SSE events in the order `sources` → `content`… → `done` or `error`, and saves both the user and assistant messages.
- Retrieval steps:
  1. Embed the query, with the query prefix if the model needs one.
  2. Take the vector top-N and the BM25 top-N.
  3. Merge with RRF (k=60).
  4. Drop results under `min_similarity` (applied after fusion, so BM25-only hits can survive with a weaker cutoff), then take the top-k (k is set in the UI).
- Prompt: the persona system prompt, the history (last N turns from the DB), and the current user turn with retrieved passages formatted as `[filename §chunk]`. Passages are never saved into history.
- Options: query rewriting (off by default) and hiding `<think>` content (shown collapsed in the UI). The generation model can be switched for each conversation from the models the provider lists.

## UI pages
- **Figures:** a grid of figures plus a create form.
- **Figure detail:** edit the persona and portrait; drag-and-drop upload with progress bars; a document list (status, chunk count, delete); a re-embed button.
- **Chat:** a sidebar with conversations for the figure (new, rename, delete), the streaming chat, a sources panel with click-to-expand passages, and Markdown/PDF export.
- **Settings:** a read-only view of the config, "Test connection" buttons, and the path to config.toml with a note saying to re-run `histfig setup` or edit the file and restart.

## Fixes from the old code
- The local embedding model was loaded at warmup even when external embeddings were configured. Models are now loaded lazily.
- Chunks were embedded and inserted one at a time. Both now happen in batches.
- When no vector hit passed the similarity threshold, BM25 was skipped entirely. Fusion now always runs.
- BM25 looked up each hit in the database separately. Lookups are now batched.
- Defaults disagreed between the code and `.env.example` (similarity threshold, query rewriting), and `CHUNK_SIZE_WORDS` was never used. There is now one config with one set of defaults.
- The `.env` export in `start.sh` broke on inline comments. It is replaced by TOML.
- PyPDF2 is replaced by pypdf, its maintained successor. Text-file decoding now tries GB18030 for Chinese.
- Chat history was lost on page reload. It is now saved in SQLite.

## Cross-platform notes
- Use `pathlib` everywhere and no shell scripts. Read and write files as UTF-8 explicitly, since Windows otherwise defaults to cp1252.
- Bind to `127.0.0.1` by default. Codespaces forwards that automatically. `histfig serve` opens the browser unless `CODESPACES` is set or `--no-browser` is passed.
- The config template explains how to install Ollama and pull models. The README tells Codespaces users to use an OpenAI-compatible API, since there is no GPU.

## Milestones
1. Package skeleton, config, wizard, `doctor` (tests the providers).
2. Database, extract/chunk, ingestion worker, figure/document API.
3. Retrieval (vector, BM25, RRF) and a CLI search command for debugging.
4. Chat streaming and conversation persistence.
5. Frontend.
6. Devcontainer, README (quickstart for each OS), GitHub Actions running pytest on Windows, macOS and Linux.

## Verification
- `pytest` unit tests:
  - chunker: CJK and English text, overlap, boundary snapping
  - extractors: sample txt in each encoding, plus pdf and docx
  - RRF and BM25
  - config round-trip
  - db migrations
- Integration test: run the ingestion and chat endpoints against a fake OpenAI-compatible server (a small FastAPI stub, so no network is needed). Covers the full path: upload → embed → search → streamed answer → saved message.
- Manual checks:
  - macOS with Ollama (`nomic-embed-text` / `qwen2.5`)
  - Codespaces with an OpenAI key
  - Windows with sentence-transformers
  - In each: create a figure, upload a Chinese PDF and an English docx, kill the server mid-upload, restart, confirm the upload resumes, then chat and check the sources.
