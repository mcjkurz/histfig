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
# LLM Configuration (OpenAI-compatible API)
export LLM_PROVIDER="local"  # "local" for Ollama, "external" for remote API
export LLM_API_URL="http://localhost:11434/v1"  # For Ollama, or "https://api.poe.com/v1" etc.
export LLM_API_KEY="your-api-key"  # Required for external APIs
export DEFAULT_MODEL="gpt-oss:120b"

export ADMIN_PASSWORD="your-secure-password"

# Optional: Query augmentation (uses LLM_API_KEY by default)
export QUERY_AUGMENTATION_ENABLED="true"
export QUERY_AUGMENTATION_MODEL="GPT-5-nano"
export QUERY_AUGMENTATION_API_URL="https://api.poe.com/v1"
export QUERY_AUGMENTATION_API_KEY="your-key"  # optional
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

All settings can be changed in `config.py` including: port, embedding model, upload limits, chunk size, etc.
