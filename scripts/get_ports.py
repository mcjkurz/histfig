#!/usr/bin/env python3
"""
Simple utility to get port configuration for shell scripts.
Usage: python get_ports.py [port_name]
"""
import sys
from config import APP_PORT

ports = {
    'app': APP_PORT,
    'main': APP_PORT,
    # Legacy aliases for compatibility
    'proxy': APP_PORT,
    'chat': APP_PORT, 
    'admin': APP_PORT
}

if len(sys.argv) == 2:
    port_name = sys.argv[1].lower()
    if port_name in ports:
        print(ports[port_name])
    else:
        print(f"Unknown port: {port_name}", file=sys.stderr)
        sys.exit(1)
else:
    print(f"app: {APP_PORT}")
