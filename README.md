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
export APP_PORT="5001"                        # Server port (default: 5001)
export EXTERNAL_API_URL="https://api.poe.com/v1"   # External API endpoint
export EXTERNAL_API_KEY="your-api-key"             # Required for external APIs
export LOCAL_API_URL="http://localhost:11434/v1"  # Local LLM endpoint (e.g., Ollama)
export ADMIN_PASSWORD="your-admin-password"

# Model lists (comma-separated)
export EXTERNAL_MODELS="GPT-5-mini,GPT-5-nano,Gemini-2.5-Flash"
export LOCAL_MODELS="llama2,mistral,qwen2"
```

You can use external API, local models, or both. Leave empty (`""`) if a source is not available.

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
