import pytest
from sqlalchemy import select

from app.agents.guardrail import Guardrail
from app.agents.orchestrator import build_orchestrator
from app.core.config import Settings
from app.db.models import Message
from app.llm.client import LLMUnavailableError
from app.services.chat import ChatService, ConversationNotFoundError
from tests.fakes import ScriptedLLM, shipping_flow, text, verdict


def make_service(session, llm) -> ChatService:
    settings = Settings()
    return ChatService(session, llm, settings, build_orchestrator(settings), Guardrail(llm, settings))


async def test_allowed_message_goes_through_orchestrator_and_specialist(session):
    llm = ScriptedLLM(shipping_flow)
    result = await make_service(session, llm).handle(1, "Where is my order ORD-1002?")

    assert result.blocked is False
    assert result.reply == "Your order ORD-1002 has shipped and arrives soon!"
    # The specialist's tool result (real DB data) was fed back to the model.
    outputs = [
        i["output"] for c in llm.calls for i in c["input"] if i.get("type") == "function_call_output"
    ]
    assert any("DL987654321" in o for o in outputs)

    rows = (await session.execute(select(Message).order_by(Message.id))).scalars().all()
    assert [(m.role, m.blocked) for m in rows] == [("user", False), ("assistant", False)]


async def test_off_topic_message_is_denied_without_running_agents(session):
    llm = ScriptedLLM(lambda kw: verdict(False, "off_topic"))
    result = await make_service(session, llm).handle(1, "Write me a poem about the moon")

    assert result.blocked is True
    assert "orders, deliveries, returns" in result.reply
    assert len(llm.calls) == 1  # only the guardrail ran
    rows = (await session.execute(select(Message))).scalars().all()
    assert all(m.blocked for m in rows)


async def test_history_is_reused_within_a_conversation(session):
    llm = ScriptedLLM(shipping_flow)
    service = make_service(session, llm)
    first = await service.handle(1, "Where is ORD-1002?")
    llm.calls.clear()
    await service.handle(1, "thanks!", first.conversation_id)
    orchestrator_call = next(c for c in llm.calls if not c.get("json_mode"))
    assert [m["role"] for m in orchestrator_call["input"][:3]] == ["user", "assistant", "user"]


async def test_conversation_of_other_customer_is_not_accessible(session):
    llm = ScriptedLLM(shipping_flow)
    first = await make_service(session, llm).handle(1, "Where is ORD-1002?")
    with pytest.raises(ConversationNotFoundError):
        await make_service(session, llm).handle(2, "hi", first.conversation_id)


async def test_invalid_guardrail_output_fails_closed(session):
    llm = ScriptedLLM(lambda kw: text("not json"))
    with pytest.raises(LLMUnavailableError):
        await make_service(session, llm).handle(1, "hello")
    assert len(llm.calls) == 1
