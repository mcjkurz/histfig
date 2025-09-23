#!/usr/bin/env python3
"""
Startup script for the RAG chat system.
Runs both the main chat application and the document upload application.
"""

import subprocess
import sys
import os
import time
import signal
import socket
from pathlib import Path

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

def start_application(script_name, port, app_name):
    """Start a Flask application."""
    try:
        print(f"🚀 Starting {app_name} on port {port}...")
        
        # Set environment variables for proper Flask operation
        env = os.environ.copy()
        env['FLASK_ENV'] = 'production'  # Disable debug mode for stability
        env['PYTHONUNBUFFERED'] = '1'  # Ensure immediate output
        
        process = subprocess.Popen([
            sys.executable, script_name
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        
        # Wait a moment to see if the process starts successfully
        time.sleep(3)
        if process.poll() is None:
            print(f"✅ {app_name} started successfully (PID: {process.pid})")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"❌ Failed to start {app_name}")
            print(f"Output: {stdout}")
            if stderr:
                print(f"Error: {stderr}")
            return None
    except Exception as e:
        print(f"❌ Error starting {app_name}: {e}")
        return None

def cleanup_processes(processes):
    """Clean up all running processes."""
    print("\n🛑 Stopping RAG Chat System...")
    
    for process in processes:
        try:
            process.terminate()
            process.wait(timeout=5)
            print(f"✅ Stopped process {process.pid}")
        except subprocess.TimeoutExpired:
            process.kill()
            print(f"🔪 Force killed process {process.pid}")
        except Exception as e:
            print(f"⚠️  Error stopping process: {e}")
    
    print("👋 RAG Chat System stopped")

def signal_handler(signum, frame, processes):
    """Handle signals for graceful shutdown."""
    cleanup_processes(processes)
    sys.exit(0)

def main():
    """Main function to start the RAG system."""
    print("🤖 RAG Chat System Startup")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("scripts/app.py").exists() or not Path("scripts/upload_app.py").exists():
        print("❌ Error: Please run this script from the rag-chat directory")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check if ports are available
    ports_to_check = [5001, 5002]
    for port in ports_to_check:
        if not check_port_available(port):
            print(f"❌ Port {port} is already in use. Please stop the process using this port or choose a different port.")
            sys.exit(1)
    print("✅ Ports 5001 and 5002 are available")
    
    # Create chroma_db directory if it doesn't exist
    os.makedirs("chroma_db", exist_ok=True)
    print("📁 Vector database directory ready")
    
    processes = []
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, processes))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, processes))
    
    try:
        # Start the upload application (port 5002)
        upload_process = start_application("scripts/upload_app.py", 5002, "Document Upload App")
        if upload_process:
            processes.append(upload_process)
        
        # Start the main chat application (port 5001)
        chat_process = start_application("scripts/app.py", 5001, "Main Chat App")
        if chat_process:
            processes.append(chat_process)
        
        if not processes:
            print("❌ Failed to start any applications")
            sys.exit(1)
        
        print("\n🎉 RAG Chat System is ready!")
        print("=" * 40)
        print("📚 Document Upload: http://localhost:5002")
        print("💬 Chat Interface: http://localhost:5001")
        print("\nInstructions:")
        print("1. First, upload documents at http://localhost:5002")
        print("2. Then use the chat interface at http://localhost:5001")
        print("3. Toggle RAG on/off in the chat interface")
        print("\nPress Ctrl+C to stop all services")
        
        # Wait for user to stop
        while True:
            time.sleep(1)
            # Check if any process has died
            dead_processes = []
            for i, process in enumerate(processes):
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    print(f"⚠️  Process {i+1} has stopped unexpectedly (exit code: {process.returncode})")
                    if stderr:
                        print(f"Error output: {stderr}")
                    dead_processes.append(i)
            
            # Remove dead processes and exit if all are dead
            if dead_processes:
                for i in reversed(dead_processes):  # Remove in reverse order to maintain indices
                    processes.pop(i)
                if not processes:
                    print("❌ All processes have stopped. Exiting...")
                    sys.exit(1)
    
    except KeyboardInterrupt:
        cleanup_processes(processes)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        cleanup_processes(processes)
        sys.exit(1)

if __name__ == "__main__":
    main()
