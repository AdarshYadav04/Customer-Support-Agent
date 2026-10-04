import json

from app.agents.base import RunContext
from app.agents.specialists.order_status import build_order_status_agent
from app.agents.specialists.product import build_product_agent
from app.agents.specialists.returns import build_returns_agent
from app.core.config import Settings


def make_ctx(session, customer_id: int) -> RunContext:
    return RunContext(session=session, customer_id=customer_id, llm=None, settings=Settings())


async def run_tool(agent, name: str, ctx: RunContext, **args) -> dict:
    tool = {t.name: t for t in agent.tools}[name]
    return json.loads(await tool.run(ctx, json.dumps(args)))


async def test_order_status_found(session):
    result = await run_tool(
        build_order_status_agent(), "get_order_status", make_ctx(session, 1), order_number="ord-1002"
    )
    assert result["found"] and result["status"] == "shipped"
    assert result["tracking_number"] == "DL987654321"


async def test_order_lookup_is_scoped_to_customer(session):
    # ORD-1001 belongs to customer 1; customer 2 must not see it.
    result = await run_tool(
        build_order_status_agent(), "get_order_status", make_ctx(session, 2), order_number="ORD-1001"
    )
    assert result["found"] is False


async def test_invalid_arguments_return_error(session):
    tool = build_order_status_agent().tools[0]
    out = json.loads(await tool.run(make_ctx(session, 1), "{}"))
    assert out["error"] == "invalid_arguments"


async def test_return_eligibility_rules(session):
    agent = build_returns_agent(Settings())
    ctx = make_ctx(session, 1)
    ok = await run_tool(agent, "check_return_eligibility", ctx, order_number="ORD-1001")
    assert ok["eligible"] is True
    too_old = await run_tool(agent, "check_return_eligibility", ctx, order_number="ORD-1003")
    assert too_old["eligible"] is False and "window" in too_old["detail"]
    not_delivered = await run_tool(agent, "check_return_eligibility", ctx, order_number="ORD-1002")
    assert not_delivered["eligible"] is False


async def test_create_return_once_only(session):
    agent = build_returns_agent(Settings())
    ctx = make_ctx(session, 1)
    first = await run_tool(
        agent, "create_return_request", ctx, order_number="ORD-1001", reason="Left earbud is dead"
    )
    assert first["created"] is True and first["status"] == "requested"
    second = await run_tool(
        agent, "create_return_request", ctx, order_number="ORD-1001", reason="Again"
    )
    assert second["created"] is False


async def test_create_return_blocked_when_ineligible(session):
    result = await run_tool(
        build_returns_agent(Settings()), "create_return_request", make_ctx(session, 1),
        order_number="ORD-1003", reason="Changed my mind",
    )
    assert result["created"] is False


async def test_product_search_and_stock(session):
    agent = build_product_agent()
    ctx = make_ctx(session, 1)
    found = await run_tool(agent, "search_products", ctx, query="wireless earbuds")
    assert [p["sku"] for p in found["products"]] == ["AUD-1001"]
    keyboard = await run_tool(agent, "get_product", ctx, sku="key-2001")
    assert keyboard["in_stock"] is False
