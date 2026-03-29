# This is the "Brain" of the gateway.
# While the adapters handle the talking, the Router handles the strategy.
# In a production environment, this is where you save the company money and prevent downtime.

# This is a Fallback & Retry pattern.
# If OpenAI is having a "bad day" (503 Service Unavailable), the router silently switches
# the request to Anthropic or a local Llama instance before the user even notices.

import asyncio
from asyncio.log import logger
from app.models.chat import ChatRequest, ChatResponse
from app.providers.base import BaseLLMAdapter
from app.providers.openai import OpenAIAdapter
import httpx
from typing import Dict, List, Any 
from app.providers.anthropic import AnthropicAdapter # Ensure this is uncommented

class LLMRouter:
    # ... (keep your __init__ and _setup_adapters) ...

    def __init__(self, config: Dict[str, Any], http_client: httpx.AsyncClient):
        self.config = config
        self.http_client = http_client # Shared client for connection pooling
        self._adapter_map = {
            "openai": OpenAIAdapter,
            "anthropic": AnthropicAdapter,
        }
        self.adapters: Dict[str, BaseLLMAdapter] = {}
        self._setup_adapters()

    async def route(self, request: ChatRequest) -> ChatResponse:
        """
        Policy:
        1. Try Primary Provider.
        2. If Primary is 'openai' and fails with 5xx/Timeout, retry once.
        3. If still failing, fall back to the next available provider.
        """
        primary_provider = request.provider_hint or self.config.get("default_provider", "openai")
        
        # Build the queue: [primary, fallback1, fallback2...]
        queue = [primary_provider]
        if self.config.get("enable_fallback", True):
            queue.extend([p for p in self.adapters.keys() if p != primary_provider])

        last_exception = None

        for provider_name in queue:
            adapter = self.adapters.get(provider_name)
            if not adapter:
                continue

            # --- Retry Logic for OpenAI ---
            # If it's OpenAI, we try up to 2 times (Initial + 1 Retry)
            # For others, we try once and move to fallback.
            max_attempts = 2 if provider_name == "openai" else 1
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Attempt {attempt + 1} for {provider_name}")
                    return await adapter.complete(request, self.http_client)

                except httpx.HTTPStatusError as e:
                    last_exception = e
                    # 4xx errors are User Errors (Bad Request) - DON'T retry or fall back
                    if e.response.status_code < 500:
                        logger.error(f"User Error from {provider_name}: {e}")
                        raise e

                    # 5xx errors are Provider Errors - Log and check if we should retry
                    logger.warning(f"{provider_name} Server Error ({e.response.status_code})...")

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exception = e
                    logger.warning(f"{provider_name} Connection Issue: {str(e)}...")

                # If we're here, the attempt failed.
                # If we have retries left for THIS provider, wait a moment and try again.
                if attempt < max_attempts - 1:
                    wait_time = 0.5 # 500ms backoff
                    await asyncio.sleep(wait_time)
                else:
                    # No more retries for this provider, move to next in queue
                    logger.error(f"Exhausted {provider_name}. Moving to fallback...")

        raise last_exception or RuntimeError("Gateway failed to find an available LLM provider.")
