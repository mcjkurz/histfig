"""Configuration for Historical Figures Chat System."""
import os

# Server
APP_PORT = int(os.environ.get("APP_PORT", "5001"))

# LLM API (must be OpenAI-compatible)
# EXTERNAL_API_URL is used for external API (e.g., Poe API) - this is the default when external source is selected
# LOCAL_API_URL is used for local models (e.g., Ollama) - this is used when local source is selected
EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_URL", "https://api.poe.com/v1")
LOCAL_API_URL = os.environ.get("LOCAL_API_URL", "http://localhost:11434/v1")
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")

# Default models for each source (fallback when no model is specified)
DEFAULT_LOCAL_MODEL = os.environ.get("DEFAULT_LOCAL_MODEL", "")
DEFAULT_EXTERNAL_MODEL = os.environ.get("DEFAULT_EXTERNAL_MODEL", "GPT-5-mini")

# Admin
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

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
CHUNK_SIZE_WORDS = int(os.environ.get("CHUNK_SIZE_WORDS", "250"))
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "1000"))
OVERLAP_PERCENT = int(os.environ.get("OVERLAP_PERCENT", "20"))

# Allowed file types
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# RAG
RAG_ENABLED = os.environ.get("RAG_ENABLED", "true").lower() == "true"

# Query augmentation (optional but enabled by default, uses separate API for enriching search queries)
QUERY_AUGMENTATION_ENABLED = os.environ.get("QUERY_AUGMENTATION_ENABLED", "true").lower() == "true"
QUERY_AUGMENTATION_MODEL = os.environ.get("QUERY_AUGMENTATION_MODEL", "GPT-5-nano")
QUERY_AUGMENTATION_API_URL = os.environ.get("QUERY_AUGMENTATION_API_URL", "https://api.poe.com/v1")
QUERY_AUGMENTATION_API_KEY = os.environ.get("QUERY_AUGMENTATION_API_KEY", EXTERNAL_API_KEY)

# Search tuning parameters
MIN_COSINE_SIMILARITY = float(os.environ.get("MIN_COSINE_SIMILARITY", "0.05"))
SEARCH_MULTIPLIER = int(os.environ.get("SEARCH_MULTIPLIER", "3"))  # Fetch N times more results for fusion
RRF_K = int(os.environ.get("RRF_K", "60"))  # Reciprocal Rank Fusion constant
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "30"))
