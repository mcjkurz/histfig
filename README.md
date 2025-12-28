# Historical Figures Chat System

Chat with historical figures using RAG-enhanced AI. Upload documents and have conversations in their authentic style.

Read a related blog post on the *Digital Orientalist*: https://digitalorientalist.com/2025/12/26/voices-from-the-past-retrieval-augmented-dialogues-with-chinese-historical-figures/

![Screenshot](img/screenshot_1.png)

## Quick Start

Open the terminal and clone this repository, then install required dependencies.

```bash
git clone https://github.com/mcjkurz/histfig.git
cd histfig

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Configuration

First copy the example settings into a new .env file:

```bash
cp .env.example .env
```
Then edit .env with your API keys and settings. You can use external API, local models, or both. Leave fields empty if not needed.

### Run

```bash
./start.sh
```

Access at:
- Chat: `http://localhost:5001/`
- Admin: `http://localhost:5001/admin/`

The server uses Gunicorn with threaded workers (default: 20 threads) to handle multiple concurrent users, each with isolated sessions; adjust `GUNICORN_THREADS` in `.env` if needed.

## Scripts

| Script | Purpose |
|--------|---------|
| `./start.sh` | Start server in background |
| `./utils/check_status.sh` | Check server status |
| `./utils/stop.sh` | Stop server |
| `./utils/clean_logs.sh` | Remove log files |
| `./utils/rebuild_bm25.sh` | Rebuild search indexes |

## Hardware Acceleration

Supports CUDA (NVIDIA GPUs), MPS (Apple Silicon), and CPU. Hardware is detected automatically.
