#!/usr/bin/env python3
"""
Simple utility to get port configuration for shell scripts.
Usage: python get_ports.py [port_name]
"""
import sys
from config import PROXY_PORT, CHAT_PORT, ADMIN_PORT

ports = {
    'proxy': PROXY_PORT,
    'chat': CHAT_PORT, 
    'admin': ADMIN_PORT
}

if len(sys.argv) == 2:
    port_name = sys.argv[1].lower()
    if port_name in ports:
        print(ports[port_name])
    else:
        print(f"Unknown port: {port_name}", file=sys.stderr)
        sys.exit(1)
else:
    for name, port in ports.items():
        print(f"{name}: {port}")
