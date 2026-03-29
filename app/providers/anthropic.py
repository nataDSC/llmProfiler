from app.providers.base import BaseLLMAdapter
from app.models.chat import ChatRequest, ChatResponse
from app.core.config import settings
import httpx
import time

class AnthropicAdapter(BaseLLMAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = "https://api.anthropic.com/v1/messages"

    async def complete(self, request: ChatRequest) -> ChatResponse:
        # Map user-facing model to Anthropic model
        model = settings.model_aliases.get(request.model, request.model)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            start = time.monotonic()
            resp = await client.post(self.base_url, json=payload, headers=headers, timeout=60)
            latency = time.monotonic() - start
            resp.raise_for_status()
            data = resp.json()
            # Standardize response
            return ChatResponse(
                id=data.get("id", "anthropic-unknown"),
                object="chat.completion",
                created=int(time.time()),
                model=model,
                choices=data.get("choices", []),
                usage=data.get("usage"),
                metrics={"latency": latency, "provider": "anthropic"}
            )

    async def stream_complete(self, request: ChatRequest):
        # Not implemented: streaming for Anthropic
        raise NotImplementedError("Anthropic streaming not implemented yet.")
