#!/bin/bash

# Restart script: kills ports and starts services in foreground

echo "Killing ports..."
./kill_ports.sh

echo "Starting services in foreground..."
./start_foreground.sh

