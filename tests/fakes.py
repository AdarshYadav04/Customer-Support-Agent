import json
from types import SimpleNamespace
from typing import Any, Callable

from openai.types.responses import ResponseFunctionToolCall


def text(content: str) -> SimpleNamespace:
    return SimpleNamespace(output=[], output_text=content)


def call(name: str, args: dict, call_id: str = "call_1") -> SimpleNamespace:
    item = ResponseFunctionToolCall(
        type="function_call", call_id=call_id, name=name, arguments=json.dumps(args)
    )
    return SimpleNamespace(output=[item], output_text="")


def verdict(allowed: bool, category: str = "ok") -> SimpleNamespace:
    return text(json.dumps({"allowed": allowed, "category": category, "reason": "test"}))


class ScriptedLLM:
    """Fake LLM: `handler(kwargs)` returns the next response and every call is recorded."""

    def __init__(self, handler: Callable[[dict[str, Any]], SimpleNamespace]) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    async def respond(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.handler(kwargs)

    async def aclose(self) -> None:
        pass


def shipping_flow(kw: dict[str, Any]) -> SimpleNamespace:
    """Guardrail allows; orchestrator -> order_status_agent -> get_order_status -> answer."""
    if kw.get("json_mode"):
        return verdict(True)
    last = kw["input"][-1]
    came_back_from_tool = last.get("type") == "function_call_output"
    if "lead customer-support agent" in kw["instructions"]:
        if came_back_from_tool:
            return text("Your order ORD-1002 has shipped and arrives soon!")
        return call("order_status_agent", {"request": "Status of order ORD-1002"})
    if "order-status specialist" in kw["instructions"]:
        if came_back_from_tool:
            return text("ORD-1002 is shipped via Delhivery.")
        return call("get_order_status", {"order_number": "ORD-1002"})
    raise AssertionError("unexpected agent")
