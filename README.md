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

### Environment Variables

```bash
export LLM_API_URL="http://localhost:11434/v1"  # Any OpenAI-compatible endpoint
export LLM_API_KEY="your-api-key"               # Required for most APIs
export DEFAULT_MODEL="your-model-name"
export ADMIN_PASSWORD="your-secure-password"
```

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
| `./check_status.sh` | Check server status |
| `./kill_ports.sh` | Stop server |

## Configuration

All settings in `config.py`: port, models, upload limits, chunking, etc.
