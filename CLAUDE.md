# CLAUDE.md — LLM Gateway & Performance Profiler

## Project Context

This is an async **LLM proxy gateway** built with FastAPI. It exposes a single OpenAI-compatible endpoint (`POST /v1/chat/completions`) that routes requests to OpenAI or Anthropic, with:

- **Hybrid caching** — exact SHA-256 match + semantic cosine-similarity search via Redis + RedisVL
- **Automatic failover** — `LLMRouter` retries the next provider on network/5xx errors
- **Performance profiling** — TTFT, total latency, TPS, and USD cost per request
- **PII sanitization** — middleware redacts emails, SSNs, credit cards, phone numbers, and addresses
- **Prometheus metrics** — exposed at `/metrics` for Grafana dashboards
- **Streamlit UI** — in `ui/`, deployed on Hugging Face alongside the gateway

The full stack is containerized: `docker-compose up --build` starts the gateway (:8000), UI (:8501), Redis, and Prometheus (:9090).

---

## Commands

### Running the server (local dev)
```bash
poetry run uvicorn app.main:app --reload
```
Requires Redis running: `docker-compose up cache -d`

### Running the full stack
```bash
docker-compose up --build
```

### Running tests
```bash
poetry run pytest
```

### Running UI tests (requires backend running at localhost:8000)
```bash
cd ui && pytest test_ui_basic.py
```

### Installing dependencies
```bash
pip install poetry
poetry install
```

There is no separate linter or formatter configured in this project. Keep code consistent with the style described below.

---

## Coding Standards

### Language and runtime
- Python 3.10–3.12. Use `from __future__ import annotations` at the top of files that use forward references or `X | Y` union syntax.
- All I/O-bound operations must be `async`/`await`. Never use blocking calls (`requests`, `time.sleep`) in async contexts.

### Pydantic V2
- All request/response models use Pydantic V2 (`BaseModel`). Use `model_dump()` not `.dict()`, and `model_dump_json()` not `.json()`.
- Add `Field(...)` with a `description` only for fields that appear in public API responses (see `GatewayMetrics`).

### Provider adapters
- Every new LLM provider must subclass `BaseLLMAdapter` ([app/providers/base.py](app/providers/base.py)) and implement both `complete()` and `stream()`.
- Register the new adapter in `LLMRouter._adapter_map` ([app/services/router.py](app/services/router.py)).

### Fail-open pattern
- Cache and embedding calls must never crash a request. Wrap them in `try/except` and log the error, then continue without the feature (the existing `HybridCache` and `EmbeddingService` calls in the route handler demonstrate this).

### Imports
- Use absolute imports (`from app.services.profiler import Profiler`), never relative.
- Avoid top-level imports of heavy dependencies (e.g., `openai`, `redisvl`) — import them inside the function/method where they are first needed, as done in the existing adapters.

### Comments
- Only add a comment when the *why* is non-obvious. Do not describe what the code does.

### Configuration
- All secrets and environment-specific values come from environment variables via `Settings` ([app/core/config.py](app/core/config.py)). Never hardcode keys or URLs.
- Per-model pricing lives in `pricing.yaml`; add new models there, not in code.

---

## Instructions

**After any edit to source files under `app/` or `tests/`, run the full test suite before reporting the task complete:**

```bash
poetry run pytest
```

All tests must pass. If a test fails, diagnose and fix the root cause — do not skip tests or mark them as expected failures unless the user explicitly requests it.

For changes to `ui/`, note that UI tests require a running backend and must be run manually:

```bash
cd ui && pytest test_ui_basic.py
```
