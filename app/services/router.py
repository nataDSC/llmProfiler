# This is the "Brain" of the gateway.
# While the adapters handle the talking, the Router handles the strategy.
# In a production environment, this is where you save the company money and prevent downtime.

# This is a Fallback & Retry pattern.
# If OpenAI is having a "bad day" (503 Service Unavailable), the router silently switches
# the request to Anthropic or a local Llama instance before the user even notices.


from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Type, Any

from models import ChatRequest, ChatResponse
from base import BaseLLMAdapter
from openai import OpenAIAdapter
# from .anthropic_adapter import AnthropicAdapter  <-- Future implementation

logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # Registry of available adapter classes
        self._adapter_map: Dict[str, Type[BaseLLMAdapter]] = {
            "openai": OpenAIAdapter,
            # "anthropic": AnthropicAdapter,
        }
        self.adapters: Dict[str, BaseLLMAdapter] = {}
        self._setup_adapters()

    def _setup_adapters(self):
        """Initialize adapters based on provided config."""
        for provider, provider_config in self.config.get("providers", {}).items():
            if provider in self._adapter_map:
                adapter_cls = self._adapter_map[provider]
                self.adapters[provider] = adapter_cls(provider_config)

    async def route(self, request: ChatRequest) -> ChatResponse:
        """
        Routes the request with built-in resilience.
        Strategy: Priority Provider -> Fallback Provider -> Error
        """
        # Determine the primary provider (manual hint or default)
        primary_provider = request.provider_hint or self.config.get("default_provider", "openai")
        
        # Get the list of providers to try (Primary first, then others)
        providers_to_try = [primary_provider]
        if self.config.get("enable_fallback", True):
            fallbacks = [p for p in self.adapters.keys() if p != primary_provider]
            providers_to_try.extend(fallbacks)

        last_exception = None

        for provider_name in providers_to_try:
            adapter = self.adapters.get(provider_name)
            if not adapter:
                continue

            try:
                logger.info(f"Routing request to {provider_name}...")
                return await adapter.complete(request)
            
            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {str(e)}")
                last_exception = e
                # Continue to the next provider in the loop
                continue

        # If we get here, all providers failed
        logger.error("All LLM providers exhausted.")
        raise last_exception or RuntimeError("No providers available to handle request.")
