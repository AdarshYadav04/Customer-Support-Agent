from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.client import LLM, LLMUnavailableError

logger = logging.getLogger(__name__)


@dataclass
class RunContext:
    """Per-request context handed to every tool.

    `customer_id` comes from authentication, never from the LLM, so tools can only
    ever touch the signed-in customer's data.
    """

    session: AsyncSession
    customer_id: int
    llm: LLM
    settings: Settings


ArgsT = TypeVar("ArgsT", bound=BaseModel)


class Tool(Generic[ArgsT]):
    """A function the model can call. Arguments are validated with Pydantic."""

    def __init__(
        self,
        name: str,
        description: str,
        params: type[ArgsT],
        handler: Callable[[RunContext, ArgsT], Awaitable[Any]],
    ) -> None:
        self.name = name
        self.description = description
        self.params = params
        self.handler = handler

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.params.model_json_schema(),
        }

    async def run(self, ctx: RunContext, arguments: str) -> str:
        try:
            args = self.params.model_validate_json(arguments or "{}")
        except ValidationError as exc:
            details = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            return json.dumps({"error": "invalid_arguments", "details": details})
        try:
            result = await self.handler(ctx, args)
        except LLMUnavailableError:
            raise
        except Exception:
            logger.exception("Tool %s failed", self.name)
            return json.dumps({"error": "tool_failed"})
        return json.dumps(result, default=str)


@dataclass(frozen=True)
class Agent:
    name: str
    description: str
    instructions: str
    tools: tuple[Tool, ...] = ()
    model: str | None = None  # falls back to settings.agent_model
