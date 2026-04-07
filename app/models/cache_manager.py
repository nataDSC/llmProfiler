# Efficiency: Semantic Caching with Redis
# 
# A standard cache looks for an exact match of the string.
# A Semantic Cache is much smarter: it uses embeddings to see if the meaning
# of a new question is close enough to a previously answered one.

# Router logic:
# Check Cache: "Have we answered this exactly (or semantically) before?" -> 
#      If yes, return in 5ms for $0.
# Route Request: If no, pick the best provider (OpenAI/Anthropic).
# Capture Metrics: Record the TTFT and Cost.
# Expose Data: Prometheus serves these numbers to Grafana.

from typing import Optional

from app.models.chat import ChatRequest, ChatResponse
import redis.asyncio as redis
import hashlib
import json

class LLMCache:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        from app.core.config import settings
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.default_ttl = settings.cache_ttl_seconds
        self.category_ttls = settings.cache_category_ttls

    def _generate_key(self, request: ChatRequest) -> str:
        """Create a unique hash based on the model and message history."""
        payload = f"{request.model}:{json.dumps([m.model_dump() for m in request.messages])}"
        return f"llm_cache:{hashlib.sha256(payload.encode()).hexdigest()}"

    async def get(self, request: ChatRequest) -> Optional[ChatResponse]:
        key = self._generate_key(request)
        cached_data = await self.client.get(key)
        if cached_data:
            # Mark as a 'cache_hit' in the metrics!
            return ChatResponse.parse_raw(cached_data)
        return None

    async def set(self, request: ChatRequest, response: ChatResponse, category: str = None):
        import time
        key = self._generate_key(request)
        # Determine TTL
        ttl = self.category_ttls.get(category, self.default_ttl)
        if ttl == 0:
            return  # Do not cache volatile queries
        # Add cached_at metadata
        data = response.model_dump()
        data["cached_at"] = time.time()
        await self.client.setex(key, ttl, json.dumps(data))
