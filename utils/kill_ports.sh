#!/bin/bash
# Kill processes using the Historical Figures Chat System port

# Get project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

APP_PORT=$(python3 scripts/get_ports.py app 2>/dev/null || echo "5001")

echo "Checking for processes using port $APP_PORT..."
PIDS=$(lsof -t -i :$APP_PORT 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "No processes found using port $APP_PORT"
else
    echo "Found processes: $PIDS"
    echo "Killing processes..."
    kill -9 $PIDS
    echo "Port $APP_PORT is now free"
fi

