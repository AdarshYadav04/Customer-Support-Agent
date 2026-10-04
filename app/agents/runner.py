from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import Agent, RunContext

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I couldn't complete that just now. Please try again in a moment."


async def run_agent(agent: Agent, ctx: RunContext, messages: list[dict[str, Any]]) -> str:
    """Run one agent to completion: call the model, execute tool calls, repeat."""
    tools = {t.name: t for t in agent.tools}
    specs = [t.spec() for t in agent.tools] or None
    items: list[dict[str, Any]] = list(messages)

    for _ in range(ctx.settings.max_tool_iterations):
        response = await ctx.llm.respond(
            model=agent.model or ctx.settings.agent_model,
            instructions=agent.instructions,
            input=items,
            tools=specs,
        )
        calls = [o for o in response.output if getattr(o, "type", None) == "function_call"]
        if not calls:
            return (response.output_text or "").strip() or FALLBACK_REPLY

        items.extend(o.model_dump(exclude_none=True) for o in response.output)
        for call in calls:
            tool = tools.get(call.name)
            if tool is None:
                output = json.dumps({"error": f"unknown_tool: {call.name}"})
            else:
                logger.info("agent=%s tool=%s", agent.name, call.name)
                output = await tool.run(ctx, call.arguments)
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": output})

    logger.warning("agent=%s hit max_tool_iterations", agent.name)
    return FALLBACK_REPLY
