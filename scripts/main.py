#!/usr/bin/env python3
"""
Historical Figures Chat System - FastAPI Application
Async application that handles all functionality on one port.
"""

import sys
from pathlib import Path

# Add directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))  # project root (for config)
sys.path.insert(0, str(Path(__file__).parent))  # scripts dir (for chat_routes, etc.)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import logging
import os
import secrets

from config import APP_PORT, DEBUG_MODE, MAX_CONTENT_LENGTH, require_valid_config

# Validate configuration before starting
require_valid_config()

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


LOG_FORMATTER = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)


def setup_logging():
    """Setup logging to console. File output is handled by shell script redirection."""
    # Configure app logger
    app_logger = logging.getLogger('histfig')
    if not app_logger.handlers:
        app_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
        app_logger.propagate = False
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(LOG_FORMATTER)
        app_logger.addHandler(console_handler)


def configure_uvicorn_logging():
    """Configure uvicorn loggers to use our format. Called after uvicorn has initialized."""
    for uvicorn_logger_name in ['uvicorn', 'uvicorn.access', 'uvicorn.error']:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = False
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(LOG_FORMATTER)
        uvicorn_logger.addHandler(handler)


setup_logging()
logger = logging.getLogger('histfig')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Configure uvicorn loggers now that uvicorn has fully initialized
    configure_uvicorn_logging()
    
    # Startup
    logger.info("Starting Historical Figures Chat System...")
    
    # Preload FigureManager (loads embedding model) so first request is fast
    from figure_manager import get_figure_manager
    import asyncio
    logger.info("Preloading FigureManager and embedding model...")
    await asyncio.to_thread(get_figure_manager)
    logger.info("FigureManager ready")
    
    # Start session cleanup task
    from chat_routes import start_session_cleanup_task
    await start_session_cleanup_task()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Historical Figures Chat System...")


# Create FastAPI application
app = FastAPI(
    title="Historical Figures Chat System",
    lifespan=lifespan,
    debug=DEBUG_MODE
)

# Session middleware with secret key
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get('SECRET_KEY', secrets.token_hex(32)),
    max_age=86400  # 24 hours
)

# Store config in app state
app.state.LOGS_DIR = str(LOGS_DIR)
app.state.MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH

# Mount static files
static_path = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Setup templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Make templates available globally
app.state.templates = templates


# Error handler for request entity too large
@app.exception_handler(413)
async def request_entity_too_large(request: Request, exc):
    """Handle file upload too large errors."""
    return JSONResponse(
        status_code=413,
        content={'error': 'Total upload size too large. Please upload fewer files at once.'}
    )


# Import and include routers
from chat_routes import chat_router
from admin_routes import admin_router

app.include_router(chat_router)
app.include_router(admin_router, prefix="/admin")


if __name__ == '__main__':
    import uvicorn
    
    logger.info(f"Starting Historical Figures Chat System on port {APP_PORT}")
    logger.info(f"Chat Interface: http://localhost:{APP_PORT}/")
    logger.info(f"Admin Interface: http://localhost:{APP_PORT}/admin/")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=APP_PORT,
        reload=DEBUG_MODE,
        log_level="debug" if DEBUG_MODE else "info",
        log_config=None  # Use our custom logging config
    )
