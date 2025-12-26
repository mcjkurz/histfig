"""
Embedding Provider - Unified interface for local and external embeddings.
Supports SentenceTransformer (local) and OpenAI-compatible APIs (external).
"""

import requests
import logging
from typing import List, Union
import torch
from sentence_transformers import SentenceTransformer

from config import (
    EMBEDDING_SOURCE,
    LOCAL_EMBEDDING_MODEL,
    EXTERNAL_EMBEDDING_MODEL,
    EMBEDDING_API_URL,
    EMBEDDING_API_KEY,
)


class EmbeddingProvider:
    """Unified embedding provider supporting local and external sources."""

    def __init__(
        self,
        source: str = None,
        local_model: str = None,
        external_model: str = None,
        api_url: str = None,
        api_key: str = None,
    ):
        self.source = source or EMBEDDING_SOURCE
        self.local_model_name = local_model or LOCAL_EMBEDDING_MODEL
        self.external_model = external_model or EXTERNAL_EMBEDDING_MODEL
        self.api_url = (api_url or EMBEDDING_API_URL).rstrip("/")
        self.api_key = api_key or EMBEDDING_API_KEY

        self.encoder = None
        self.device = None

        if self.source == "local":
            self._init_local()

    def _init_local(self):
        """Initialize local SentenceTransformer model."""
        if torch.backends.mps.is_available():
            self.device = "mps"
        elif torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"

        self.encoder = SentenceTransformer(self.local_model_name, device=self.device)
        logging.info(f"Loaded local embedding model: {self.local_model_name} on {self.device}")

    def encode_document(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Encode document text for storage/indexing."""
        if self.source == "local":
            return self._encode_local(text, is_query=False)
        return self._encode_external(text)

    def encode_query(self, text: str) -> List[float]:
        """Encode query text for search."""
        if self.source == "local":
            return self._encode_local(text, is_query=True)
        return self._encode_external(text)

    def _encode_local(self, text: Union[str, List[str]], is_query: bool = False) -> Union[List[float], List[List[float]]]:
        """Encode using local SentenceTransformer with Qwen-style prompts."""
        if self.encoder is None:
            self._init_local()

        # Qwen embedding models use instruction prefixes for better performance
        is_qwen = "qwen" in self.local_model_name.lower()

        if is_qwen and is_query:
            # Add query instruction for Qwen models
            if isinstance(text, str):
                text = f"query: {text}"
            else:
                text = [f"query: {t}" for t in text]

        result = self.encoder.encode(text)
        return result.tolist()

    def _encode_external(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Encode using external OpenAI-compatible API."""
        if isinstance(text, str):
            input_data = [text]
            single_input = True
        else:
            input_data = text
            single_input = False

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.post(
                f"{self.api_url}/embeddings",
                headers=headers,
                json={"model": self.external_model, "input": input_data},
                timeout=30,
            )

            if response.status_code != 200:
                error_msg = self._parse_error(response)
                logging.error(f"Embedding API error: {error_msg}")
                raise RuntimeError(f"Embedding API error: {error_msg}")

            data = response.json()
            embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

            return embeddings[0] if single_input else embeddings

        except requests.exceptions.RequestException as e:
            logging.error(f"Embedding API request failed: {e}")
            raise RuntimeError(f"Embedding API request failed: {e}")

    def _parse_error(self, response) -> str:
        """Parse error response."""
        try:
            error_data = response.json()
            if "error" in error_data:
                err = error_data["error"]
                return err.get("message", str(err)) if isinstance(err, dict) else str(err)
        except Exception:
            pass
        return f"HTTP {response.status_code}"


# Global instance
_embedding_provider = None


def get_embedding_provider() -> EmbeddingProvider:
    """Get or create global embedding provider instance."""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = EmbeddingProvider()
    return _embedding_provider

