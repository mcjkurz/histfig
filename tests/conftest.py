import hashlib

import numpy as np
import pytest

from histfig.config import Config, EmbeddingConfig
from histfig.providers.embed import Embedder, Usage
from histfig.retrieval.tokenize import tokenize


class FakeEmbedder(Embedder):
    """Deterministic bag-of-words hashing embedder — similar texts get similar vectors."""

    dim = 64

    def __init__(self, model="fake-embed"):
        super().__init__(EmbeddingConfig(provider="openai_compatible", model=model, batch_size=4))
        self.calls = 0

    async def _embed_raw(self, texts):
        self.calls += 1
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokenize(t) or ["empty"]:
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        return out + 1e-3

    async def _embed_raw_usage(self, texts):
        return await self._embed_raw(texts), Usage(tokens=10 * len(texts), cost=0.001 * len(texts))


class FakeChat:
    def __init__(self):
        self.last_messages = None

    async def stream(self, messages, model=None, temperature=None):
        self.last_messages = messages
        yield "thinking", "pondering"
        for word in ["I ", "remember ", "the ", "river."]:
            yield "content", word

    async def complete(self, messages, model=None):
        return "OK"

    script: list = []  # agent search: the replies call_tools gives, one per step

    async def call_tools(self, messages, tools, model=None):
        self.tool_messages = messages
        step = sum(1 for m in messages if m["role"] == "assistant" and m.get("tool_calls"))
        reply = self.script[step] if step < len(self.script) else {}
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def cfg():
    c = Config()
    c.chat.model = "fake-chat"
    c.embedding = EmbeddingConfig(provider="openai_compatible", model="fake-embed", batch_size=4)
    c.chunking.chunk_size = 100  # ~300 English characters
    c.chunking.overlap = 15
    c.retrieval.min_similarity = 0.0
    return c
