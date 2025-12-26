# Historical Figures Chat System

Chat with historical figures using RAG-enhanced AI. Upload documents and have conversations in their authentic style.

![Screenshot](img/screenshot_1.png)

## Quick Start

```bash
git clone https://github.com/mcjkurz/histfig.git
cd histfig

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```bash
# First copy the example settings into a new .env file
cp .env.example .env
# Then edit .env with your API keys and settings
```

You can use external API, local models, or both. Leave fields empty if not needed.

### Run

```bash
./start.sh
```

Access at:
- Chat: `http://localhost:5001/`
- Admin: `http://localhost:5001/admin/`

## Scripts

| Script | Purpose |
|--------|---------|
| `./start.sh` | Start server in background |
| `./utils/check_status.sh` | Check server status |
| `./utils/kill_ports.sh` | Stop server |
| `./utils/clean_logs.sh` | Remove log files |
| `./utils/rebuild_bm25.sh` | Rebuild search indexes |

## Configuration

All settings in `config.py`: port, models, upload limits, chunking, etc.

## Hardware Acceleration

Supports CUDA (NVIDIA GPUs), MPS (Apple Silicon), and CPU. Hardware is detected automatically.
