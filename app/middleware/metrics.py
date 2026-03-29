# Observability: Prometheus Metrics Middleware
# We need to capture the GatewayMetrics from every request and aggregate them.
# This allows us to hook up a Grafana dashboard to see "Total Spend" and 
# "Average TTFT" in real-time.

from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Request, Response

# Define the metrics we want to track
LLM_REQUEST_COUNT = Counter(
    "llm_gateway_requests_total", 
    "Total requests handled by the gateway", 
    ["provider", "model", "status"]
)
LLM_LATENCY = Histogram(
    "llm_gateway_latency_ms", 
    "End-to-end latency in milliseconds", 
    ["provider", "model"]
)
LLM_COST_TOTAL = Counter(
    "llm_gateway_cost_usd_total", 
    "Total estimated cost in USD", 
    ["provider", "model"]
)
LLM_TTFT = Histogram(
    "llm_gateway_ttft_ms", 
    "Time to First Token in milliseconds", 
    ["provider", "model"]
)

async def metrics_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # After the request, if we have metrics in the response state:
    if hasattr(request.state, "metrics"):
        m = request.state.metrics
        labels = {"provider": m.provider_used, "model": m.model_used}
        
        LLM_REQUEST_COUNT.labels(**labels, status="success").inc()
        LLM_LATENCY.labels(**labels).observe(m.total_latency_ms)
        LLM_COST_TOTAL.labels(**labels).inc(m.estimated_cost_usd)
        if m.ttft_ms:
            LLM_TTFT.labels(**labels).observe(m.ttft_ms)
            
    return response
