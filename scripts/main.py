#!/usr/bin/env python3
"""
Historical Figures Chat System - Unified Application
Single Flask application that handles all functionality on one port.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, request
import logging
from logging.handlers import RotatingFileHandler
import signal
import os
import secrets
from datetime import datetime

from config import APP_PORT, DEBUG_MODE, MAX_CONTENT_LENGTH
from chat_routes import chat_bp
from admin_routes import admin_bp
from figure_manager import get_figure_manager

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with dated log files."""
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = LOGS_DIR / f"server_{timestamp}.log"
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # File handler (rotates at 10MB, keeps 5 backups)
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    logging.info(f"Logging initialized. Log file: {log_filename}")
    return str(log_filename)

# Setup logging
current_log_file = setup_logging()

# Create main Flask application
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Store current log file path in app config for access from routes
app.config['CURRENT_LOG_FILE'] = current_log_file
app.config['LOGS_DIR'] = str(LOGS_DIR)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# Register blueprints
app.register_blueprint(chat_bp)  # Chat routes at root (/)
app.register_blueprint(admin_bp)  # Admin routes at /admin

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file upload too large errors."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return jsonify({'error': 'Total upload size too large. Please upload fewer files at once.'}), 413
    return 'Total upload size too large. Please upload fewer files at once.', 413

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logging.info("Shutting down Historical Figures Chat System...")
    sys.exit(0)

if __name__ == '__main__':
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Preload FigureManager (loads embedding model) so first request is fast
    logging.info("Preloading FigureManager and embedding model...")
    get_figure_manager()
    logging.info("FigureManager ready")
    
    try:
        logging.info(f"Starting Historical Figures Chat System on port {APP_PORT}")
        logging.info(f"Chat Interface: http://localhost:{APP_PORT}/")
        logging.info(f"Admin Interface: http://localhost:{APP_PORT}/admin/")
        app.run(debug=DEBUG_MODE, host='0.0.0.0', port=APP_PORT)
    except KeyboardInterrupt:
        logging.info("Application stopped by user")
    except Exception as e:
        logging.error(f"Application error: {e}")
    finally:
        logging.info("Application shutdown complete")

