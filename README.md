# Historical Figures Chat System

Chat with historical figures using RAG-enhanced AI. Upload documents and have conversations in their authentic style.

![Screenshot](img/screenshot_1.png)

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/mcjkurz/histfig.git
cd histfig

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set Environment Variables

Before running, export your API credentials:

```bash
export EXTERNAL_API_KEY="your-api-key"
export EXTERNAL_BASE_URL="https://api.poe.com/v1"  # default
export ADMIN_PASSWORD="your-secure-password"

# Optional: Query augmentation (defaults to EXTERNAL_API_KEY if not set)
export QUERY_AUGMENTATION_ENABLED="true"
export QUERY_AUGMENTATION_MODEL="GPT-5-nano"  # default
export QUERY_AUGMENTATION_API_URL="https://api.poe.com/v1"
export QUERY_AUGMENTATION_API_KEY="your-key"  # optional, uses EXTERNAL_API_KEY by default
```

### 3. Run

```bash
./start.sh
```

The server runs in background. Access at:
- Chat: `http://localhost:5001/`
- Admin: `http://localhost:5001/admin/`

Logs are saved to `logs/server_<timestamp>.log`

## Utility Scripts

| Script | Purpose |
|--------|---------|
| `./check_status.sh` | Check if server is running |
| `./kill_ports.sh` | Stop the server |

## Configuration

Edit `scripts/config.py` to change:
- `APP_PORT` - Server port (default: 5001)
- `OLLAMA_URL` / `OLLAMA_MODEL` - For local Ollama setup
- `MAX_CONTENT_LENGTH` - Max upload size

## Requirements

- Python 3.8+
- API key for an OpenAI-compatible LLM provider
- (Optional) [Ollama](https://ollama.ai/) for local models
