# Implementation Plan: LLM Gateway & Profiler

This plan outlines the phased approach for building a robust, async, adapter-based LLM gateway with profiling, cost tracking, and extensibility. It is based on the requirements and structure in /memories/session/plan.md.

---

# Phase Status

- **Phase 1: Project Scaffolding & Foundation** — done
- **Phase 2: Provider Adapters & Routing Logic** — done
- **Phase 3: Profiling, Metrics, and Cost Calculation** — done
- **Phase 4: Endpoint, Streaming, and Middleware Integration** — done
- **Phase 5: Caching, Security, and Deployment** — done
- **Phase 6: Advanced Caching Strategy** — done

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

## Phase 6: Advanced Caching Strategy

**Status:** Complete (April 2026)

**Goal:** Make caching smarter and more production-ready by supporting tiered TTLs, cache categories, and stale-while-revalidate for semantic and exact cache entries.

**Highlights:**

- Implemented category-based TTLs and cache category mapping in config and cache classes.
- Added tiered TTL logic for both exact and semantic/vector cache entries.
- Integrated stale-while-revalidate: stale cache hits are served and trigger async background refresh.
- Metadata (`cached_at`, `model`, etc.) and freshness checks are enforced on all cache lookups.
- Volatile/no-cache category is supported and bypasses cache as required.
- All TTLs, category mappings, and freshness windows are configurable.
- Tests cover category TTL, stale-while-revalidate, metadata/freshness, and no-cache logic.

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

---

## Phase 7: UI & Demo Experience

**Status:** Complete (April 2026)

**TODO:**

- Expanded PII redaction coverage: Added regex patterns for phone numbers, addresses, and account numbers to the PII redaction logic. Consider using a PII detection library for more robust coverage in the future.

**Goal:** Deliver a production-grade, developer-focused UI and demo experience that showcases the gateway’s unique value: traceability, policy-driven routing, PII handling, and real-time metrics.

**Highlights:**

- Streamlit-based UI for rapid local and cloud deployment (integrates with FastAPI backend).
- "Execution Trace" panel visualizes the full inference path for every request (PII check, cache hits/misses, router logic, etc.).
- Sidebar "Policy Engine" lets users select routing policies (e.g., Penny Pincher, Speed Demon, High Fidelity, Chaos Mode for failover simulation).
- Dual-view chat area: shows both "User Sent" and "Gateway Received" (PII redaction demo).
- Metrics dashboard: displays total savings, latency delta, cache efficiency (pie chart), and other key stats.
- Admin panel: includes manual cache invalidation for live demo of semantic cache dynamics.
- Docker Compose setup for local development: FastAPI, Redis, Streamlit UI.

**Steps:**

1. **User Story Expansion**
   - Add a "Traceability" story: As a backend engineer, I want to see a step-by-step execution trace for every request, so I can verify gateway logic and cache behavior.

2. **Tech Stack & Integration**
   - Use Streamlit for the UI, running on port 8501, talking to FastAPI (port 8000).
   - Prepare for AWS deployment: UI as a separate container/service.

3. **UI Features & Enterprise Architecture**
   - **Execution Trace Panel:** Waterfall view of each step (PII, cache, embedding, router, etc.) with timing and status.
   - **Sidebar Policy Engine:** Routing policy selector (Penny Pincher, Speed Demon, High Fidelity, Chaos Mode for error simulation).
   - **Chaos Mode:** UI toggle sends `X-Simulate-Error` header to trigger simulated provider failures; FastAPI middleware and router logic handle and trace simulated errors for demo and testing.
   - **Dual Chat View:** Show both original and redacted input side-by-side (demonstrates PII redaction before LLM/cache).
   - **Metrics Dashboard:** Big-number stats, latency deltas, cache efficiency pie chart.
   - **Admin Panel:** Manual cache invalidation button for demoing semantic cache refresh.
   - **PII Blocked Badge:** UI highlights when PII is detected and redacted, reinforcing compliance and security.
   - **Rate Limiting Feedback:** UI displays rate limit status (429) if triggered, with clear messaging.

4. **Infrastructure & Local-to-Cloud Bridge**
   - Project structure: `gateway/` (FastAPI), `ui/` (Streamlit), `docker-compose.yml`, `.env` for secrets.
   - Use `redis/redis-stack-server` for vector search and RedisInsight UI (port 8001) for debugging.
   - Docker Compose orchestrates all services with healthchecks and service discovery (no IPs, just service names).
   - Volumes for Redis persistence.
   - Documented local launch: `docker-compose up --build` brings up UI, API, and cache with correct networking.

5. **Backend Enhancements**
   - **Chaos Middleware:** FastAPI middleware inspects `X-Simulate-Error` and sets request state for router to simulate provider failures.
   - **Router Integration:** LLMRouter checks for simulated error and raises HTTP 500 for the targeted provider.
   - **PII Redaction:** Regex-based redaction (email, phone, credit card, etc.) in `app/core/security.py`, applied before logging, caching, or LLM call.
   - **Rate Limiting:** Redis-backed token bucket or fixed window limiter in `app/core/limiter.py`, enforced via dependency or middleware; 429 returned if exceeded.

6. **Demo Workflow**
   - Demonstrate cache hit/miss, semantic similarity, and manual cache invalidation live.
   - Use Chaos Mode to simulate provider errors and show real-time failover.
   - Show PII redaction in action and rate limiting feedback.

7. **Testing & Polish**
   - Add/expand tests for API endpoints supporting the UI (trace, metrics, cache control, chaos, rate limiting, PII redaction).
   - Document demo scenarios, UI usage, and local/cloud deployment in README.

**Status:** Complete

4. **Demo Workflow**
   - Demonstrate cache hit/miss, semantic similarity, and manual cache invalidation live.
   - Use Chaos Mode to simulate provider errors and show real-time failover.

5. **Local-to-Cloud Bridge**
   - Extend Docker Compose to include Streamlit UI alongside FastAPI and Redis for seamless local development and demo.

6. **Testing & Polish**
   - Add/expand tests for API endpoints supporting the UI (trace, metrics, cache control).
   - Document demo scenarios and UI usage in README.

**Status:** Complete
