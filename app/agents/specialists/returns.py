from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.agents.base import Agent, RunContext, Tool
from app.core.config import Settings
from app.db import repositories as repo
from app.db.models import Order, OrderStatus

INSTRUCTIONS = """You are the returns specialist of an online store. The return window is \
{days} days from delivery.
- Always call check_return_eligibility first.
- Only call create_return_request if the request explicitly says the customer has CONFIRMED they \
want to proceed AND gives a reason. Otherwise report the eligibility result and say that the \
customer must confirm and give a reason.
- Never promise refund amounts or timelines; only report what tools return.
Reply with a short, factual summary."""


class OrderRefArgs(BaseModel):
    order_number: str = Field(description="Order number, e.g. ORD-1001")


class CreateReturnArgs(BaseModel):
    order_number: str = Field(description="Order number, e.g. ORD-1001")
    reason: str = Field(min_length=3, max_length=500, description="Customer's reason for returning")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def evaluate_return_eligibility(
    order: Order, has_existing_return: bool, now: datetime, window_days: int
) -> tuple[bool, str]:
    if has_existing_return:
        return False, "A return request already exists for this order."
    if order.status != OrderStatus.DELIVERED or order.delivered_at is None:
        return False, "Only delivered orders can be returned."
    deadline = _as_utc(order.delivered_at) + timedelta(days=window_days)
    if now > deadline:
        return False, f"The {window_days}-day return window ended on {deadline.date().isoformat()}."
    return True, f"Eligible for return until {deadline.date().isoformat()}."


async def check_return_eligibility(ctx: RunContext, args: OrderRefArgs) -> dict:
    order = await repo.get_order_for_customer(ctx.session, ctx.customer_id, args.order_number)
    if order is None:
        return {"found": False, "message": "No order with that number on this account."}
    existing = await repo.get_return_for_order(ctx.session, order.id)
    eligible, detail = evaluate_return_eligibility(
        order, existing is not None, datetime.now(timezone.utc), ctx.settings.return_window_days
    )
    return {"found": True, "order_number": order.order_number, "eligible": eligible, "detail": detail}


async def create_return_request(ctx: RunContext, args: CreateReturnArgs) -> dict:
    order = await repo.get_order_for_customer(ctx.session, ctx.customer_id, args.order_number)
    if order is None:
        return {"created": False, "message": "No order with that number on this account."}
    existing = await repo.get_return_for_order(ctx.session, order.id)
    # Re-check here: never rely on the model having called the eligibility tool.
    eligible, detail = evaluate_return_eligibility(
        order, existing is not None, datetime.now(timezone.utc), ctx.settings.return_window_days
    )
    if not eligible:
        return {"created": False, "message": detail}
    request = await repo.create_return(ctx.session, order.id, args.reason)
    return {
        "created": True,
        "return_id": request.id,
        "order_number": order.order_number,
        "status": request.status.value,
    }


def build_returns_agent(settings: Settings) -> Agent:
    return Agent(
        name="returns_agent",
        description=(
            "Returns specialist: checks whether an order can be returned and, once the customer "
            "has explicitly confirmed and given a reason, creates the return request."
        ),
        instructions=INSTRUCTIONS.format(days=settings.return_window_days),
        tools=(
            Tool("check_return_eligibility", "Check whether an order can be returned.",
                 OrderRefArgs, check_return_eligibility),
            Tool("create_return_request",
                 "Create a return request for an eligible order. Only after customer confirmation.",
                 CreateReturnArgs, create_return_request),
        ),
    )
