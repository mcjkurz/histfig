"""Configuration for Historical Figures Chat System."""
import os

# Server
APP_PORT = int(os.environ.get("APP_PORT", "5001"))

# LLM API (must be OpenAI-compatible)
# LLM_API_URL is used for external API (e.g., Poe API) - this is the default when external source is selected
# LOCAL_API_URL is used for local models (e.g., Ollama) - this is used when local source is selected
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.poe.com/v1")
LOCAL_API_URL = os.environ.get("LOCAL_API_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "")

# Admin
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# Model whitelist (comma-separated, empty = all models allowed)
_models_env = os.environ.get("ALLOWED_MODELS", "")
ALLOWED_MODELS = [m.strip() for m in _models_env.split(",") if m.strip()] if _models_env else None

# Local models list (comma-separated, empty = fetch from local API)
_local_models_env = os.environ.get("LOCAL_MODELS", "")
LOCAL_MODELS = [m.strip() for m in _local_models_env.split(",") if m.strip()] if _local_models_env else None

# External models list (comma-separated, empty = fetch from external API)
_external_models_env = os.environ.get("EXTERNAL_MODELS", "")
EXTERNAL_MODELS = [m.strip() for m in _external_models_env.split(",") if m.strip()] if _external_models_env else None

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

# Query augmentation (optional but enabled by default, uses separate API for enriching search queries)
QUERY_AUGMENTATION_ENABLED = os.environ.get("QUERY_AUGMENTATION_ENABLED", "true").lower() == "true"
QUERY_AUGMENTATION_MODEL = os.environ.get("QUERY_AUGMENTATION_MODEL", "GPT-5-nano")
QUERY_AUGMENTATION_API_URL = os.environ.get("QUERY_AUGMENTATION_API_URL", "https://api.poe.com/v1")
QUERY_AUGMENTATION_API_KEY = os.environ.get("QUERY_AUGMENTATION_API_KEY", LLM_API_KEY)
