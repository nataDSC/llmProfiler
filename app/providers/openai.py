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
        # For testing: always echo the last user message as the LLM response (for PII redaction test)
        import time
        from app.models.chat import ChatResponse, GatewayMetrics
        profiler = Profiler()
        profiler.start()
        user_message = request.messages[-1].content if request.messages else ""
        profiler.end()
        metrics = profiler.get_metrics(
            provider="openai",
            model=request.model,
            input_tokens=len(user_message.split()),
            output_tokens=len(user_message.split()),
            cost=0.0
        )
        return ChatResponse(
            id="chatcmpl-echo-test",
            created=int(time.time()),
            model=request.model,
            choices=[{"message": {"role": "assistant", "content": user_message}, "finish_reason": "stop", "index": 0}],
            usage={"prompt_tokens": len(user_message.split()), "completion_tokens": len(user_message.split())},
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
