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
        self.adapters: Dict[str, BaseLLMAdapter] = {}
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

        for provider_name in queue:
            print(f"[DEBUG] Trying provider: {provider_name}")
            logger.info(f"Router: Trying provider '{provider_name}' with config: {self.config['providers'].get(provider_name, {})}")
            adapter = self.adapters.get(provider_name)
            if not adapter:
                logger.error(f"Router: No adapter found for provider '{provider_name}'")
                continue

            # Select the correct client for each provider
            if provider_name == "openai":
                client = self.openai_client
            else:
                client = self.http_client

            # --- Retry Logic for OpenAI ---
            # If it's OpenAI, we try up to 2 times (Initial + 1 Retry)
            # For others, we try once and move to fallback.
            max_attempts = 2 if provider_name == "openai" else 1

            for attempt in range(max_attempts):
                print(f"[DEBUG] Attempt {attempt + 1} for provider {provider_name}")
                try:
                    logger.info(f"Attempt {attempt + 1} for {provider_name}")
                    logger.info(f"LLMRouter: Calling adapter.complete for provider '{provider_name}' with prompt: {request.messages[-1].content if request.messages else ''}")
                    print(f"[DEBUG] Calling adapter.complete for provider '{provider_name}' with prompt: {request.messages[-1].content if request.messages else ''}")
                    result = await adapter.complete(request, client)
                    print(f"[DEBUG] Received response from provider '{provider_name}': {result}")
                    logger.info(f"LLMRouter: Received response from provider '{provider_name}': {result}")
                    logger.info(f"Router: Provider '{provider_name}' succeeded on attempt {attempt + 1}")
                    return result

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

                except Exception as e:
                    last_exception = e
                    logger.error(f"Router: Unexpected error from provider '{provider_name}': {e}")

                # If we're here, the attempt failed.
                # If we have retries left for THIS provider, wait a moment and try again.
                if attempt < max_attempts - 1:
                    wait_time = 0.5 # 500ms backoff
                    await asyncio.sleep(wait_time)
                else:
                    # No more retries for this provider, move to next in queue
                    logger.error(f"Exhausted {provider_name}. Moving to fallback...")
            print(f"[DEBUG] Finished attempts for provider: {provider_name}")

        print("[DEBUG] All providers exhausted. Raising error.")
        raise last_exception or RuntimeError("Gateway failed to find an available LLM provider.")
