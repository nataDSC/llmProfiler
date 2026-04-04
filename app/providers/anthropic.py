
from app.providers.base import BaseLLMAdapter
from app.models.chat import ChatRequest, ChatResponse
from app.core.config import settings
from app.services.profiler import Profiler
from app.services.pricing import calculate_request_cost
import time
import httpx

class AnthropicAdapter(BaseLLMAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = "https://api.anthropic.com/v1/messages"
        # Anthropic-specific headers
        self.default_headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }


    async def complete(self, request: ChatRequest, client: httpx.AsyncClient) -> ChatResponse:
        profiler = Profiler()
        profiler.start()
        # 1. Extract 'system' message from the array (Anthropic requirement)
        system_msg = next((m.content for m in request.messages if m.role == "system"), None)
        messages = [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"]

        payload = {
            "model": settings.model_aliases.get(request.model, request.model),
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        resp = await client.post(self.base_url, json=payload, headers=self.default_headers, timeout=60)
        profiler.end()
        resp.raise_for_status()
        data = resp.json()

        input_tokens = data["usage"]["input_tokens"]
        output_tokens = data["usage"]["output_tokens"]
        cost = calculate_request_cost("anthropic", payload["model"], input_tokens, output_tokens)

        choices = [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": data["content"][0]["text"]
            },
            "finish_reason": data.get("stop_reason")
        }]

        metrics = profiler.get_metrics(
            provider="anthropic",
            model=payload["model"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost
        )

        return ChatResponse(
            id=data.get("id", "anthropic-unknown"),
            object="chat.completion",
            created=int(time.time()),
            model=payload["model"],
            choices=choices,
            usage={"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
            metrics=metrics
        )

        return ChatResponse(
            id=data["id"],
            created=int(time.time()),
            model=payload["model"],
            choices=choices,
            usage={"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
            metrics=metrics
        )

    async def stream(self, request: ChatRequest, client: httpx.AsyncClient):
        """Streaming implementation would go here following the same logic."""
        raise NotImplementedError("Anthropic streaming requires SSE event mapping.")
