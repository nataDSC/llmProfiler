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
    def __init__(self, config: Dict[str, Any], http_client: httpx.AsyncClient):
        self.config = config
        self.http_client = http_client # Shared client for connection pooling
        self._adapter_map = {
            "openai": OpenAIAdapter,
            "anthropic": AnthropicAdapter,
        }
        self.adapters = {}
        self.openai_client = None
        self._setup_adapters()

    def _setup_adapters(self):
        """Initialize adapters based on config and _adapter_map."""
        for provider, provider_config in self.config.get("providers", {}).items():
            if provider == "openai":
                try:
                    import openai
                    self.openai_client = openai.AsyncOpenAI(api_key=provider_config["api_key"])
                except ImportError:
                    self.openai_client = None
            if provider in self._adapter_map:
                self.adapters[provider] = self._adapter_map[provider](provider_config)

    async def route(self, request: ChatRequest) -> ChatResponse:
        import httpx  # Ensure httpx is always available in this scope
        print("[DEBUG] Entered LLMRouter.route() with request:", request)
        """
        Policy:
        1. Try Primary Provider.
        2. If Primary is 'openai' and fails with 5xx/Timeout, retry once.
        3. If still failing, fall back to the next available provider.
        """
        primary_provider = request.provider_hint or self.config.get("default_provider", "openai")
        logger.info(f"Router: Received request with provider hint: {request.provider_hint}. Primary provider set to: {primary_provider}")
        # Build the queue: [primary, fallback1, fallback2...]
        queue = [primary_provider]
        if self.config.get("enable_fallback", True):
            queue.extend([p for p in self.adapters.keys() if p != primary_provider])

        last_exception = None
        provider_model_map = {
            "openai": "gpt-3.5-turbo",
            "anthropic": "claude-3-haiku-20240307",
        }

        for provider_name in queue:
            # --- Model mapping for fallback ---
            mapped_model = provider_model_map.get(provider_name)
            original_model = request.model
            if mapped_model and original_model != mapped_model:
                logger.info(f"Router: Mapping model '{original_model}' to '{mapped_model}' for provider '{provider_name}' fallback.")
                request.model = mapped_model
            # --- Chaos Mode: Simulate Failure if requested ---
            if getattr(request, "simulate_error", None) and request.simulate_error == provider_name:
                logger.warning(f"[CHAOS MODE] Simulating failure for provider '{provider_name}' as requested.")
                # Simulate a 502 Bad Gateway error, but continue to next provider (do not raise immediately)
                last_exception = httpx.HTTPStatusError(f"Simulated failure for {provider_name}", request=None, response=type('obj', (object,), {'status_code': 502})())
                logger.error(f"Exhausted {provider_name} due to Chaos Mode. Moving to fallback...")
                continue
            # Actually call the provider adapter
            try:
                response = await self.adapters[provider_name].call(request)
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exception = e
                logger.warning(f"{provider_name} Connection Issue: {str(e)}...")
            except Exception as e:
                last_exception = e
                logger.error(f"Router: Unexpected error from provider '{provider_name}': {e}")
            # If we're here, the attempt failed. Move to next provider.
        # If all providers fail
        print("[DEBUG] All providers exhausted. Raising error.")
        raise last_exception or RuntimeError("Gateway failed to find an available LLM provider.")
