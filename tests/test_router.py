import pytest
from app.services.router import LLMRouter
from app.models.chat import ChatRequest
from app.core.config import settings

@pytest.mark.asyncio
async def test_router_openai_fallback(monkeypatch):
    from app.services.router import LLMRouter
    from app.models.chat import ChatRequest, ChatMessage
    import httpx

    # Dummy config
    config = {
        "default_provider": "openai",
        "enable_fallback": True,
        "providers": {
            "openai": {"api_key": "fake"},
            "anthropic": {"api_key": "fake"},
        }
    }
    client = httpx.AsyncClient()
    router = LLMRouter(config, client)

    # Patch adapters in router
    class FailingOpenAI:
        async def complete(self, request, client):
            raise httpx.HTTPStatusError("fail", request=None, response=type('obj', (object,), {'status_code': 503})())
    class SucceedingAnthropic:
        async def complete(self, request, client):
            return "anthropic-success"

    router.adapters["openai"] = FailingOpenAI()
    router.adapters["anthropic"] = SucceedingAnthropic()

    req = ChatRequest(model="gpt-3.5-turbo", messages=[ChatMessage(role="user", content="hi")])
    result = await router.route(req)
    assert result == "anthropic-success"
