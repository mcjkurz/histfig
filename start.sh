#!/bin/bash

# Historical Figures Chat System - FOREGROUND MODE
# 
# This script runs the server in the TERMINAL (foreground mode).
# - The server will run while this terminal is open
# - Press Ctrl+C to stop the server
# - Closing the terminal will stop the server

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

# Activate virtual environment
source venv/bin/activate

# Initialize application (creates directories, checks dependencies)
python scripts/init_app.py || exit 1

# Get port configuration
APP_PORT=$(python scripts/get_ports.py app)

echo ""
echo "🌐 Access URLs:"
echo "   Chat Interface: http://localhost:$APP_PORT/"
echo "   Admin Interface: http://localhost:$APP_PORT/admin/"
echo ""
echo "Press Ctrl+C to stop the application"
echo "================================================"

# Start unified application
python scripts/main.py
