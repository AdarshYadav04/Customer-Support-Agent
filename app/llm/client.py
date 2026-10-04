from __future__ import annotations

import logging
from typing import Any, Protocol

import openai
from openai import AsyncOpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """The LLM backend failed or returned something unusable."""


class LLM(Protocol):
    async def respond(
        self,
        *,
        model: str,
        instructions: str,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> Any: ...

    async def aclose(self) -> None: ...


class OpenAIResponsesClient:
    """Thin wrapper over the OpenAI Responses API, pointed at the LiteLLM proxy."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.litellm_proxy_url,
            api_key=settings.litellm_proxy_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    async def respond(
        self,
        *,
        model: str,
        instructions: str,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input,
            "store": False,  # we keep conversation state in Postgres
        }
        if tools:
            kwargs["tools"] = tools
        if json_mode:
            kwargs["text"] = {"format": {"type": "json_object"}}
        try:
            return await self._client.responses.create(**kwargs)
        except openai.OpenAIError as exc:
            logger.exception("LLM request failed (model=%s)", model)
            raise LLMUnavailableError("LLM request failed") from exc

    async def aclose(self) -> None:
        await self._client.close()
