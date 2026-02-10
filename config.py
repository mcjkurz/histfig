"""Configuration for Historical Figures Chat System."""
import os
import sys
from pathlib import Path


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


def _get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent


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

# Chat password (optional - if empty, chat is public)
CHAT_PASSWORD = os.environ.get("CHAT_PASSWORD", "")

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
MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "2000"))
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"

# Paths (relative to project root)
_PROJECT_ROOT = _get_project_root()
FIGURES_DIR = str(_PROJECT_ROOT / "figures")
CHROMA_DB_PATH = str(_PROJECT_ROOT / "chroma_db")
TEMP_UPLOAD_DIR = str(_PROJECT_ROOT / "temp_uploads")
FIGURE_IMAGES_DIR = str(_PROJECT_ROOT / "static" / "figure_images")

# Embeddings
EMBEDDING_SOURCE = os.environ.get("EMBEDDING_SOURCE", "local")  # "local" or "external"
LOCAL_EMBEDDING_MODEL = os.environ.get("LOCAL_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
EXTERNAL_EMBEDDING_MODEL = os.environ.get("EXTERNAL_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_API_URL = os.environ.get("EMBEDDING_API_URL", "https://api.openai.com/v1")
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")

# Document chunking
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "1000"))
OVERLAP_PERCENT = int(os.environ.get("OVERLAP_PERCENT", "20"))

# Allowed file types
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# RAG
RAG_ENABLED = os.environ.get("RAG_ENABLED", "true").lower() == "true"

# Document retrieval options for UI (comma-separated list of numbers, e.g., "3,5,10,15")
_docs_to_retrieve_env = os.environ.get("DOCS_TO_RETRIEVE", "2,3,5,10,15,20")
DOCS_TO_RETRIEVE = [int(n.strip()) for n in _docs_to_retrieve_env.split(",") if n.strip().isdigit()]

# Query augmentation (optional but enabled by default, uses separate API for enriching search queries)
QUERY_AUGMENTATION_ENABLED = os.environ.get("QUERY_AUGMENTATION_ENABLED", "true").lower() == "true"
QUERY_AUGMENTATION_MODEL = os.environ.get("QUERY_AUGMENTATION_MODEL", "GPT-5-nano")
QUERY_AUGMENTATION_API_URL = os.environ.get("QUERY_AUGMENTATION_API_URL", "https://api.poe.com/v1")
QUERY_AUGMENTATION_API_KEY = os.environ.get("QUERY_AUGMENTATION_API_KEY", EXTERNAL_API_KEY)

# Search tuning parameters
MIN_COSINE_SIMILARITY = float(os.environ.get("MIN_COSINE_SIMILARITY", "0.05"))
SEARCH_MULTIPLIER = int(os.environ.get("SEARCH_MULTIPLIER", "3"))
RRF_K = int(os.environ.get("RRF_K", "60"))
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "30"))


def validate_config() -> list[str]:
    """
    Validate configuration and return list of errors.
    Returns empty list if configuration is valid.
    """
    errors = []
    warnings = []
    
    # Validate embedding configuration
    if EMBEDDING_SOURCE == "external":
        if not EMBEDDING_API_KEY:
            errors.append("EMBEDDING_API_KEY is required when EMBEDDING_SOURCE=external")
        if not EXTERNAL_EMBEDDING_MODEL:
            errors.append("EXTERNAL_EMBEDDING_MODEL is required when EMBEDDING_SOURCE=external")
    elif EMBEDDING_SOURCE == "local":
        if not LOCAL_EMBEDDING_MODEL:
            errors.append("LOCAL_EMBEDDING_MODEL is required when EMBEDDING_SOURCE=local")
    else:
        errors.append(f"EMBEDDING_SOURCE must be 'local' or 'external', got: {EMBEDDING_SOURCE}")
    
    # Validate query augmentation configuration (only warn, not error)
    if QUERY_AUGMENTATION_ENABLED:
        if not QUERY_AUGMENTATION_API_KEY:
            warnings.append("QUERY_AUGMENTATION_API_KEY not set - query augmentation will be disabled at runtime")
        if not QUERY_AUGMENTATION_MODEL:
            warnings.append("QUERY_AUGMENTATION_MODEL not set - query augmentation may fail")
    
    # Validate numeric ranges
    if not (0 <= OVERLAP_PERCENT <= 50):
        errors.append(f"OVERLAP_PERCENT must be between 0 and 50, got: {OVERLAP_PERCENT}")
    
    if MAX_CHUNK_CHARS < 100:
        errors.append(f"MAX_CHUNK_CHARS must be at least 100, got: {MAX_CHUNK_CHARS}")
    
    if not (0 <= MIN_COSINE_SIMILARITY <= 1):
        errors.append(f"MIN_COSINE_SIMILARITY must be between 0 and 1, got: {MIN_COSINE_SIMILARITY}")
    
    if APP_PORT < 1 or APP_PORT > 65535:
        errors.append(f"APP_PORT must be between 1 and 65535, got: {APP_PORT}")
    
    # Print warnings (non-fatal)
    for warning in warnings:
        print(f"⚠️  Config Warning: {warning}", file=sys.stderr)
    
    return errors


def require_valid_config():
    """
    Validate configuration and exit if invalid.
    Call this at application startup.
    """
    errors = validate_config()
    
    if errors:
        print("\n❌ Configuration Error(s):", file=sys.stderr)
        for error in errors:
            print(f"   • {error}", file=sys.stderr)
        print("\nPlease check your environment variables or .env file.", file=sys.stderr)
        print("See README.md for configuration documentation.\n", file=sys.stderr)
        raise ConfigurationError(f"Invalid configuration: {'; '.join(errors)}")
