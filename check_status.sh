#!/bin/bash

# Historical Figures Chat System - Status Checker
# Quick script to check if the RAG system is running

echo "🔍 Checking RAG Chat System Status..."
echo "=================================="

# Check if processes are running on the expected ports
PORTS=(5001 5003 5004)
RUNNING=0

for PORT in "${PORTS[@]}"; do
    PID=$(lsof -t -i :$PORT 2>/dev/null)
    if [ ! -z "$PID" ]; then
        PROCESS_NAME=$(ps -p $PID -o comm= 2>/dev/null)
        echo "✅ Port $PORT: Running (PID: $PID, Process: $PROCESS_NAME)"
        RUNNING=$((RUNNING + 1))
    else
        echo "❌ Port $PORT: Not running"
    fi
done

echo ""

if [ $RUNNING -eq 3 ]; then
    echo "🎉 All services are running!"
    echo "🌐 Chat Interface: http://localhost:5001/"
    echo "⚙️  Admin Interface: http://localhost:5001/admin/"
elif [ $RUNNING -gt 0 ]; then
    echo "⚠️  Some services are running, but not all"
    echo "💡 Try running ./kill_ports.sh then ./start_persistent.sh"
else
    echo "😴 No services are running"
    echo "💡 Run ./start_persistent.sh to start the system"
fi

echo "=================================="




