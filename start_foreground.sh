#!/bin/bash

# Historical Figures Chat System - FOREGROUND MODE
# 
# This script runs the server in the TERMINAL (foreground mode).
# - The server will run while this terminal is open
# - Press Ctrl+C to stop the server
# - Closing the terminal will stop the server
# 
# Applications started based on config.py:
# 1. Chat app (internal)
# 2. Admin app (internal)  
# 3. Proxy app (external)

echo "🚀 Starting Historical Figures Chat System..."
echo "================================================"

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "🛑 Stopping all applications..."
    kill $CHAT_PID $ADMIN_PID $PROXY_PID 2>/dev/null
    wait
    echo "✅ All applications stopped"
    exit 0
}

# Set up signal handling
trap cleanup SIGINT SIGTERM

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please create it first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate" 
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Initialize application (creates directories, checks dependencies)
python scripts/init_app.py || exit 1

# Get port configuration
CHAT_PORT=$(python scripts/get_ports.py chat)
ADMIN_PORT=$(python scripts/get_ports.py admin)
PROXY_PORT=$(python scripts/get_ports.py proxy)

# Start chat application
echo "🗨️  Starting chat application on port $CHAT_PORT..."
python scripts/app.py &
CHAT_PID=$!

sleep 2

# Start admin application
echo "⚙️  Starting admin application on port $ADMIN_PORT..."
python scripts/admin_app.py &
ADMIN_PID=$!

sleep 2

# Start proxy application
echo "🔄 Starting reverse proxy on port $PROXY_PORT..."
echo ""
echo "🌐 Access URLs:"
echo "   Chat Interface: http://localhost:$PROXY_PORT/"
echo "   Admin Interface: http://localhost:$PROXY_PORT/admin/"
echo ""
echo "Press Ctrl+C to stop all applications"
echo "================================================"

python scripts/proxy_app.py &
PROXY_PID=$!

# Wait for all processes
wait
