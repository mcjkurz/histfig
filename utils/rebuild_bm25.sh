#!/bin/bash

# Script to rebuild BM25 indexes for all figures

# Get project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=============================================="
echo "  BM25 Index Rebuild Tool"
echo "=============================================="
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Run the rebuild script
python3 scripts/rebuild_bm25_indexes.py

echo ""
echo "=============================================="

