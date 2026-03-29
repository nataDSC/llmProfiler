# Implementation Plan: LLM Gateway & Profiler

This plan outlines the phased approach for building a robust, async, adapter-based LLM gateway with profiling, cost tracking, and extensibility. It is based on the requirements and structure in /memories/session/plan.md.

---

# Phase Status

- **Phase 1: Project Scaffolding & Foundation** — done
- **Phase 2: Provider Adapters & Routing Logic** — started
- **Phase 3: Profiling, Metrics, and Cost Calculation** — not started
- **Phase 4: Endpoint, Streaming, and Middleware Integration** — not started
- **Phase 5: Caching, Security, and Deployment** — not started

---

## Phase 1: Project Scaffolding & Foundation

**Goal:** Establish a solid, testable, and extensible project structure.

**Steps:**
1. Create the Python package layout and directory structure.
2. Add __init__.py files to all packages.
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

**Steps:**
1. Scaffold Redis caching for semantic/TTL cache (defer implementation if not in scope).
2. Add PII sanitization middleware/layer.
3. Add Dockerfile and containerization assets.
4. Document environment, deployment, and operational notes in README.md.
5. Add/expand tests for caching and security.

---

## Further Considerations
- Model aliasing and pricing normalization are handled in config and pricing services.
- Streaming metrics are included in the final JSON chunk for compatibility with modern LLM gateways.
- All code is async and adapter-based for extensibility and performance.

---

This plan should be updated as requirements evolve or as new phases are added.
