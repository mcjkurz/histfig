"""Streaming chat over any OpenAI-compatible /chat/completions endpoint.

Ollama exposes the same API at http://localhost:11434/v1, so one client covers
local and hosted models.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import AsyncIterator

import httpx

from histfig.config import ChatConfig


class ProviderError(RuntimeError):
    pass


def _headers(api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body)
        if isinstance(err, dict):
            err = err.get("message", err)
        return f"HTTP {resp.status_code}: {err}"
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:300]}"


async def list_models(base_url: str, api_key: str = "", timeout: float = 10, path: str = "/models") -> list[str]:
    """Model ids from GET {base_url}/models (works for OpenAI-style APIs and Ollama).

    OpenRouter lists embedding models separately: pass path="/embeddings/models".
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(base_url.rstrip("/") + path, headers=_headers(api_key))
        if resp.status_code != 200:
            raise ProviderError(_error_text(resp))
        data = resp.json().get("data", [])
        return sorted(m["id"] for m in data if "id" in m)


async def available_models(base_url: str, api_key: str = "", embedding: bool = False) -> list[str]:
    """The models a provider offers (OpenRouter keeps embedding models in a separate list)."""
    path = "/embeddings/models" if embedding and "openrouter.ai" in base_url else "/models"
    return await list_models(base_url, api_key, path=path)


def model_available(name: str, models: list[str]) -> bool:
    """Is the model in the provider's list? (Ollama also lists "name:latest" for "name".)"""
    return name in models or f"{name}:latest" in models


def similar(name: str, models: list[str]) -> list[str]:
    """Close matches for a mistyped model name: substring matches first, then fuzzy ones."""
    low = name.lower()
    contains = [m for m in models if low in m.lower()]
    return contains[:6] or difflib.get_close_matches(name, models, n=6, cutoff=0.5)


_THINK_RE = re.compile(r"<think>.*?(</think>\s*|$)", re.DOTALL)


def strip_thinking(text: str) -> str:
    """The answer without inline <think>…</think> reasoning."""
    return _THINK_RE.sub("", text).strip()


async def check_chat(chat) -> str:
    """One tiny request (Settings' Test button, `histfig doctor`); raises on failure."""
    reply = strip_thinking(await chat.complete([{"role": "user", "content": "Reply with the single word: OK"}]))
    return f"replied {reply[:60]!r}" if reply else "empty reply"


class ChatProvider:
    """Yields ("content" | "thinking", text) tuples while streaming a reply."""

    def __init__(self, cfg: ChatConfig):
        self.cfg = cfg

    @property
    def url(self) -> str:
        return self.cfg.base_url.rstrip("/") + "/chat/completions"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout, connect=15),
                                 headers=_headers(self.cfg.resolved_key()))

    async def stream(
        self, messages: list[dict], model: str | None = None, temperature: float | None = None
    ) -> AsyncIterator[tuple[str, str]]:
        payload = {
            "model": model or self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "stream": True,
        }
        try:
            async with self._client() as client:
                async with client.stream("POST", self.url, json=payload) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        raise ProviderError(_error_text(resp))
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("error"):
                            raise ProviderError(str(chunk["error"]))
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta") or {}
                            thinking = delta.get("reasoning_content") or delta.get("reasoning")
                            if thinking:
                                yield "thinking", thinking
                            if delta.get("content"):
                                yield "content", delta["content"]
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach {self.url}: {e!r}") from e

    async def call_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
        """One non-streaming call that may use tools; returns the reply message
        ({"content": ..., "tool_calls": [...]}). Used by agent search."""
        payload = {"model": model or self.cfg.model, "messages": messages, "tools": tools,
                   "tool_choice": "auto", "temperature": 0}
        try:
            async with self._client() as client:
                resp = await client.post(self.url, json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach {self.url}: {e!r}") from e
        if resp.status_code != 200:
            raise ProviderError(_error_text(resp))
        body = resp.json()
        if body.get("error") or not body.get("choices"):
            raise ProviderError(str(body.get("error") or "empty reply"))
        return body["choices"][0].get("message") or {}

    async def complete(self, messages: list[dict], model: str | None = None) -> str:
        parts = [text async for kind, text in self.stream(messages, model) if kind == "content"]
        return "".join(parts)
