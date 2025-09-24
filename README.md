# Historical Figures Chat System

Chat with historical figures using RAG-enhanced AI. Upload documents and have conversations in their authentic style. 

This project is developed for purely educational and experimental purposes.

![Screenshot](img/screenshot_1.png)

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

## Configuration

All configuration is centralized in `scripts/config.py`. You can modify:

### Ports
- `PROXY_PORT = 5001` - Main external access port
- `CHAT_PORT = 5003` - Internal chat application port  
- `ADMIN_PORT = 5004` - Internal admin application port

### Other Settings
- `OLLAMA_URL` - Ollama server URL
- `DEFAULT_MODEL` - Default language model
- `MAX_CONTENT_LENGTH` - Maximum file upload size
- `DEBUG_MODE` - Enable/disable debug mode

**To change ports:** Edit the values in `scripts/config.py`, then restart the application.

## Out-of-the-Box Ready

The application automatically:
- Creates necessary directories (`figures/`, `chroma_db/`, `temp_uploads/`)
- Initializes the vector database
- Sets up historical figure management
- No manual database setup required

## Features

- Chat with historical figures using RAG-enhanced AI
- Upload and process documents (TXT, PDF, DOCX, MD)
- Admin interface for managing figures and documents
- Real-time streaming responses
- Configurable ports and settings
- Modern responsive UI
