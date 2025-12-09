#!/usr/bin/env python3
"""
Historical Figures Chat System - Unified Application
Single Flask application that handles all functionality on one port.
"""

from flask import Flask, jsonify, request
import logging
import signal
import sys
import os
import secrets

from config import APP_PORT, DEBUG_MODE, MAX_CONTENT_LENGTH
from chat_routes import chat_bp
from admin_routes import admin_bp

# Create main Flask application
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# Setup logging
logging.basicConfig(level=logging.INFO if not DEBUG_MODE else logging.DEBUG)

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

