#!/bin/bash

# Historical Figures Chat System - Background Mode
# Runs the server in background with timestamped log files

echo "🚀 Starting Historical Figures Chat System..."
echo "================================================"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please create it first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate" 
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Get port configuration
APP_PORT=$(python3 scripts/get_ports.py app 2>/dev/null || echo "5001")

# Check if already running
RUNNING_PIDS=$(lsof -t -i :$APP_PORT 2>/dev/null)
if [ ! -z "$RUNNING_PIDS" ]; then
    echo "⚠️  Server already running on port $APP_PORT"
    echo "💡 Run ./kill_ports.sh first to stop existing server"
    exit 1
fi

# Create logs directory if needed
mkdir -p logs

# Create timestamped log file
LOG_FILE="logs/server_$(date +%Y-%m-%d_%H-%M-%S).log"

echo "📝 Log file: $LOG_FILE"

# Start server in background
(
    source venv/bin/activate
    python scripts/init_app.py
    python scripts/main.py
) >> "$LOG_FILE" 2>&1 &

# Wait for startup
sleep 3

# Check if started successfully
STARTED_PIDS=$(lsof -t -i :$APP_PORT 2>/dev/null)
if [ ! -z "$STARTED_PIDS" ]; then
    echo "✅ Server started successfully!"
    echo ""
    echo "🌐 Access URLs:"
    echo "   Chat Interface: http://localhost:$APP_PORT/"
    echo "   Admin Interface: http://localhost:$APP_PORT/admin/"
    echo ""
    echo "💡 Commands:"
    echo "   Check status: ./check_status.sh"
    echo "   Stop server:  ./kill_ports.sh"
    echo "   View logs:    tail -f $LOG_FILE"
else
    echo "❌ Failed to start. Check logs:"
    tail -20 "$LOG_FILE" 2>/dev/null
    exit 1
fi

echo "================================================"
