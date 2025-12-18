#!/bin/bash

# Historical Figures Chat System - Status Checker
# Quick script to check if the system is running

echo "🔍 Checking Historical Figures Chat System Status..."
echo "=================================="

# Get port from config
APP_PORT=$(python3 scripts/get_ports.py app 2>/dev/null || echo "5001")

PID=$(lsof -t -i :$APP_PORT 2>/dev/null)
if [ ! -z "$PID" ]; then
    PROCESS_NAME=$(ps -p $PID -o comm= 2>/dev/null)
    echo "✅ Port $APP_PORT: Running (PID: $PID, Process: $PROCESS_NAME)"
    echo ""
    echo "🎉 Service is running!"
    echo "🌐 Chat Interface: http://localhost:$APP_PORT/"
    echo "⚙️  Admin Interface: http://localhost:$APP_PORT/admin/"
else
    echo "❌ Port $APP_PORT: Not running"
    echo ""
    echo "😴 Service is not running"
    echo "💡 Run ./start.sh to start the system"
fi

echo "=================================="
