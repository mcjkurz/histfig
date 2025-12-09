#!/bin/bash

# Script to rebuild BM25 indexes for all figures
# This should be run when you want to refresh the BM25 search indexes

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

