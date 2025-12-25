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
    echo "💡 Run ./utils/kill_ports.sh first to stop existing server"
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

# Wait for server to be ready (poll health endpoint)
MAX_WAIT=120  # Maximum seconds to wait
POLL_INTERVAL=2  # Seconds between checks
ELAPSED=0

echo "⏳ Waiting for server to start..."

while [ $ELAPSED -lt $MAX_WAIT ]; do
    # Check if process is listening on port and health endpoint responds
    if lsof -t -i :$APP_PORT >/dev/null 2>&1; then
        if curl -s --max-time 5 "http://localhost:$APP_PORT/api/health" >/dev/null 2>&1; then
            echo "✅ Server started successfully!"
            echo ""
            echo "🌐 Access URLs:"
            echo "   Chat Interface: http://localhost:$APP_PORT/"
            echo "   Admin Interface: http://localhost:$APP_PORT/admin/"
            echo ""
            echo "💡 Commands:"
            echo "   Check status: ./utils/check_status.sh"
            echo "   Stop server:  ./utils/kill_ports.sh"
            echo "   View logs:    tail -f $LOG_FILE"
            echo "================================================"
            exit 0
        fi
    fi
    
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

# Timeout reached
echo ""
echo "❌ Server failed to start within ${MAX_WAIT}s. Check logs:"
tail -20 "$LOG_FILE" 2>/dev/null
exit 1
