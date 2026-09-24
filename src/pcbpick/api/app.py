"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pcbpick.api import orchestrator
from pcbpick.api.db import init_db, make_engine, make_session_factory
from pcbpick.api.routers import projects, runs, users
from pcbpick.api.settings import Settings, get_settings
from pcbpick.llm.ollama_client import OllamaLLMClient, ensure_ollama_running


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Only when PCBPICK_USE_LLM=1 -- default_llm_client() returns None otherwise,
    # so this never attempts a live network call in tests or the default run.
    llm_client = orchestrator.default_llm_client()
    if isinstance(llm_client, OllamaLLMClient):
        ensure_ollama_running(base_url=llm_client.base_url)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="pcbpick", version="0.1.0", lifespan=_lifespan)

    engine = make_engine(settings.database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.settings = settings

    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(users.router)
    app.include_router(projects.router)
    app.include_router(runs.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
