# Historical Figures Chat System

Chat with historical figures using RAG-enhanced AI. Upload documents and have conversations in their authentic style.

## Prerequisites

- Python 3.7+
- [Ollama](https://ollama.ai/) installed and running
- At least one language model pulled in Ollama (e.g., `ollama pull llama2`)

## Installation

1. Clone this repository
2. Create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Usage

### Quick Start (Foreground)
```bash
./start_foreground.sh
```
Runs in terminal. Press Ctrl+C to stop.

### Background Mode
```bash
./start_background.sh
```
Runs persistently in background. Use `./kill_ports.sh` to stop.

### Check Status
```bash
./check_status.sh
```

## Access URLs

- Chat Interface: `http://localhost:5001/`
- Admin Interface: `http://localhost:5001/admin/`

## Port Configuration

The system uses these ports:
- 5001: Main proxy (external access)
- 5003: Chat app (internal)
- 5004: Admin app (internal)

To use different ports, modify the port numbers in the respective Python files.

## Features

- Chat with historical figures
- Document upload and RAG integration
- Admin interface for managing figures
- Real-time streaming responses
- Modern responsive UI
