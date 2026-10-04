from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import Agent, RunContext, Tool
from app.db import repositories as repo
from app.db.models import Order

INSTRUCTIONS = """You are the order-status specialist of an online store.
Use your tools to look up the current customer's orders and report status, tracking details and \
delivery estimates. Only state facts returned by tools. If an order is not found, say so and \
suggest double-checking the order number. Reply with a short, factual summary."""


class GetOrderStatusArgs(BaseModel):
    order_number: str = Field(description="Order number, e.g. ORD-1001")


class ListRecentOrdersArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=10, description="How many recent orders to return")


def _serialize(order: Order) -> dict:
    return {
        "order_number": order.order_number,
        "status": order.status.value,
        "placed_at": order.placed_at,
        "total": order.total,
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery,
        "delivered_at": order.delivered_at,
        "items": [{"name": i.product.name, "quantity": i.quantity} for i in order.items],
    }


async def get_order_status(ctx: RunContext, args: GetOrderStatusArgs) -> dict:
    order = await repo.get_order_for_customer(ctx.session, ctx.customer_id, args.order_number)
    if order is None:
        return {"found": False, "message": "No order with that number on this account."}
    return {"found": True, **_serialize(order)}


async def list_recent_orders(ctx: RunContext, args: ListRecentOrdersArgs) -> dict:
    orders = await repo.list_recent_orders(ctx.session, ctx.customer_id, args.limit)
    return {"orders": [_serialize(o) for o in orders]}


def build_order_status_agent() -> Agent:
    return Agent(
        name="order_status_agent",
        description=(
            "Order status specialist: looks up an order's status, tracking number, carrier and "
            "delivery estimate, or lists the customer's recent orders."
        ),
        instructions=INSTRUCTIONS,
        tools=(
            Tool("get_order_status", "Get status and tracking details for one order.",
                 GetOrderStatusArgs, get_order_status),
            Tool("list_recent_orders", "List the customer's most recent orders.",
                 ListRecentOrdersArgs, list_recent_orders),
        ),
    )
