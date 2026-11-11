"""Interactive setup: a few questions, then writes data/config.toml. Safe to re-run.

Only values you already have are offered as [defaults]; nothing is suggested
for you (no example models or URLs pre-filled).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from histfig.config import (
    OLLAMA_URL,
    OPENROUTER_URL,
    Config,
    load_config,
    save_config,
    suggested_prefixes,
)
from histfig.providers.chat import available_models as fetch_models
from histfig.providers.chat import similar

# (id, label, provider, base_url — None means "ask")
CHAT_SERVICES = [
    ("openrouter", "OpenRouter — one API key, many models (https://openrouter.ai)", "openai_compatible", OPENROUTER_URL),
    ("ollama", "Ollama — local models, free and private (https://ollama.com)", "ollama", OLLAMA_URL),
    ("other", "Another OpenAI-compatible API (OpenAI, LM Studio, vLLM, …)", "openai_compatible", None),
]
EMBED_SERVICES = CHAT_SERVICES + [
    ("local", "sentence-transformers — runs inside HistFig (needs `uv sync --extra local`)",
     "sentence_transformers", ""),
]
MODEL_HINTS = {
    "openrouter": "Model names are listed at https://openrouter.ai/models (e.g. vendor/model-name).",
    "ollama": "Run `ollama list` to see your installed models (`ollama pull <name>` to get one).",
    "local": "Use a Hugging Face model name (owner/model-name).",
}


def ask(prompt: str, default: str = "", required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{suffix}: ").strip() or default
        if answer or not required:
            return answer
        print("  This one is required.")


def ask_int(prompt: str, default: int, minimum: int) -> int:
    while True:
        answer = ask(prompt, str(default))
        if answer.isdigit() and int(answer) >= minimum:
            return int(answer)
        print(f"  Please enter a whole number ≥ {minimum}.")


def yes(prompt: str) -> bool:
    return not input(f"{prompt} (Y/n): ").strip().lower().startswith("n")


def choose(services: list[tuple], current: str) -> str:
    for i, (sid, label, *_) in enumerate(services, start=1):
        print(f"  {i}. {label}{'  (current)' if sid == current else ''}")
    default = next((str(i) for i, s in enumerate(services, 1) if s[0] == current), "1")
    while True:
        answer = ask("Choose a number", default)
        if answer.isdigit() and 1 <= int(answer) <= len(services):
            return services[int(answer) - 1][0]
        print("  Please enter one of the numbers above.")


def service_of(section) -> str:
    if section.provider == "ollama":
        return "ollama"
    if section.provider == "sentence_transformers":
        return "local"
    return "openrouter" if section.base_url.rstrip("/") == OPENROUTER_URL else "other"


def ask_key(section) -> None:
    keep = " [keep current key]" if section.api_key else ""
    key = input(f"API key — paste it, or press Enter to use an environment variable{keep}: ").strip()
    if key:
        section.api_key, section.api_key_env = key, ""
    elif not section.api_key:
        section.api_key_env = ask("Name of the environment variable holding the key", section.api_key_env,
                                  required=True)
        if not os.environ.get(section.api_key_env):
            print(f"  Note: ${section.api_key_env} is not set in this shell right now.")


def available_models(section, sid: str, embedding: bool) -> list[str] | None:
    """The provider's model ids, or None if they can't be listed (then names aren't checked)."""
    if sid == "local":
        return None
    try:
        return asyncio.run(fetch_models(section.base_url, section.resolved_key(), embedding))
    except Exception as e:
        print(f"  Could not get the model list from {section.base_url} ({e}).")
        if sid == "ollama":
            print("  Is Ollama running? The model name won't be checked.")
        else:
            print("  The model name won't be checked.")
        return None


def ask_model(section, sid: str, default: str, embedding: bool) -> str:
    models = available_models(section, sid, embedding)
    while True:
        name = ask("Model name", default, required=True)
        if models is None or name in models or f"{name}:latest" in models:
            return name
        print(f"  '{name}' is not available at {section.base_url}.")
        matches = similar(name, models)
        if matches:
            print("  Did you mean: " + ", ".join(matches))
        if sid == "ollama":
            print(f"  To download it, run: ollama pull {name}")
        # Pre-fill the obvious fix: the same name with a vendor prefix, or the only match.
        exact = [m for m in matches if m.lower().endswith("/" + name.lower())]
        default = exact[0] if exact else (matches[0] if len(matches) == 1 else "")


def setup_service(section, services: list[tuple], shared=None, embedding: bool = False) -> bool:
    """Ask for service, URL, key and model. Returns True if the model changed."""
    current = service_of(section)
    sid = choose(services, current)
    _, _, provider, url = next(s for s in services if s[0] == sid)
    switched = sid != current
    section.provider = provider

    if url is None:
        section.base_url = ask("Base URL of the API (ends in /v1)", "" if switched else section.base_url,
                               required=True)
    else:
        section.base_url = url

    if provider == "ollama":
        section.api_key, section.api_key_env = "", ""
    elif provider == "openai_compatible":
        if switched:
            section.api_key, section.api_key_env = "", ""
        same_as_chat = shared is not None and shared.base_url == section.base_url
        if same_as_chat and yes("Use the same API key as the chat model?"):
            section.api_key, section.api_key_env = shared.api_key, shared.api_key_env
        else:
            ask_key(section)

    if embedding and sid == "openrouter":
        print("  Embedding models are listed at https://openrouter.ai/models?output_modalities=embeddings")
    elif sid in MODEL_HINTS:
        print(f"  {MODEL_HINTS[sid]}")
    old_model = section.model
    section.model = ask_model(section, sid, "" if switched else section.model, embedding)
    return section.model != old_model


def run_wizard(data_dir: Path) -> Config:
    existing = load_config(data_dir)
    cfg = existing or Config()
    print("HistFig setup. Press Enter to keep a value shown in [brackets]; Ctrl+C cancels.")
    if existing:
        print(f"Editing {data_dir / 'config.toml'}")

    print("\n== 1/3  Chat model (writes the answers) ==")
    setup_service(cfg.chat, CHAT_SERVICES)

    print("\n== 2/3  Embedding model (finds the relevant passages) ==")
    e = cfg.embedding
    if setup_service(e, EMBED_SERVICES, shared=cfg.chat, embedding=True):
        e.query_prefix, e.document_prefix = suggested_prefixes(e.model)
        if e.query_prefix or e.document_prefix:
            print("  Using the recommended query/document prefixes for this model.")

    print("\n== 3/3  Passages (how texts are split up) ==")
    cfg.chunking.chunk_size = ask_int("Characters per passage", cfg.chunking.chunk_size, 100)
    cfg.chunking.overlap = ask_int("Overlap between passages (characters)", cfg.chunking.overlap, 0)

    for problem in cfg.validate():
        print(f"Warning: {problem}")
    path = save_config(cfg, data_dir)
    print(f"\nSaved {path} (you can also edit it by hand).")
    return cfg
