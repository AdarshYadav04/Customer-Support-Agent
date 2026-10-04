from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Conversation,
    Customer,
    Message,
    Order,
    Product,
    ReturnRequest,
)


def _normalize_order_number(order_number: str) -> str:
    return order_number.strip().upper()


# --- customers -------------------------------------------------------------
async def get_customer(session: AsyncSession, customer_id: int) -> Customer | None:
    return await session.get(Customer, customer_id)


# --- orders ----------------------------------------------------------------
async def get_order_for_customer(
    session: AsyncSession, customer_id: int, order_number: str
) -> Order | None:
    """Always scoped to the customer: one customer can never read another's order."""
    stmt = select(Order).where(
        Order.customer_id == customer_id,
        Order.order_number == _normalize_order_number(order_number),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_recent_orders(
    session: AsyncSession, customer_id: int, limit: int = 5
) -> Sequence[Order]:
    stmt = (
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.placed_at.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).scalars().all()


# --- returns ---------------------------------------------------------------
async def get_return_for_order(session: AsyncSession, order_id: int) -> ReturnRequest | None:
    stmt = select(ReturnRequest).where(ReturnRequest.order_id == order_id).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_return(session: AsyncSession, order_id: int, reason: str) -> ReturnRequest:
    request = ReturnRequest(order_id=order_id, reason=reason)
    session.add(request)
    await session.flush()
    return request


# --- products --------------------------------------------------------------
def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def search_products(session: AsyncSession, query: str, limit: int = 5) -> Sequence[Product]:
    terms = [t for t in re.split(r"\s+", query.strip()) if t][:5]
    if not terms:
        return []
    conditions = [
        or_(
            Product.name.ilike(_like(t), escape="\\"),
            Product.description.ilike(_like(t), escape="\\"),
        )
        for t in terms
    ]
    stmt = select(Product).where(and_(*conditions)).order_by(Product.name).limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def get_product_by_sku(session: AsyncSession, sku: str) -> Product | None:
    stmt = select(Product).where(Product.sku == sku.strip().upper())
    return (await session.execute(stmt)).scalar_one_or_none()


# --- conversations ---------------------------------------------------------
async def create_conversation(session: AsyncSession, customer_id: int) -> Conversation:
    conversation = Conversation(customer_id=customer_id)
    session.add(conversation)
    await session.flush()
    return conversation


async def get_conversation(
    session: AsyncSession, conversation_id: str, customer_id: int
) -> Conversation | None:
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.customer_id == customer_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_history(session: AsyncSession, conversation_id: str, limit: int) -> list[dict]:
    """Last `limit` non-blocked messages, oldest first, in Responses API input format."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.blocked.is_(False))
        .order_by(Message.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


async def add_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    blocked: bool = False,
) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content, blocked=blocked)
    session.add(message)
    await session.flush()
    return message
