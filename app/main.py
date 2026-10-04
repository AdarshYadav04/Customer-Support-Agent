from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.guardrail import Guardrail
from app.agents.orchestrator import build_orchestrator
from app.api.routes import chat_router, health_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.models import Base
from app.db.session import create_engine, create_session_factory
from app.llm.client import LLM, OpenAIResponsesClient


def create_app(llm: LLM | None = None) -> FastAPI:
    """App factory. Pass `llm` to inject a fake client (tests)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        setup_logging(settings.log_level)

        engine = create_engine(settings.database_url)
        if settings.auto_create_tables:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        llm_client = llm or OpenAIResponsesClient(settings)
        app.state.settings = settings
        app.state.session_factory = create_session_factory(engine)
        app.state.llm = llm_client
        app.state.orchestrator = build_orchestrator(settings)
        app.state.guardrail = Guardrail(llm_client, settings)
        try:
            yield
        finally:
            await llm_client.aclose()
            await engine.dispose()

    app = FastAPI(title="Ecommerce Support Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
