import asyncio

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.models import Base
from app.db.seed import seed
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from tests.fakes import ScriptedLLM, shipping_flow, verdict


def _prepare_db(url: str) -> None:
    async def run() -> None:
        engine = create_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with create_session_factory(engine)() as session:
            await seed(session)
        await engine.dispose()

    asyncio.run(run())


def test_chat_endpoint(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SERVICE_API_KEY", "secret")
    get_settings.cache_clear()
    _prepare_db(url)

    def handler(kw):
        if kw.get("json_mode") and "poem" in kw["input"][0]["content"]:
            return verdict(False, "off_topic")
        return shipping_flow(kw)

    try:
        with TestClient(create_app(llm=ScriptedLLM(handler))) as client:
            headers = {"X-API-Key": "secret", "X-Customer-Id": "1"}

            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/ready").status_code == 200

            body = {"message": "Where is ORD-1002?"}
            assert client.post("/v1/chat", json=body).status_code == 401  # no API key
            assert client.post(
                "/v1/chat", json=body, headers={**headers, "X-Customer-Id": "99"}
            ).status_code == 401  # unknown customer

            ok = client.post("/v1/chat", json=body, headers=headers)
            assert ok.status_code == 200
            assert ok.json()["blocked"] is False and "shipped" in ok.json()["reply"]

            denied = client.post("/v1/chat", json={"message": "write a poem"}, headers=headers)
            assert denied.json()["blocked"] is True

            assert client.post("/v1/chat", json={"message": "   "}, headers=headers).status_code == 422
            missing = client.post(
                "/v1/chat", json={**body, "conversation_id": "nope"}, headers=headers
            )
            assert missing.status_code == 404
    finally:
        get_settings.cache_clear()
