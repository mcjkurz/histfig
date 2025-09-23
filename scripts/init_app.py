#!/usr/bin/env python3
"""
Application initialization script.
Creates necessary directories and ensures the app is ready to run.
"""

import os
import sys
from pathlib import Path
from config import FIGURES_DIR, CHROMA_DB_PATH, TEMP_UPLOAD_DIR

def init_directories():
    """Create necessary directories for the application."""
    directories = [
        FIGURES_DIR,
        CHROMA_DB_PATH, 
        TEMP_UPLOAD_DIR
    ]
    
    print("🔧 Initializing application directories...")
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"   ✅ {directory}")
    
    print("✅ Application directories ready")

def check_requirements():
    """Check if requirements.txt dependencies are installed."""
    try:
        import flask
        import requests
        import chromadb
        import sentence_transformers
        import torch
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Run: pip install -r requirements.txt")
        return False

def main():
    """Initialize the application."""
    print("🚀 Historical Figures Chat System - Initialization")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)
    
    # Initialize directories
    init_directories()
    
    # Check dependencies
    if not check_requirements():
        print("❌ Dependencies not installed")
        sys.exit(1)
    
    print("✅ Application initialization complete!")
    print("💡 You can now run: ./start_foreground.sh or ./start_background.sh")

if __name__ == '__main__':
    main()
