#!/bin/bash
# Kill processes using RAG system ports (5001-5004)

echo "Checking for processes using ports 5001-5004..."
PIDS=$(lsof -t -i :5001 -i :5002 -i :5003 -i :5004 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "No processes found using ports 5001-5004"
else
    echo "Found processes: $PIDS"
    echo "Killing processes..."
    kill -9 $PIDS
    echo "Ports 5001-5004 are now free"
fi
