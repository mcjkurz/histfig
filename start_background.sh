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

# Check if already running
RUNNING_PIDS=$(lsof -t -i :5001 -i :5003 -i :5004 2>/dev/null)
if [ ! -z "$RUNNING_PIDS" ]; then
    echo "⚠️  Server appears to be already running on ports 5001, 5003, or 5004"
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
STARTED_PIDS=$(lsof -t -i :5001 -i :5003 -i :5004 2>/dev/null)
if [ ! -z "$STARTED_PIDS" ]; then
    echo "✅ Server started successfully in background!"
    echo ""
    echo "🌐 Access URLs:"
    echo "   Chat Interface: http://localhost:5001/"
    echo "   Admin Interface: http://localhost:5001/admin/"
    echo "   External Domain: https://chat.qhchina.org/"
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


