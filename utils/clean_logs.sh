#!/bin/bash

# Clean logs from the logs folder

# Get project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

echo "🧹 Cleaning logs..."
echo "=================================="

if [ -d "$LOGS_DIR" ]; then
    FILE_COUNT=$(find "$LOGS_DIR" -type f | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -gt 0 ]; then
        rm -f "$LOGS_DIR"/*
        echo "✅ Removed $FILE_COUNT log file(s) from $LOGS_DIR"
    else
        echo "📁 Logs folder is already empty"
    fi
else
    echo "📁 Logs folder does not exist: $LOGS_DIR"
fi

echo "=================================="

