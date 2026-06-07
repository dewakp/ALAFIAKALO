"""AI / LLM schemas."""

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class AIQueryRequest(BaseModel):
    query: str
    messages: list[ChatMessage] | None = None  # prior conversation turns
    context_module: str | None = None  # nutrition, fitness, labs, medications, mood, lifestyle
    include_history: bool = False
    persona: str | None = None  # babalawo, dibia, boka, sage, curandero, ...
    model: str | None = None    # override default model (e.g. gpt-oss:20b)


class AIQueryResponse(BaseModel):
    response: str
    module: str | None = None
    confidence: float | None = None
    persona: str | None = None


class AIPersonaOut(BaseModel):
    key: str
    title: str
    origin: str
    region: str
    greeting: str
    description: str
    icon: str | None = None
    specialty: str | None = None
    capabilities: list[str] | None = None


class AIPersonaGroup(BaseModel):
    region: str
    label: str
    personas: list[AIPersonaOut]


class AIQueryResponseWithMemory(AIQueryResponse):
    """Extended response that also returns the saved interaction ID for feedback."""
    interaction_id: int | None = None


class AIFeedbackRequest(BaseModel):
    interaction_id: int
    was_helpful: bool
    user_feedback: str | None = None
    was_followed: bool | None = None


class AIFeedbackResponse(BaseModel):
    ok: bool
    interaction_id: int
