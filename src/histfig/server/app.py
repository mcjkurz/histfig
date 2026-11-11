"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from histfig.config import ChatConfig, Config
from histfig.db import Database
from histfig.ingest.jobs import IngestWorker
from histfig.providers.chat import ChatProvider, list_models
from histfig.providers.embed import Embedder, make_embedder
from histfig.retrieval.search import SearchIndex
from histfig.server.public import RateLimiter, delete_old_visitor_conversations, visitor_cookie

STATIC_DIR = Path(str(resources.files("histfig") / "static"))


class ModelCache:
    """The chat provider's model list, fetched once and kept for an hour.

    Fetching it from e.g. OpenRouter takes ~1 s, so it is prefetched at startup
    and never fetched on every page view.
    """

    max_age = 3600.0

    def __init__(self, cfg: ChatConfig):
        self.cfg = cfg
        self.models: list[str] | None = None
        self.fetched_at = 0.0
        self._task: asyncio.Task | None = None

    async def _fetch(self) -> list[str]:
        models = await list_models(self.cfg.base_url, self.cfg.resolved_key())
        self.models, self.fetched_at = models, time.monotonic()
        return models

    def _start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._fetch())
            self._task.add_done_callback(lambda t: t.cancelled() or t.exception())  # no "never retrieved" noise
        return self._task

    def prefetch(self) -> None:
        self._start()

    async def get(self) -> list[str]:
        if self.models is not None and time.monotonic() - self.fetched_at < self.max_age:
            return self.models
        return await asyncio.shield(self._start())


@dataclass
class AppState:
    cfg: Config
    data_dir: Path
    db: Database
    index: SearchIndex
    embedder: Embedder
    chat: ChatProvider
    worker: IngestWorker
    models: ModelCache = field(default=None)  # type: ignore[assignment]
    prefetch_models: bool = True
    public: bool = False
    limiter: object = None  # public.RateLimiter in public mode

    def apply_config(self, new: Config) -> None:
        """Use a new configuration right away (saved from the Settings page)."""
        old, self.cfg = self.cfg, new
        if new.chat != old.chat:
            self.chat.cfg = new.chat  # the provider only reads its settings; no need to rebuild it
            self.models = ModelCache(new.chat)
            if self.prefetch_models:
                self.models.prefetch()
        if new.embedding != old.embedding:
            self.embedder = make_embedder(new.embedding, key=self.embedding_key)
            self.worker.embedder = self.embedder

    def embedding_key(self) -> str:
        return self.cfg.embedding_key()  # always the current settings (shares the chat key)
        self.worker.cfg = new

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"


async def _clean_up_daily(state: AppState) -> None:
    """Delete old visitor conversations at start-up and then once a day."""
    log = logging.getLogger("histfig")
    while True:
        try:
            n = delete_old_visitor_conversations(state.db, state.cfg.public.keep_days)
            if n:
                log.info("Deleted %d visitor conversation(s) unused for %d days", n, state.cfg.public.keep_days)
        except Exception:
            log.exception("Clean-up of visitor conversations failed")
        await asyncio.sleep(24 * 3600)


def create_app(
    cfg: Config,
    data_dir: Path,
    embedder: Embedder | None = None,
    chat: ChatProvider | None = None,
    prefetch_models: bool = True,
    public: bool = False,
) -> FastAPI:
    data_dir = Path(data_dir)
    db = Database(data_dir / "histfig.db")
    index = SearchIndex(db)
    embedder = embedder or make_embedder(cfg.embedding)
    chat = chat or ChatProvider(cfg.chat)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state = AppState(cfg, data_dir, db, index, embedder, chat,
                         IngestWorker(db, cfg, embedder, index), ModelCache(cfg.chat), prefetch_models,
                         public, RateLimiter(cfg.public.messages_per_hour) if public else None)
        if prefetch_models:
            state.models.prefetch()
        state.uploads_dir.mkdir(parents=True, exist_ok=True)
        state.images_dir.mkdir(parents=True, exist_ok=True)
        app.state.hf = state
        state.embedder.key = state.embedding_key
        state.worker.start()
        cleaner = asyncio.create_task(_clean_up_daily(state))
        logging.getLogger("histfig").info("Data directory: %s", data_dir)
        yield
        cleaner.cancel()
        await state.worker.stop()

    app = FastAPI(title="HistFig", lifespan=lifespan)
    if public:
        app.middleware("http")(visitor_cookie)

    from histfig.server.api import router

    app.include_router(router, prefix="/api")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index_page():
        return FileResponse(STATIC_DIR / "index.html")

    return app
