import pytest
from app.services.router import LLMRouter
from app.models.chat import ChatRequest
from app.core.config import settings

@pytest.mark.asyncio
async def test_router_openai_fallback(monkeypatch):
    # TODO: Mock OpenAIAdapter to fail, AnthropicAdapter to succeed
    pass
