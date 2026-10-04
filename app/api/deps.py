from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db import repositories as repo
from app.db.models import Customer
from app.services.chat import ChatService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def verify_api_key(
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.service_api_key
    if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


async def get_current_customer(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_customer_id: Annotated[int, Header()],
) -> Customer:
    """Identify the signed-in customer.

    Trusts the `X-Customer-Id` header, which is only safe behind an API gateway that
    authenticates the user and sets it. Swap this for JWT/session auth if exposed directly.
    """
    customer = await repo.get_customer(session, x_customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown customer")
    return customer


def get_chat_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> ChatService:
    state = request.app.state
    return ChatService(
        session=session,
        llm=state.llm,
        settings=state.settings,
        orchestrator=state.orchestrator,
        guardrail=state.guardrail,
    )
