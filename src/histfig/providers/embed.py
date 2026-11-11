"""Embedding backends behind one interface: ``await embedder.embed(texts) -> ndarray``.

All vectors are returned as float32 and L2-normalised, so cosine similarity is
a plain dot product.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import numpy as np

from histfig.config import EmbeddingConfig
from histfig.providers.chat import ProviderError, _error_text, _headers


def normalise(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


@dataclass
class Usage:
    """What the provider reported for one request (0 = not reported)."""

    tokens: int = 0
    cost: float = 0.0  # USD; only some providers (e.g. OpenRouter) report it


class Embedder:
    def __init__(self, cfg: EmbeddingConfig, key: Callable[[], str] | None = None):
        self.cfg = cfg
        self.key = key or cfg.resolved_key  # e.g. Config.embedding_key, to share the chat key

    @property
    def model_id(self) -> str:
        return self.cfg.model_id

    async def _embed_raw(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    async def _embed_raw_usage(self, texts: list[str]) -> tuple[np.ndarray, Usage]:
        return await self._embed_raw(texts), Usage()

    async def embed_documents_with_usage(self, texts: list[str]) -> tuple[np.ndarray, Usage]:
        vectors, usage = await self._embed_raw_usage([self.cfg.document_prefix + t for t in texts])
        return normalise(vectors), usage

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return normalise(await self._embed_raw(texts))

    async def embed_query(self, text: str) -> np.ndarray:
        return (await self.embed([self.cfg.query_prefix + text]))[0]


class HTTPEmbedder(Embedder):
    """POST {base_url}/embeddings — OpenAI, OpenRouter, LM Studio, Ollama (/v1), ..."""

    retries = 4

    async def _embed_raw(self, texts: list[str]) -> np.ndarray:
        return (await self._embed_raw_usage(texts))[0]

    async def _embed_raw_usage(self, texts: list[str]) -> tuple[np.ndarray, Usage]:
        url = self.cfg.base_url.rstrip("/") + "/embeddings"
        payload = {"model": self.cfg.model, "input": texts}
        headers = _headers(self.key())
        last_error = ""
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout, connect=15)) as client:
            for attempt in range(self.retries):
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as e:
                    last_error = f"Could not reach {url}: {e!r}"
                else:
                    if resp.status_code == 200:
                        body = resp.json()
                        data = sorted(body["data"], key=lambda d: d.get("index", 0))
                        if len(data) != len(texts):
                            raise ProviderError(
                                f"Expected {len(texts)} embeddings, got {len(data)}"
                            )
                        vectors = np.array([d["embedding"] for d in data], dtype=np.float32)
                        return vectors, _usage(body.get("usage"))
                    last_error = _error_text(resp)
                    if resp.status_code not in (408, 409, 429) and resp.status_code < 500:
                        break  # not retryable (bad model name, bad key, ...)
                await asyncio.sleep(2**attempt)
        raise ProviderError(last_error)


def _usage(raw) -> Usage:
    if not isinstance(raw, dict):
        return Usage()
    tokens = raw.get("total_tokens") or raw.get("prompt_tokens") or 0
    cost = raw.get("cost") or 0
    try:
        return Usage(tokens=int(tokens), cost=float(cost))
    except (TypeError, ValueError):
        return Usage()


class SentenceTransformerEmbedder(Embedder):
    """Runs a sentence-transformers model in-process (optional `local` extra)."""

    _model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ProviderError(
                    "sentence-transformers is not installed. Install it with "
                    "`uv sync --extra local` (or `pip install sentence-transformers`)."
                ) from e
            self._model = SentenceTransformer(self.cfg.model)
        return self._model

    async def _embed_raw(self, texts: list[str]) -> np.ndarray:
        def run():
            model = self._load()
            return model.encode(texts, batch_size=len(texts), convert_to_numpy=True)

        return await asyncio.to_thread(run)


def make_embedder(cfg: EmbeddingConfig, key: Callable[[], str] | None = None) -> Embedder:
    if cfg.provider == "sentence_transformers":
        return SentenceTransformerEmbedder(cfg)
    return HTTPEmbedder(cfg, key)
