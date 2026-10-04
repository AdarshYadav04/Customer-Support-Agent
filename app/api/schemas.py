from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ChatRequest(BaseModel):
    message: Message
    conversation_id: str | None = Field(
        default=None, description="Omit to start a new conversation."
    )


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    blocked: bool = Field(description="True when the guardrail declined the message.")
