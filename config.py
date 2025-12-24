"""
Configuration file for Historical Figures Chat System.
Modify these settings to customize ports and other configurations.
"""
import os

# Port Configuration (single-port setup)
APP_PORT = 5001        # Application port for all services (chat, admin, uploads)

# LLM Provider Configuration
# "local" = local Ollama instance, "external" = remote API (e.g., OpenAI, Poe)
# Both must be OpenAI-compatible endpoints
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local")

# LLM API Configuration (OpenAI-compatible endpoint)
# For local Ollama: http://localhost:11434/v1
# For external APIs: https://api.poe.com/v1, https://api.openai.com/v1, etc.
LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")  # Required for external APIs
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gpt-oss:120b")

# Admin Panel Configuration
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # Change in production!

# Available Models for External API (only used when LLM_PROVIDER="external")
EXTERNAL_API_MODELS = [
    "GPT-5.2",
    "GPT-5.2-Instant",
    "GPT-5.1",
    "GPT-5.1-Instant",
    "GPT-5-mini",
    "GPT-5-nano", 
    "Gemini-2.5-Flash",
    "Gemini-3-Flash",
    "Grok-4-Fast-Non-Reasoning",
]

# File Upload Limits
MAX_FILES_PER_REQUEST = 10                              # Max files in single upload
MAX_FILE_SIZE = 50 * 1024 * 1024                        # 50MB per file
MAX_CONTENT_LENGTH = MAX_FILES_PER_REQUEST * MAX_FILE_SIZE  # Total request size

MAX_CONTEXT_MESSAGES = 15              # Keep last 15 exchanges
DEBUG_MODE = False                     # Set to True for development

# Database Paths
FIGURES_DIR = "./figures"
CHROMA_DB_PATH = "./chroma_db"

# Embedding Model Configuration
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")

# Document Processing Settings
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "250"))  # Words per chunk (for word-based chunking)
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "1000"))  # Characters per chunk (primary method)
OVERLAP_PERCENT = int(os.environ.get("OVERLAP_PERCENT", "20"))  # Chunk overlap percentage (0-50%, default 20%)

# File Upload Settings
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
TEMP_UPLOAD_DIR = "./temp_uploads"
FIGURE_IMAGES_DIR = "./static/figure_images"

# RAG Settings
RAG_ENABLED = os.environ.get("RAG_ENABLED", "true").lower() == "true"

# Query Augmentation Settings
QUERY_AUGMENTATION_ENABLED = os.environ.get("QUERY_AUGMENTATION_ENABLED", "true").lower() == "true"
QUERY_AUGMENTATION_MODEL = os.environ.get("QUERY_AUGMENTATION_MODEL", "GPT-5-nano")
QUERY_AUGMENTATION_API_URL = os.environ.get("QUERY_AUGMENTATION_API_URL", "https://api.poe.com/v1")
QUERY_AUGMENTATION_API_KEY = os.environ.get("QUERY_AUGMENTATION_API_KEY", LLM_API_KEY)  # Defaults to LLM_API_KEY
