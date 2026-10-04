from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, RunContext
from app.agents.guardrail import Guardrail
from app.agents.runner import run_agent
from app.core.config import Settings
from app.db import repositories as repo
from app.llm.client import LLM

logger = logging.getLogger(__name__)


class ConversationNotFoundError(Exception):
    pass


@dataclass
class ChatResult:
    conversation_id: str
    reply: str
    blocked: bool


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLM,
        settings: Settings,
        orchestrator: Agent,
        guardrail: Guardrail,
    ) -> None:
        self._session = session
        self._llm = llm
        self._settings = settings
        self._orchestrator = orchestrator
        self._guardrail = guardrail

    async def handle(
        self, customer_id: int, message: str, conversation_id: str | None = None
    ) -> ChatResult:
        if conversation_id:
            conversation = await repo.get_conversation(self._session, conversation_id, customer_id)
            if conversation is None:
                raise ConversationNotFoundError(conversation_id)
        else:
            conversation = await repo.create_conversation(self._session, customer_id)

        history = await repo.get_history(
            self._session, conversation.id, self._settings.history_limit
        )

        verdict = await self._guardrail.check(message, history)
        if not verdict.allowed:
            logger.info("Blocked message (category=%s): %s", verdict.category, verdict.reason)
            reply = self._guardrail.denial_message(verdict)
            await self._save_turn(conversation.id, message, reply, blocked=True)
            return ChatResult(conversation.id, reply, blocked=True)

        ctx = RunContext(
            session=self._session,
            customer_id=customer_id,
            llm=self._llm,
            settings=self._settings,
        )
        reply = await run_agent(
            self._orchestrator, ctx, [*history, {"role": "user", "content": message}]
        )
        await self._save_turn(conversation.id, message, reply, blocked=False)
        return ChatResult(conversation.id, reply, blocked=False)

    async def _save_turn(self, conversation_id: str, message: str, reply: str, blocked: bool) -> None:
        await repo.add_message(self._session, conversation_id, "user", message, blocked)
        await repo.add_message(self._session, conversation_id, "assistant", reply, blocked)
        await self._session.commit()
