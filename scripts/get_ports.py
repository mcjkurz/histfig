#!/usr/bin/env python3
"""
Simple utility to get port configuration for shell scripts.
Usage: python get_ports.py [app]
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import APP_PORT

if len(sys.argv) == 2:
    port_name = sys.argv[1].lower()
    if port_name == 'app':
        print(APP_PORT)
    else:
        print(f"Unknown port: {port_name}", file=sys.stderr)
        sys.exit(1)
else:
    print(APP_PORT)
