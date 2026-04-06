# Implementation Plan: LLM Gateway & Profiler

This plan outlines the phased approach for building a robust, async, adapter-based LLM gateway with profiling, cost tracking, and extensibility. It is based on the requirements and structure in /memories/session/plan.md.

---

# Phase Status

- **Phase 1: Project Scaffolding & Foundation** — done
- **Phase 2: Provider Adapters & Routing Logic** — done
- **Phase 3: Profiling, Metrics, and Cost Calculation** — done
- **Phase 4: Endpoint, Streaming, and Middleware Integration** — done
- **Phase 5: Caching, Security, and Deployment** — done
- **Phase 6: Advanced Caching Strategy (Planned)** — planned

---

## Phase 1: Project Scaffolding & Foundation

**Goal:** Establish a solid, testable, and extensible project structure.

**Steps:**

1. Create the Python package layout and directory structure.
2. Add **init**.py files to all packages.
3. Add pyproject.toml with all core and dev dependencies (FastAPI, httpx, pydantic, uvicorn, tiktoken, pyyaml, redis, pytest, pytest-asyncio).
4. Add .gitignore and pytest.ini for environment and test config.
5. Create pricing.yaml with initial model pricing data.
6. Implement app/core/config.py for environment, provider, and pricing config (including model aliasing).
7. Implement app/main.py and app/api/routes/chat.py as the FastAPI entrypoint and placeholder endpoint.
8. Implement app/models/chat.py and app/models/pricing.py for request/response and pricing schemas.
9. Implement app/providers/base.py for the adapter interface.
10. Implement app/services/pricing.py for pricing lookup and normalization.
11. Add initial tests for pricing and router logic.
12. Document setup, build, and test instructions in README.md.

---

## Phase 2: Provider Adapters & Routing Logic

**Goal:** Enable real LLM calls, smart routing, and failover.

**Steps:**

1. Implement OpenAIAdapter and AnthropicAdapter in app/providers/ with async logic and model aliasing.
2. Implement app/services/router.py to select provider, handle retries, and failover (retry OpenAI once, then fallback to Anthropic).
3. Ensure all adapters and router use async HTTP and are testable/mocked.
4. Add/expand tests for routing, failover, and adapter selection.

---

## Phase 3: Profiling, Metrics, and Cost Calculation

**Goal:** Track and expose latency, TTFT, and cost for every request.

**Steps:**

1. Implement app/services/profiler.py to capture TTFT and total latency for both streaming and non-streaming flows.
2. Update adapters and router to use profiler and attach metrics to responses.
3. Update app/services/pricing.py to compute cost per request using pricing.yaml and token usage.
4. Implement app/middleware/metrics.py to emit X-Gateway-Metrics header (for non-streaming) or include metrics in the final JSON chunk (for streaming).
5. Add/expand tests for metrics, cost, and header/chunk emission.

---

## Phase 4: Endpoint, Streaming, and Middleware Integration

**Goal:** Expose a production-ready, OpenAI-compatible /v1/chat/completions endpoint.

**Steps:**

1. Implement the /v1/chat/completions endpoint in app/api/routes/chat.py, supporting both streaming and non-streaming requests.
2. Integrate provider selection via X-LLM-Provider header.
3. Ensure streaming responses include metrics in the final JSON chunk (not as trailing headers).
4. Integrate all middleware and finalize FastAPI app wiring.
5. Add/expand endpoint and integration tests.

---

## Phase 5: Caching, Security, and Deployment

**Goal:** Optimize, secure, and containerize the gateway for production.

**Status:** Complete

**Highlights:**

- Implemented hybrid (exact + semantic/vector) caching using Redis and RedisVL, with OpenAI/local embeddings.
- Added robust PII sanitization middleware for all requests and responses.
- Containerized the stack with Docker and docker-compose (FastAPI, Redis, Prometheus).
- Updated README with deployment, Redis, and security details.
- Added/expanded tests for cache hit/miss, PII redaction, and security (including cache clearing for reliable PII tests).
- All tests pass; system is production-ready and fully observable.

---

## Phase 6: Advanced Caching Strategy (Planned)

**Goal:** Make caching smarter and more production-ready by supporting tiered TTLs, cache categories, and stale-while-revalidate for semantic and exact cache entries.

**Steps:**

1. **Category-Based TTLs**
   - Define cache categories (e.g., fact-based, creative, code, volatile) and their recommended TTLs in config.
   - Allow the caller (endpoint or router) to specify a cache category or priority for each request.
   - In `HybridCache.store`, select the TTL based on the category, falling back to a default if not provided.

2. **Tiered TTL Logic**
   - For exact matches, set the TTL on the Redis key using the selected TTL.
   - For semantic/vector matches, after storing the hash/vector, manually set the expiry on the Redis hash key using the selected TTL.

3. **Stale-While-Revalidate**
   - When serving a cache hit:
     - If the entry is within the "fresh" window (e.g., <24h), return immediately.
     - If the entry is "stale" (e.g., 24–48h), return the cached value but trigger a background refresh from the LLM to update the cache for the next user.
   - Store a `cached_at` timestamp in each cache entry to support this logic.

4. **Volatile/No-Cache Handling**
   - For highly volatile queries (e.g., real-time data), allow the caller to specify "do not cache" and bypass the cache entirely.

5. **Metadata and Freshness Checks**
   - Store metadata (e.g., `cached_at`, `model`) in all cache entries.
   - On cache lookup, check the age of the entry and the user's freshness requirements before returning a hit.

6. **Configurable Defaults**
   - Make all TTLs, category mappings, and freshness windows configurable via settings.

7. **Testing**
   - Add/expand tests for:
     - Category-based TTL selection and expiry
     - Stale-while-revalidate logic (including background refresh)
     - Metadata and freshness checks
     - No-cache/volatile bypass

---

## Further Considerations

- Model aliasing and pricing normalization are handled in config and pricing services.
- Streaming metrics are included in the final JSON chunk for compatibility with modern LLM gateways.
- All code is async and adapter-based for extensibility and performance.

---

This plan should be updated as requirements evolve or as new phases are added.
