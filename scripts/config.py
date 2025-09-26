"""
Configuration file for Historical Figures Chat System.
Modify these settings to customize ports and other configurations.
"""
import os

# Port Configuration
PROXY_PORT = 5001      # Main external access port
CHAT_PORT = 5003       # Internal chat application port  
ADMIN_PORT = 5004      # Internal admin application port
UPLOAD_PORT = 5002     # Upload application port (if used)

# Model Provider Configuration
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "ollama")  # Options: "ollama"

# Ollama Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")

# Application Settings
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
MAX_CONTEXT_MESSAGES = 10              # Keep last 10 exchanges
DEBUG_MODE = False                     # Set to True for development

# Database Paths
FIGURES_DIR = "./figures"
CHROMA_DB_PATH = "./chroma_db"

# File Upload Settings
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
TEMP_UPLOAD_DIR = "./temp_uploads"
FIGURE_IMAGES_DIR = "./static/figure_images"
