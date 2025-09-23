# Historical Figures Chat System - User Guide

## Overview

This system allows you to simulate conversations with historical figures by uploading their texts (diaries, letters, speeches, etc.) and using RAG to inform AI responses in their style.

## Getting Started

### 1. Create a Historical Figure

```bash
python scripts/figure_cli.py create napoleon_bonaparte "Napoleon Bonaparte" \
  --description "French military general and political leader" \
  --personality-prompt "Respond as Napoleon Bonaparte would, with confidence, strategic thinking, and references to military campaigns and political philosophy." \
  --metadata '{"birth_year": 1769, "death_year": 1821, "nationality": "French", "occupation": "Emperor, Military General"}'
```

### 2. Upload Documents

```bash
# Upload PDF files
python scripts/figure_cli.py upload napoleon_bonaparte /path/to/napoleon_diary.pdf

# Upload text files
python scripts/figure_cli.py upload napoleon_bonaparte /path/to/letters.txt /path/to/speeches.txt

# Upload multiple files at once
python scripts/figure_cli.py upload napoleon_bonaparte *.pdf *.txt
```

### 3. List Available Figures

```bash
python scripts/figure_cli.py list
```

### 4. View Figure Details

```bash
python scripts/figure_cli.py show napoleon_bonaparte
```

### 5. Search Figure's Documents

```bash
python scripts/figure_cli.py search napoleon_bonaparte "military strategy" --limit 3
```

### 6. Delete a Figure

```bash
python scripts/figure_cli.py delete napoleon_bonaparte --force
```

## Using the Web Interface

1. **Start the Server**: Run `./start_foreground.sh` or `./start_background.sh`
2. **Open Browser**: Navigate to `http://localhost:5001`
3. **Select Figure**: Use the dropdown in the top-left to select a historical figure
4. **Chat**: Ask questions and the AI will respond as that figure, using their documents for context

## Features

- **Multi-Figure Support**: Create and manage multiple historical figures
- **Document Chunking**: Automatically processes and chunks uploaded documents
- **Vector Search**: Uses semantic similarity to find relevant content
- **Persona-Based Responses**: AI responds in the style of the selected figure
- **Real-time Switching**: Switch between figures mid-conversation
- **Source Citations**: Shows which documents informed each response

## Document Types Supported

- **PDF**: Automatically extracted and processed
- **TXT**: Plain text files with automatic encoding detection

## System Architecture

- **Figure Manager**: Handles CRUD operations for figures
- **ChromaDB Collections**: Each figure has its own isolated vector collection
- **Document Processor**: Chunks and processes uploaded texts
- **Web Interface**: Provides figure selection and chat interface

## Tips for Best Results

1. **Quality Documents**: Upload high-quality texts that represent the figure's authentic voice
2. **Personality Prompts**: Use specific prompts that capture the figure's communication style
3. **Document Variety**: Include different types of texts (personal writings, public speeches, etc.)
4. **Metadata**: Add relevant biographical information to enhance context

## Troubleshooting

- **No Documents Found**: Ensure documents are properly uploaded and processed
- **Figure Not Responding**: Check that the figure has documents and the personality prompt is set
- **Performance**: Large document collections may take longer to search

## Example Figures to Try

1. **Napoleon Bonaparte**: Military strategies, leadership philosophy
2. **Leonardo da Vinci**: Scientific observations, artistic techniques
3. **Marcus Aurelius**: Stoic philosophy, leadership reflections
4. **Benjamin Franklin**: Political wisdom, scientific discoveries

Enjoy chatting with history!
