from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any
import time

from models import ChatRequest, ChatResponse, GatewayMetrics

class BaseLLMAdapter(ABC):
    """
    Abstract Base Class that all LLM providers must implement.
    Ensures a consistent interface for the Router.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider_name = config.get("name", "unknown")

    @abstractmethod
    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Execute a standard (non-streaming) completion."""
        pass

    @abstractmethod
    async def stream(self, request: ChatRequest) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a streaming completion."""
        pass

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Standardized cost calculation logic used by all adapters.
        Uses the formula:
        """
        # Logic to pull from pricing.yaml would go here
        # Cost = (input_tokens / 1,000,000 * input_rate) + (output_tokens / 1,000,000 * output_rate)
        return 0.0  # Placeholder for the actual calculation logic

    def _create_metrics(
        self, 
        model: str, 
        start_time: float, 
        input_tokens: int, 
        output_tokens: int,
        ttft: float | None = None
    ) -> GatewayMetrics:
        """Helper to generate standardized metrics for every call."""
        total_latency = (time.perf_counter() - start_time) * 1000 # Convert to ms
        
        return GatewayMetrics(
            ttft_ms=ttft,
            total_latency_ms=total_latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=self.calculate_cost(model, input_tokens, output_tokens),
            provider_used=self.provider_name,
            model_used=model
        )
