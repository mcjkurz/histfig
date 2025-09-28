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

# External API Configuration
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")

# Available Models for External API
AVAILABLE_MODELS = [
    "GPT-5-mini",
    "GPT-5-nano", 
    "GPT-4.1-mini",
    "Gemini-2.5-Flash",
    "Nova-Micro-1.0",
    "Grok-4-Fast-Non-Reasoning",
    "Other"
]

# Application Settings
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
MAX_CONTEXT_MESSAGES = 10              # Keep last 10 exchanges
DEBUG_MODE = False                     # Set to True for development

# Database Paths
FIGURES_DIR = "./figures"
CHROMA_DB_PATH = "./chroma_db"

# Embedding Model Configuration
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Document Processing Settings
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "300"))  # Number of words per chunk
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "50"))  # Overlap in words

# File Upload Settings
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
TEMP_UPLOAD_DIR = "./temp_uploads"
FIGURE_IMAGES_DIR = "./static/figure_images"
