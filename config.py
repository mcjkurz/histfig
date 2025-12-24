"""Configuration for Historical Figures Chat System."""
import os

# Server
APP_PORT = int(os.environ.get("APP_PORT", "5001"))

# LLM API (must be OpenAI-compatible)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local")  # "local" or "external"
LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")

# Default model depends on provider if not explicitly set
_default_model = "gpt-oss:120b" if LLM_PROVIDER == "local" else "GPT-5-mini"
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", _default_model)

# Admin
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# Model presets for external APIs
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

# File uploads
MAX_FILES_PER_REQUEST = 10
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_CONTENT_LENGTH = MAX_FILES_PER_REQUEST * MAX_FILE_SIZE

# Chat
MAX_CONTEXT_MESSAGES = 15
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"

# Paths
FIGURES_DIR = "./figures"
CHROMA_DB_PATH = "./chroma_db"
TEMP_UPLOAD_DIR = "./temp_uploads"
FIGURE_IMAGES_DIR = "./static/figure_images"

# Embeddings
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")

# Document chunking
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "250"))
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "1000"))
OVERLAP_PERCENT = int(os.environ.get("OVERLAP_PERCENT", "20"))

# Allowed file types
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# RAG
RAG_ENABLED = os.environ.get("RAG_ENABLED", "true").lower() == "true"

# Query augmentation (optional, uses separate API for enriching search queries)
QUERY_AUGMENTATION_ENABLED = os.environ.get("QUERY_AUGMENTATION_ENABLED", "true").lower() == "true"
QUERY_AUGMENTATION_MODEL = os.environ.get("QUERY_AUGMENTATION_MODEL", "GPT-5-nano")
QUERY_AUGMENTATION_API_URL = os.environ.get("QUERY_AUGMENTATION_API_URL", "https://api.poe.com/v1")
QUERY_AUGMENTATION_API_KEY = os.environ.get("QUERY_AUGMENTATION_API_KEY", LLM_API_KEY)
