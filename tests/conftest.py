import os

# Required settings; real values come from .env in normal use.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LITELLM_PROXY_URL", "http://localhost:4000/v1")
os.environ.setdefault("LITELLM_PROXY_KEY", "sk-test")

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.seed import seed  # noqa: E402
from app.db.session import create_session_factory  # noqa: E402


@pytest_asyncio.fixture
async def session():
    """In-memory SQLite with demo data (customer 1 = Alex, customer 2 = Sam)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with create_session_factory(engine)() as s:
        await seed(s)
        yield s
    await engine.dispose()
