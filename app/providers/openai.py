from __future__ import annotations
import time
from typing import AsyncGenerator, Dict, Any

from app.providers.base import BaseLLMAdapter
from app.models.chat import ChatRequest, ChatResponse, ChatMessage

class OpenAIAdapter(BaseLLMAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]

    async def complete(self, request: ChatRequest, client: Any) -> ChatResponse:
        """Standard non-streaming completion with full metric capture."""
        start_time = time.perf_counter()
        # Use the provided client (should be an OpenAI client or httpx client wrapper)
        response = await client.chat.completions.create(
            model=request.model,
            messages=[m.dict() for m in request.messages],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False
        )

        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        metrics = self._create_metrics(
            model=request.model,
            start_time=start_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        return ChatResponse(
            id=response.id,
            created=response.created,
            model=response.model,
            choices=[choice.to_dict() for choice in response.choices],
            usage={"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
            metrics=metrics
        )

    async def stream(self, request: ChatRequest, client: Any) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming completion with TTFT (Time to First Token) tracking."""
        start_time = time.perf_counter()
        ttft = None
        response = await client.chat.completions.create(
            model=request.model,
            messages=[m.dict() for m in request.messages],
            stream=True
        )

        async for chunk in response:
            # Capture TTFT on the very first chunk that contains content
            if ttft is None and len(chunk.choices) > 0:
                ttft = (time.perf_counter() - start_time) * 1000  # ms
            
            # Yield the chunk immediately to the frontend
            yield chunk.to_dict()

        # Note: In a production version, we would log the final 
        # total latency and token count to Redis/DB here.
