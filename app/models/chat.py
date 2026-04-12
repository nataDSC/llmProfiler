
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class GatewayMetrics(BaseModel):
    # UI stats
    savings: float = 0.0
    latency_delta: float = 0.0
    cache_efficiency: int = 0
    """Real-time performance metrics for the LLM call."""
    ttft_ms: Optional[float] = Field(None, description="Time to First Token in milliseconds")
    total_latency_ms: float = Field(..., description="End-to-end request duration")
    tokens_per_second: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    provider_used: str
    model_used: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    """OpenAI-compatible request schema."""
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    provider_hint: Optional[str] = None  # Custom field for routing
    simulate_error: Optional[str] = None  # For chaos/failover simulation

class ChatResponse(BaseModel):
    """Enriched response including gateway telemetry."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]
    metrics: GatewayMetrics  # The "Secret Sauce" of your project
    trace: Optional[str] = None  # Optional trace/debug info
    redacted_prompt: Optional[str] = None  # Redacted user prompt for UI display
