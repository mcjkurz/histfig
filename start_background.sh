#!/bin/bash

# Historical Figures Chat System - BACKGROUND MODE
# 
# This script runs the server PERSISTENTLY in the background.
# - The server will run even after closing the terminal
# - The server will survive system sleep/wake cycles  
# - Use ./kill_ports.sh to stop the server
# - Perfect for when you want to start the server and forget about it

echo "🚀 Starting Historical Figures Chat System (Background Mode)..."
echo "================================================"

# Get port configuration  
CHAT_PORT=$(python3 scripts/get_ports.py chat 2>/dev/null || echo "5003")
ADMIN_PORT=$(python3 scripts/get_ports.py admin 2>/dev/null || echo "5004") 
PROXY_PORT=$(python3 scripts/get_ports.py proxy 2>/dev/null || echo "5001")

# Check if already running
RUNNING_PIDS=$(lsof -t -i :$PROXY_PORT -i :$CHAT_PORT -i :$ADMIN_PORT 2>/dev/null)
if [ ! -z "$RUNNING_PIDS" ]; then
    echo "⚠️  Server appears to be already running on ports $PROXY_PORT, $CHAT_PORT, or $ADMIN_PORT"
    echo "💡 Run ./kill_ports.sh first to stop existing servers"
    echo "🔍 Or run ./check_status.sh to verify status"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please create it first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate" 
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Start the server in complete background mode
echo "🌙 Starting server with sleep prevention..."

# Use nohup to detach from terminal, caffeinate to prevent sleep
# Redirect output to log file for debugging if needed
nohup caffeinate -i -s ./start_foreground.sh > rag_server.log 2>&1 &

# Give it a moment to start
sleep 3

# Check if it started successfully
STARTED_PIDS=$(lsof -t -i :$PROXY_PORT -i :$CHAT_PORT -i :$ADMIN_PORT 2>/dev/null)
if [ ! -z "$STARTED_PIDS" ]; then
    echo "✅ Server started successfully in background!"
    echo ""
    echo "🌐 Access URLs:"
    echo "   Chat Interface: http://localhost:$PROXY_PORT/"
    echo "   Admin Interface: http://localhost:$PROXY_PORT/admin/"
    echo ""
    echo "💡 Useful commands:"
    echo "   Check status: ./check_status.sh"
    echo "   Stop server:  ./kill_ports.sh"
    echo "   View logs:    tail -f rag_server.log"
    echo ""
    echo "🔋 Your Mac will stay awake as long as the server runs"
    echo "🖥️  You can now close this terminal safely"
else
    echo "❌ Failed to start server. Check rag_server.log for details:"
    tail -10 rag_server.log 2>/dev/null || echo "No log file found"
    exit 1
fi

echo "================================================"


