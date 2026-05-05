---
name: gateway-backend
description: Use when working on app/providers/, app/services/router.py, app/services/pricing.py, app/middleware/, app/core/, app/api/routes/chat.py, or app/models/chat.py. Covers the core FastAPI gateway: provider adapters, routing strategy, middleware, cost calculation, and the main completion endpoint.
---

# Gateway Backend Skill

You are working on the **core FastAPI backend** of an LLM proxy gateway. This skill gives you the invariants, patterns, and open work items you need to work safely and correctly in `app/`.

---

## Architecture in one paragraph

The gateway receives OpenAI-compatible `POST /v1/chat/completions` requests. The main route handler in `app/api/routes/chat.py` orchestrates: (1) PII sanitization via middleware, (2) hybrid cache lookup, (3) embedding generation, (4) routing through `LLMRouter` to OpenAI or Anthropic, (5) cache store, (6) metrics enrichment. Every provider implements `BaseLLMAdapter`. The `LLMRouter` holds the failover strategy and is the only code that picks a provider. `Profiler` is the stopwatch. `calculate_request_cost()` is the only place that touches `pricing.yaml`.

---

## Non-negotiable invariants

### Fail-open
Cache, embedding, and rate limiting are optimization paths, not critical paths. Every call to these services must be wrapped in `try/except`. On failure: log with `logger.error()`, continue without the feature. Never let a Redis timeout or embedding API error propagate as a 500 to the user.

```python
# Correct pattern
try:
    cache = HybridCache(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"))
except Exception as e:
    logger.error(f"HybridCache unavailable, proceeding without cache: {e}")
    cache = None
```

### Pydantic V2
All models use Pydantic V2. Use:
- `model_dump()` not `.dict()`
- `model_dump_json()` not `.json()`
- `model_validate()` not `parse_obj()`
- Never `parse_raw()` — that is Pydantic V1 and will break silently on complex types

### Async discipline
All I/O is async. Never use:
- `requests` (use `httpx.AsyncClient`)
- `time.sleep()` (use `await asyncio.sleep()`)
- Synchronous Redis calls in async functions (use `await`)

### Shared HTTP client
The singleton `httpx.AsyncClient` lives in `app/core/http.py`. Adapters receive it via FastAPI `Depends(get_http_client)`. Never instantiate a new `AsyncClient` inside a request handler or adapter method — it bypasses connection pooling and opens unbounded file handles under load.

### Absolute imports only
```python
# Correct
from app.services.profiler import Profiler

# Wrong
from ..services.profiler import Profiler
```

### Deferred heavy imports
`openai`, `redisvl`, and `anthropic` are imported inside methods/functions, not at module top level. This keeps startup time low and avoids circular imports. Follow this pattern when adding new providers.

---

## Adapter pattern

Every LLM provider subclasses `BaseLLMAdapter` (`app/providers/base.py`) and must implement:
- `complete(request, client) -> ChatResponse` — non-streaming call
- `stream(request, client) -> AsyncGenerator` — streaming call
- `call(request) -> ChatResponse` — the method the router actually invokes; creates its own SDK client

To add a new provider:
1. Create `app/providers/<name>.py` subclassing `BaseLLMAdapter`
2. Register it in `LLMRouter._adapter_map` in `app/services/router.py`
3. Add default model mapping in `LLMRouter.route()` `provider_model_map`
4. Add pricing entry in `pricing.yaml`
5. Add API key handling in `Settings.providers` in `app/core/config.py`

### Cost calculation
`BaseLLMAdapter.calculate_cost()` in the base class is a **placeholder that returns `0.0`**. The real cost logic is in `app/services/pricing.py:calculate_request_cost()`. Adapters should call that function — not override the base method. The base method exists only as a stub and should eventually be removed.

---

## Routing strategy

`LLMRouter.route()` implements a fallback queue:
1. Build queue: `[primary_provider, ...all_others]`
2. For each provider: check for chaos mode simulation, call adapter, catch `TimeoutException`/`NetworkError`, move to next
3. If all fail: raise the last exception

**Chaos mode**: the `X-Simulate-Error: <provider>` request header triggers a simulated 502 for the named provider. The router checks `request.simulate_error` on the `ChatRequest` model, not `request.state`. This is set in the route handler from the HTTP header.

**Provider routing hint**: the `X-LLM-Provider` header overrides `default_provider`. The route handler reads it and sets `request.provider_hint`.

---

## Middleware ordering

In `app/main.py`, middleware is registered in this order:
1. `PIISanitizerMiddleware` — runs first on requests, last on responses
2. `metrics_middleware` — runs after PII on requests

**This order is load-bearing.** If reversed, Prometheus counters will include unredacted PII in label values and the cache will store unredacted content. Do not change the order.

---

## Header contracts (public surface)

| Header | Direction | Purpose |
|---|---|---|
| `X-LLM-Provider` | Request | Force a specific provider |
| `X-Simulate-Error` | Request | Chaos mode: simulate named provider failure |
| `X-Disable-Cache` | Request | Bypass cache entirely (`"true"` to disable) |
| `X-Semantic-Threshold` | Request | Override cosine distance threshold (float) |
| `X-Gateway-Metrics` | Response | Full `GatewayMetrics` JSON for observability |

New features should use new `X-*` headers, not query parameters.

---

## Configuration

All secrets and environment-specific values come from `Settings` in `app/core/config.py`, which reads environment variables. Never hardcode API keys, URLs, or paths. Per-model pricing lives in `pricing.yaml` — add new models there, not in code.

Key settings:
- `settings.default_provider` — fallback if no `X-LLM-Provider` header
- `settings.model_aliases` — maps UI-friendly names to provider model IDs
- `settings.cache_ttl_seconds`, `settings.cache_category_ttls` — TTL strategy
- `settings.cache_fresh_window`, `settings.cache_stale_window` — stale-while-revalidate

---

## Open work items owned by this domain

- [ ] **Implement rate limiting**: create `app/core/limiter.py` with a Redis-backed fixed-window `RateLimiter`, wire it into `app/api/routes/chat.py` as a FastAPI dependency. Return 429 on limit exceeded.
- [ ] **Remove debug prints**: `router.py:45` and `router.py:92` have `print("[DEBUG] ...")` statements — replace with `logger.debug()` or remove.
- [ ] **Remove unreachable code**: `chat.py:248-253` is dead code after the `return llm_response` on line 246. Delete it.
- [ ] **Resolve `BaseLLMAdapter.calculate_cost()`**: it returns `0.0`. Either delegate to `calculate_request_cost()` from `pricing.py` or remove it to avoid confusion.

---

## Verification

After any change to `app/` or `tests/`, run:

```bash
poetry run pytest
```

All tests must pass before the task is considered complete.
