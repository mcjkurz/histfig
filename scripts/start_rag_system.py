#!/usr/bin/env python3
"""
Startup script for the Historical Figures Chat System.
Runs the unified Flask application on a single port.
"""

import subprocess
import sys
import os
import time
import signal
import socket
from pathlib import Path
from config import APP_PORT

def check_port_available(port):
    """Check if a port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0  # Port is available if connection fails
    except Exception:
        return False

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import chromadb
        import sentence_transformers
        import PyPDF2
        import flask
        print("✅ All dependencies found")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please install dependencies: pip install -r requirements.txt")
        return False

def start_application():
    """Start the Flask application."""
    try:
        print(f"🚀 Starting Historical Figures Chat System on port {APP_PORT}...")
        
        env = os.environ.copy()
        env['FLASK_ENV'] = 'production'
        env['PYTHONUNBUFFERED'] = '1'
        
        process = subprocess.Popen([
            sys.executable, 'scripts/main.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        
        time.sleep(3)
        if process.poll() is None:
            print(f"✅ Application started successfully (PID: {process.pid})")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"❌ Failed to start application")
            print(f"Output: {stdout}")
            if stderr:
                print(f"Error: {stderr}")
            return None
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        return None

def cleanup_process(process):
    """Clean up running process."""
    print("\n🛑 Stopping Historical Figures Chat System...")
    
    try:
        process.terminate()
        process.wait(timeout=5)
        print(f"✅ Stopped process {process.pid}")
    except subprocess.TimeoutExpired:
        process.kill()
        print(f"🔪 Force killed process {process.pid}")
    except Exception as e:
        print(f"⚠️  Error stopping process: {e}")
    
    print("👋 Application stopped")

def signal_handler(signum, frame, process):
    """Handle signals for graceful shutdown."""
    cleanup_process(process)
    sys.exit(0)

def main():
    """Main function to start the system."""
    print("🤖 Historical Figures Chat System Startup")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("scripts/main.py").exists():
        print("❌ Error: Please run this script from the histfig directory")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check if port is available
    if not check_port_available(APP_PORT):
        print(f"❌ Port {APP_PORT} is already in use.")
        print("💡 Run ./kill_ports.sh to stop existing process")
        sys.exit(1)
    print(f"✅ Port {APP_PORT} is available")
    
    # Create chroma_db directory if it doesn't exist
    os.makedirs("chroma_db", exist_ok=True)
    print("📁 Vector database directory ready")
    
    process = None
    
    try:
        # Start the application
        process = start_application()
        
        if not process:
            print("❌ Failed to start application")
            sys.exit(1)
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, process))
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, process))
        
        print("\n🎉 Historical Figures Chat System is ready!")
        print("=" * 40)
        print(f"💬 Chat Interface: http://localhost:{APP_PORT}/")
        print(f"⚙️  Admin Interface: http://localhost:{APP_PORT}/admin/")
        print("\nPress Ctrl+C to stop")
        
        # Wait for process
        while True:
            time.sleep(1)
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                print(f"⚠️  Application stopped unexpectedly (exit code: {process.returncode})")
                if stderr:
                    print(f"Error output: {stderr}")
                sys.exit(1)
    
    except KeyboardInterrupt:
        if process:
            cleanup_process(process)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if process:
            cleanup_process(process)
        sys.exit(1)

if __name__ == "__main__":
    main()
