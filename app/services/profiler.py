import time
from typing import Optional

from app.models.chat import GatewayMetrics

class Profiler:
    def __init__(self):
        self.start_time = None
        self.ttft = None
        self.end_time = None

    def start(self):
        self.start_time = time.perf_counter() # Changed to perf_counter for higher precision

    def first_token(self):
        if self.ttft is None:
           self.ttft = time.perf_counter() - self.start_time

    def end(self):
        self.end_time = time.perf_counter()

    @property
    def latency(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    @property
    def ttft_value(self) -> Optional[float]:
        return self.ttft

    def get_metrics(self, provider: str, model: str, input_tokens: int, output_tokens: int, cost: float) -> GatewayMetrics:
        """Converts stopwatch state into our standard Pydantic model."""
        latency_ms = (self.end_time - self.start_time) * 1000
        tps = (output_tokens / (latency_ms / 1000)) if latency_ms > 0 else 0

        return GatewayMetrics(
            ttft_ms=self.ttft * 1000 if self.ttft else None,
            total_latency_ms=latency_ms,
            tokens_per_second=tps,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            provider_used=provider,
            model_used=model
        )
