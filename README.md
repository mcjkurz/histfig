# HistFig

Chat with historical figures, grounded in their own writings — running on your own computer.

You create a *figure* (say, Lu Xun or Mary Wollstonecraft), upload their texts
(**txt, md, pdf, docx**), and HistFig splits them into passages, turns each passage into a
vector with an embedding model, and stores everything in a local database. When you ask a
question, the most relevant passages are retrieved and given to a language model, which
answers in the figure's voice. Every answer shows the passages it was based on.

Everything (settings, database, uploaded files, conversations) lives in the `data/` folder.

> The older version of HistFig is kept in the
> [`legacy` branch](https://github.com/mcjkurz/histfig/tree/legacy).

## What you need

- **Python 3.11 or newer**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (recommended) — installs the right dependencies on Windows, macOS and Linux
- **Models**, one of:
  - an **[OpenRouter](https://openrouter.ai)** API key (the default; many chat and embedding models)
  - **[Ollama](https://ollama.com)** for fully local, free models (`ollama pull <model>`)
  - any other **OpenAI-compatible API** (OpenAI, LM Studio, vLLM, …) and its API key
  - optionally **sentence-transformers** to compute embeddings inside HistFig without any server
    (install with `uv sync --extra local`; downloads PyTorch, ~2 GB)

You can mix them, e.g. an API for chat and Ollama for embeddings.

## Quick start

```bash
git clone <this repository> histfig
cd histfig
uv sync            # install dependencies
uv run histfig     # starts HistFig and opens it in your browser
```

The first time, the browser opens on the **Settings** page. Choose:

1. the **chat model**: OpenRouter, Ollama or another OpenAI-compatible API, its API key, and the model name;
2. the **embedding model**: the same choices, plus sentence-transformers running inside HistFig.

Click **Save** (model names are checked, with suggestions for typos) and **Test connections**. Then create a figure (optionally with a portrait: an image file or a link to one, which is downloaded and kept locally), upload texts, and start chatting.

### Windows

Install uv in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

then run the same `uv sync` / `uv run histfig` commands in a new terminal.

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### GitHub Codespaces

Open the repository in a codespace; dependencies are installed automatically. Codespaces have
no GPU, so use an OpenAI-compatible API. Either paste the key on the Settings page, or (better) add it as a
Codespaces secret called `OPENROUTER_API_KEY` and enter that name under **Advanced → Key from
environment variable** on the Settings page. Run `uv run histfig`; Codespaces offers to open the forwarded port 8000.

### Without uv

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e .
histfig
```

## Starting and stopping

- **Start:** open a terminal in the HistFig folder and run `uv run histfig`. Keep that terminal open
  while you use HistFig in the browser.
- **Stop:** click the terminal and press **Ctrl+C** (also on macOS: Ctrl, not Cmd). Closing the
  terminal window stops it too.
- **Start again:** run `uv run histfig` again. Your figures, documents and conversations are kept.
- **Already running?** If HistFig is still running, for example in another window or after an
  accidental **Ctrl+Z** (which pauses it instead of stopping it), `uv run histfig` notices and asks
  *"Stop it and start a new one?"*. Press Enter to restart it.

## Commands

| Command | What it does |
|---|---|
| `uv run histfig` | Start the app (the first time, it opens on the Settings page) |
| `uv run histfig setup` | Optional: configure in the terminal instead of the browser |
| `uv run histfig doctor` | Check that the chat and embedding models respond |
| `uv run histfig serve --public` | Read-only server to share (see below) |
| `uv run histfig serve --port 8080 --no-browser` | Start on another port, without opening a browser |

Use `--data-dir PATH` (or the `HISTFIG_DATA` environment variable) to keep data somewhere other than `./data`.

## Configuration

Everything is set on the **Settings** page and takes effect immediately. It is saved in
`data/config.toml`, a plain text file you can also edit by hand (restart HistFig afterwards):

```toml
[chat]
provider = "openai_compatible"           # or "ollama"
base_url = "https://openrouter.ai/api/v1"
model = "vendor/model-name"
api_key = ""                             # paste a key here, or…
api_key_env = ""                         # …name an environment variable holding it

[embedding]
provider = "openai_compatible"           # or "ollama", "sentence_transformers"
base_url = "https://openrouter.ai/api/v1"
model = "qwen/qwen3-embedding-4b"
batch_size = 16                          # passages per request; 1 = one by one
query_prefix = ""                        # some models need these; filled in for known ones
document_prefix = ""

[chunking]
chunk_size = 1000                        # per passage, in Chinese characters (3 English letters = 1)
overlap = 150

[retrieval]
top_k = 5                                # passages given to the model per question
min_similarity = 0.2
history_messages = 20                    # earlier messages sent along as context
```

**Changing the embedding model?** Vectors from different models can't be compared, so each figure
remembers the model it was built with. After a change, the figure's page shows a notice and a
**Rebuild index** button (the same button also applies new chunking settings). Until then, search
falls back to keyword matching.

## Prompts

The prompt tells the model how to play a figure. You can edit prompts in the app:

- **General prompts** (Settings page) work for every figure. One of them is the default.
- **Figure prompts** (on a figure's page) are only for that figure. There you can also choose which
  prompt new conversations with that figure start with.
- **Per conversation:** pick a prompt under **⚙ Options** in the chat.

Prompts can use the placeholders `{name}`, `{years}`, `{description}` and `{persona}` (the figure's
persona instructions), so one general prompt works for every figure. **Reset to built-in** in the
editor restores the original text, which lives in `src/histfig/prompts.py`.

## Simple search and agent search

Under **⚙ Options → Documents** in the chat:

- **Simple search** (default): the passages that best match the question go to the model with it.
- **Agent search**: the model looks things up itself before it answers. It can search by meaning,
  look for exact words (names, titles, phrases), read the passages around a hit, and try again with
  other words. Then it picks the passages to answer from, or decides that no lookup is needed,
  e.g. for a greeting. The steps are shown above the answer and included in the export. It is
  slower and makes a few more model calls per question (at most 5 rounds). The model must support
  tool calling. If it doesn't, HistFig says so and uses simple search.
- **Don't use**: chat without the documents.

Answers mark what comes from a passage with its number, like a footnote. Click it to see the
passage. **Immersive** (also under ⚙ Options) hides the numbers, sources, research steps and
thinking, so the chat reads like a plain conversation.

## Sharing a read-only server

To let others (students, a class, a website audience) talk to figures you prepared, without letting
them change anything:

1. Prepare everything as usual: figures, documents, prompts, models and API key. Do it on the server,
   or on your computer and then copy the whole `data/` folder to the server.
2. Start it locked:

   ```bash
   uv run histfig serve --public --host 0.0.0.0 --no-browser
   ```

Visitors can chat, choose a prompt, and change temperature, passages and "show thinking". They can
pick a model only from the ones you added under **Settings → Chat model → Models**
(Browse models… → Add; one of them is the default). They can't see or change settings or the API key, and can't edit figures,
documents or prompts.
Each visitor (browser) only sees their own conversations.

```toml
[public]                 # in data/config.toml
keep_days = 14           # visitors' conversations unused this long are deleted automatically
messages_per_hour = 30   # per visitor, to protect your API budget
```

To change something, stop the server, start it without `--public`, make the changes, and restart it
with `--public`. Your own conversations (made without `--public`) are never shown to visitors or deleted.

For HTTPS, put a web server in front, e.g. [Caddy](https://caddyserver.com) with a `Caddyfile` of:

```
histfig.example.org {
    reverse_proxy localhost:8000
}
```

(then start HistFig without `--host 0.0.0.0`, so only Caddy can reach it).

## How it works

- **Ingestion** runs in the background: extract text → split into passages at paragraph/sentence
  boundaries (Chinese and Western punctuation) → send to the embedding model in batches → store in
  SQLite. If HistFig is stopped mid-way, it continues where it left off on the next start.
- **Passage size** is counted in Chinese characters, with about three letters of English (or any
  other alphabet) counting as one character, because a character carries about as much as three
  letters. So passages hold a similar amount of text in any language: 1000 is about 1000 Chinese
  characters or 500 English words.
- **Retrieval** is hybrid: vector similarity plus keyword search (BM25), merged with reciprocal rank
  fusion. Keywords are words (jieba segments Chinese), English words are stemmed (rivers → river),
  and pairs of neighbouring words are added, so a shared phrase counts for more.
- **Backups:** copy the `data/` folder.

## Development

```bash
uv sync
uv run pytest
```

The code lives in `src/histfig/`: `config.py`, `wizard.py`, `cli.py`, `db.py`, `providers/`,
`ingest/`, `retrieval/`, `server/`, and the browser UI in `static/` (plain JavaScript, no build step).
