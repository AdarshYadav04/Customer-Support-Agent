from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_chat_service, get_current_customer, get_session, verify_api_key
from app.api.schemas import ChatRequest, ChatResponse
from app.db.models import Customer
from app.llm.client import LLMUnavailableError
from app.services.chat import ChatService, ConversationNotFoundError

chat_router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(verify_api_key)])
health_router = APIRouter(tags=["health"])


@chat_router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    customer: Annotated[Customer, Depends(get_current_customer)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    try:
        result = await service.handle(customer.id, body.message, body.conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    except LLMUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant is temporarily unavailable. Please try again shortly.",
        )
    return ChatResponse(
        conversation_id=result.conversation_id, reply=result.reply, blocked=result.blocked
    )


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable")
    return {"status": "ready"}
