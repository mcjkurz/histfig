#!/bin/bash

# Historical Figures Chat System - FOREGROUND MODE
# 
# This script runs the server in the TERMINAL (foreground mode).
# - The server will run while this terminal is open
# - Press Ctrl+C to stop the server
# - Closing the terminal will stop the server
# 
# Applications started:
# 1. Chat app on port 5003 (internal)
# 2. Admin app on port 5004 (internal)  
# 3. Proxy app on port 5001 (external - connects to Cloudflare tunnel)

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

# Start chat application (internal port 5003)
echo "🗨️  Starting chat application on port 5003..."
python app.py &
CHAT_PID=$!

# Wait a moment for chat app to start
sleep 2

# Start admin application (internal port 5004)
echo "⚙️  Starting admin application on port 5004..."
python admin_app.py &
ADMIN_PID=$!

# Wait a moment for admin app to start
sleep 2

# Start proxy application (external port 5001)
echo "🔄 Starting reverse proxy on port 5001..."
echo ""
echo "🌐 Access URLs:"
echo "   Chat Interface: http://localhost:5001/"
echo "   Admin Interface: http://localhost:5001/admin/"
echo "   External Domain: https://chat.qhchina.org/"
echo "   Admin via Domain: https://chat.qhchina.org/admin/"
echo ""
echo "Press Ctrl+C to stop all applications"
echo "================================================"

python proxy_app.py &
PROXY_PID=$!

# Wait for all processes
wait
