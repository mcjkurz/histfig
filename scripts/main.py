#!/usr/bin/env python3
"""
Historical Figures Chat System - Unified Application
Single Flask application that handles all functionality on one port.
"""

import sys
from pathlib import Path

# Add directories to path for imports
# Parent directory for config.py, scripts directory for other modules
sys.path.insert(0, str(Path(__file__).parent.parent))  # project root (for config)
sys.path.insert(0, str(Path(__file__).parent))  # scripts dir (for chat_routes, etc.)

from flask import Flask, jsonify, request
import logging
import signal
import os
import secrets

from config import APP_PORT, DEBUG_MODE, MAX_CONTENT_LENGTH
from chat_routes import chat_bp
from admin_routes import admin_bp
from figure_manager import get_figure_manager

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging to console. File output is handled by shell script redirection."""
    # Use app-specific logger instead of root to avoid conflicts with gunicorn
    app_logger = logging.getLogger('histfig')
    
    # Skip if already configured
    if app_logger.handlers:
        return
    
    # Console formatter
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Setup app logger
    app_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    app_logger.propagate = False  # Don't duplicate to root logger
    
    # Console handler (gunicorn/shell script redirects this to log file)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    app_logger.addHandler(console_handler)

# Setup logging
setup_logging()

# Create a logger for this module
logger = logging.getLogger('histfig')

# Create main Flask application
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Store logs directory in app config for access from routes
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

# Preload FigureManager (loads embedding model) so first request is fast
logger.info("Preloading FigureManager and embedding model...")
get_figure_manager()
logger.info("FigureManager ready")

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file upload too large errors."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return jsonify({'error': 'Total upload size too large. Please upload fewer files at once.'}), 413
    return 'Total upload size too large. Please upload fewer files at once.', 413

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutting down Historical Figures Chat System...")
    sys.exit(0)

if __name__ == '__main__':
    # Direct execution (development mode) - use Flask's built-in server
    # For production, use: gunicorn -k gevent -w 1 scripts.main:app
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info(f"Starting Historical Figures Chat System on port {APP_PORT}")
        logger.info(f"Chat Interface: http://localhost:{APP_PORT}/")
        logger.info(f"Admin Interface: http://localhost:{APP_PORT}/admin/")
        app.run(debug=DEBUG_MODE, host='0.0.0.0', port=APP_PORT)
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        logger.info("Application shutdown complete")

