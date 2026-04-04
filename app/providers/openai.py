from __future__ import annotations
import time
from typing import AsyncGenerator, Dict, Any


from app.providers.base import BaseLLMAdapter
from app.models.chat import ChatRequest, ChatResponse, ChatMessage
from app.services.profiler import Profiler
from app.services.pricing import calculate_request_cost

class OpenAIAdapter(BaseLLMAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]

    async def complete(self, request: ChatRequest, client: Any) -> ChatResponse:
        import logging
        logger = logging.getLogger(__name__)
        profiler = Profiler()
        profiler.start()
        logger.info(f"OpenAIAdapter: Using API key: {self.api_key[:6]}... (masked)")
        try:
            response = await client.chat.completions.create(
                model=request.model,
                messages=[m.model_dump() for m in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False
            )
        except Exception as e:
            logger.error(f"OpenAIAdapter: Exception during completion: {e}")
            raise
        profiler.end()

        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        cost = calculate_request_cost("openai", request.model, input_tokens, output_tokens)
        metrics = profiler.get_metrics(
            provider="openai",
            model=request.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost
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
            messages=[m.model_dump() for m in request.messages],
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
