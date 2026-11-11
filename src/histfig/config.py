"""Configuration: one human-editable TOML file (``<data_dir>/config.toml``).

Every field has a default, so a partial or hand-edited file still loads.
Unknown keys are ignored. API keys can be written inline (``api_key``) or read
from an environment variable named by ``api_key_env``.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

CHAT_PROVIDERS = ("ollama", "openai_compatible")
EMBED_PROVIDERS = ("ollama", "openai_compatible", "sentence_transformers")

OLLAMA_URL = "http://localhost:11434/v1"
OPENROUTER_URL = "https://openrouter.ai/api/v1"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass
class ChatConfig:
    provider: str = "openai_compatible"
    base_url: str = OPENROUTER_URL
    api_key: str = ""
    api_key_env: str = ""
    model: str = ""
    temperature: float = 0.7
    timeout: float = 300.0
    # Extra models that can be picked per conversation (⚙ Options); `model` is always allowed.
    allowed_models: list[str] = field(default_factory=list)

    def resolved_key(self) -> str:
        return resolve_key(self.api_key, self.api_key_env)

    def allows(self, model: str) -> bool:
        return not model or model == self.model or model in self.allowed_models


@dataclass
class EmbeddingConfig:
    provider: str = "openai_compatible"
    base_url: str = OPENROUTER_URL
    api_key: str = ""
    api_key_env: str = ""
    model: str = ""
    batch_size: int = 16
    # Some models expect an instruction/prefix on queries and/or documents.
    query_prefix: str = ""
    document_prefix: str = ""
    timeout: float = 120.0

    def resolved_key(self) -> str:
        return resolve_key(self.api_key, self.api_key_env)

    @property
    def model_id(self) -> str:
        """Identity stored with each figure so vectors from different models never mix."""
        return f"{self.provider}:{self.model}"


@dataclass
class ChunkingConfig:
    chunk_size: int = 1000  # Chinese characters; ~3 other characters count as one (ingest/chunk.py)
    overlap: int = 150


@dataclass
class RetrievalConfig:
    top_k: int = 5
    candidates: int = 30
    min_similarity: float = 0.2
    rrf_k: int = 60
    history_messages: int = 20


@dataclass
class PublicConfig:
    """Only used with `histfig serve --public`."""

    keep_days: int = 14  # visitors' conversations unused this long are deleted (0 = keep)
    messages_per_hour: int = 30  # per visitor (0 = no limit)


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    public: PublicConfig = field(default_factory=PublicConfig)

    def embedding_key(self) -> str:
        """The embedding model's own key; without one, the chat model's key when both use the
        same service. Sharing is resolved here, at use time, so there is never a stale copy."""
        e, c = self.embedding, self.chat
        if e.api_key or e.api_key_env:
            return e.resolved_key()
        same_service = e.provider == c.provider and e.base_url.rstrip("/") == c.base_url.rstrip("/")
        return c.resolved_key() if same_service else ""

    def validate(self) -> list[str]:
        problems = []
        if self.chat.provider not in CHAT_PROVIDERS:
            problems.append(f"chat.provider must be one of {CHAT_PROVIDERS}")
        if self.embedding.provider not in EMBED_PROVIDERS:
            problems.append(f"embedding.provider must be one of {EMBED_PROVIDERS}")
        if not self.chat.model:
            problems.append("chat.model is empty")
        if not self.embedding.model:
            problems.append("embedding.model is empty")
        if self.chunking.chunk_size < 100:
            problems.append("chunking.chunk_size should be at least 100")
        if not 0 <= self.chunking.overlap < self.chunking.chunk_size // 2:
            problems.append("chunking.overlap must be >= 0 and less than half of chunk_size")
        if self.embedding.batch_size < 1:
            problems.append("embedding.batch_size must be >= 1")
        return problems


def resolve_key(inline: str, env_name: str) -> str:
    if inline:
        return inline
    if env_name:
        return os.environ.get(env_name, "")
    return ""


def default_data_dir() -> Path:
    return Path(os.environ.get("HISTFIG_DATA", "data")).resolve()


def config_path(data_dir: Path) -> Path:
    return data_dir / "config.toml"


def _fill(cls, values: dict):
    names = {f.name: f for f in fields(cls)}
    kwargs = {}
    for key, value in (values or {}).items():
        if key in names:
            default = getattr(cls(), key)
            # coerce simple numeric types written as strings / ints
            if isinstance(default, bool) or default is None:
                kwargs[key] = value
            elif isinstance(default, list):
                if not isinstance(value, list):
                    raise ValueError(f"{key} must be a list")
                kwargs[key] = list(dict.fromkeys(str(v).strip() for v in value if str(v).strip()))
            elif isinstance(default, float):
                kwargs[key] = float(value)
            elif isinstance(default, int):
                kwargs[key] = int(value)
            else:
                kwargs[key] = value
    return cls(**kwargs)


def _from_dict(raw: dict) -> Config:
    return Config(
        server=_fill(ServerConfig, raw.get("server", {})),
        chat=_fill(ChatConfig, raw.get("chat", {})),
        embedding=_fill(EmbeddingConfig, raw.get("embedding", {})),
        chunking=_fill(ChunkingConfig, raw.get("chunking", {})),
        retrieval=_fill(RetrievalConfig, raw.get("retrieval", {})),
        public=_fill(PublicConfig, raw.get("public", {})),
    )


def load_config(data_dir: Path) -> Config | None:
    path = config_path(data_dir)
    if not path.exists():
        return None
    with path.open("rb") as f:
        return _from_dict(tomllib.load(f))


def updated(cfg: Config, changes: dict) -> Config:
    """A copy of cfg with {section: {field: value}} applied. Unknown keys and the
    [server] section (needs a restart) are ignored; bad numbers raise ValueError."""
    data = asdict(cfg)
    for section, values in (changes or {}).items():
        if section in data and section not in ("server", "public") and isinstance(values, dict):
            data[section].update({k: v for k, v in values.items() if k in data[section]})
    return _from_dict(data)


# Written by save_config() with the current values filled in, so the comments
# survive every save. Every field of every section must appear here.
TEMPLATE = """\
# HistFig configuration. Change it with `histfig setup`, or edit this file and restart.
# Every setting has a default, so lines you delete fall back to it.
#
# API keys: put the key in api_key, or put the NAME of an environment variable
# holding it in api_key_env (e.g. "OPENROUTER_API_KEY", handy for Codespaces secrets).
# Check your settings with `histfig doctor`.

[server]
host = {server_host}
port = {server_port}

[chat]
# provider: "openai_compatible" (OpenRouter, OpenAI, LM Studio, vLLM, ...) or "ollama"
# base_url: OpenRouter https://openrouter.ai/api/v1 · Ollama http://localhost:11434/v1
provider = {chat_provider}
base_url = {chat_base_url}
api_key = {chat_api_key}
api_key_env = {chat_api_key_env}
model = {chat_model}
temperature = {chat_temperature}
timeout = {chat_timeout}
# Extra models people can pick per conversation (⚙ Options); the model above is always available.
allowed_models = {chat_allowed_models}

[embedding]
# provider: "openai_compatible", "ollama", or "sentence_transformers" (runs inside
# HistFig; install with `uv sync --extra local`; base_url and api_key are ignored).
# model must be an EMBEDDING model, not a chat model.
provider = {embedding_provider}
base_url = {embedding_base_url}
api_key = {embedding_api_key}
api_key_env = {embedding_api_key_env}
model = {embedding_model}
batch_size = {embedding_batch_size}
# Some models expect prefixes (setup fills in the known ones):
#   nomic-embed-text:     "search_query: " / "search_document: "
#   multilingual-e5 / e5: "query: " / "passage: "
#   Qwen3-Embedding:      "Instruct: Given a question, retrieve passages that help answer it\\nQuery: " / ""
# Changing the embedding model means rebuilding each figure's index (button on its page).
query_prefix = {embedding_query_prefix}
document_prefix = {embedding_document_prefix}
timeout = {embedding_timeout}

[chunking]
# In Chinese characters; about 3 letters of English (or any alphabet) count as one.
chunk_size = {chunking_chunk_size}
overlap = {chunking_overlap}

[retrieval]
top_k = {retrieval_top_k}
candidates = {retrieval_candidates}
min_similarity = {retrieval_min_similarity}
rrf_k = {retrieval_rrf_k}
history_messages = {retrieval_history_messages}

[public]
# Only used with `histfig serve --public` (a read-only server you share with others).
keep_days = {public_keep_days}                # visitors' conversations unused this long are deleted (0 = keep)
messages_per_hour = {public_messages_per_hour}       # per visitor (0 = no limit)
"""


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(v, ensure_ascii=False)  # JSON string escapes are valid TOML


def save_config(cfg: Config, data_dir: Path) -> Path:
    values = {
        f"{section}_{key}": _toml_value(value)
        for section, entries in asdict(cfg).items()
        for key, value in entries.items()
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    path = config_path(data_dir)
    path.write_text(TEMPLATE.format(**values), encoding="utf-8")
    return path


def suggested_prefixes(model: str) -> tuple[str, str]:
    """Known query/document prefixes for popular embedding models."""
    m = model.lower()
    if "nomic-embed" in m:
        return "search_query: ", "search_document: "
    if "multilingual-e5" in m or "/e5-" in m or m.startswith("e5-"):
        return "query: ", "passage: "
    if "qwen3-embedding" in m:
        return "Instruct: Given a question, retrieve passages that help answer it\nQuery: ", ""
    if "bge" in m and "m3" not in m and "zh" in m:
        return "为这个句子生成表示以用于检索相关文章：", ""
    return "", ""
