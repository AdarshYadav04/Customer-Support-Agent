from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import Agent, RunContext, Tool
from app.agents.runner import run_agent
from app.agents.specialists.order_status import build_order_status_agent
from app.agents.specialists.product import build_product_agent
from app.agents.specialists.returns import build_returns_agent
from app.core.config import Settings

INSTRUCTIONS = """You are the lead customer-support agent for {store}, an online store. You \
coordinate specialist agents, which you call as tools:
- order_status_agent: order status, tracking, delivery estimates, recent orders
- returns_agent: return eligibility and creating return requests
- product_agent: product search, details, price, stock

Rules:
- Never state order, return or product facts yourself; always get them from a specialist.
- Make each specialist request self-contained: include order numbers, product names and what the \
customer wants.
- If a required detail is missing (e.g. an order number), ask the customer instead of guessing.
- Call several specialists if the message covers several topics.
- Ask returns_agent to create a return only after the customer has explicitly confirmed it and \
given a reason; say so in the request.
- Reply to the customer in a short, friendly, plain-text message. Never mention agents, tools or \
internal systems.
- Only help with orders, delivery, returns and products. Politely decline anything else."""


class DelegateArgs(BaseModel):
    request: str = Field(description="Self-contained request for the specialist")


def delegate_tool(agent: Agent) -> Tool[DelegateArgs]:
    """Expose a specialist agent to the orchestrator as a tool."""

    async def handler(ctx: RunContext, args: DelegateArgs) -> dict:
        reply = await run_agent(agent, ctx, [{"role": "user", "content": args.request}])
        return {"reply": reply}

    return Tool(agent.name, agent.description, DelegateArgs, handler)


def build_orchestrator(settings: Settings) -> Agent:
    specialists = [
        build_order_status_agent(),
        build_returns_agent(settings),
        build_product_agent(),
    ]
    return Agent(
        name="support_orchestrator",
        description="Routes customer requests to specialist agents.",
        instructions=INSTRUCTIONS.format(store=settings.store_name),
        tools=tuple(delegate_tool(a) for a in specialists),
    )
