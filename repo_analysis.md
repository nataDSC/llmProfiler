# LLM Gateway & Performance Profiler — Repo Analysis

## Overview

An async, production-style **LLM proxy gateway** built with FastAPI. It presents a unified OpenAI-compatible API that routes requests to multiple LLM backends (OpenAI, Anthropic), tracks detailed performance metrics, applies hybrid caching, and sanitizes PII. A separate Streamlit UI lives in `ui/` and is deployed alongside the gateway.

**Public deployment:** https://maarseek-llm-gateway-ui.hf.space

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.10–3.12 |
| Web framework | FastAPI + Uvicorn (async) |
| Data validation | Pydantic V2 |
| HTTP client | httpx (HTTP/2 enabled, shared connection pool) |
| Caching | Redis + RedisVL (hybrid exact + semantic/vector) |
| Embeddings | OpenAI embeddings API (1536-dim vectors) |
| Metrics | Prometheus (`prometheus_client`) |
| LLM providers | OpenAI SDK, Anthropic (via custom HTTP adapter) |
| UI | Streamlit |
| Packaging | Poetry (`pyproject.toml`) + `requirements.txt` |
| Testing | pytest + pytest-asyncio |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
llmProfiler/
├── app/
│   ├── main.py                  # FastAPI app factory, middleware registration
│   ├── api/routes/chat.py       # POST /v1/chat/completions — main request handler
│   ├── core/
│   │   ├── config.py            # Settings (env vars, pricing, cache windows, model aliases)
│   │   └── http.py              # Shared httpx async client (connection pooling)
│   ├── middleware/
│   │   ├── pii.py               # PII sanitization (email, SSN, CC, phone, address)
│   │   └── metrics.py           # Prometheus metrics middleware
│   ├── models/
│   │   ├── chat.py              # ChatRequest, ChatResponse, GatewayMetrics Pydantic models
│   │   ├── cache_manager.py     # Cache model utilities
│   │   └── pricing.py           # Pricing model
│   ├── providers/
│   │   ├── base.py              # BaseLLMAdapter ABC
│   │   ├── openai.py            # OpenAI adapter
│   │   └── anthropic.py         # Anthropic adapter
│   └── services/
│       ├── router.py            # LLMRouter — failover/retry strategy
│       ├── profiler.py          # Profiler — TTFT/latency/TPS stopwatch
│       ├── cache.py             # HybridCache — exact + semantic Redis caching
│       ├── embedding.py         # EmbeddingService — OpenAI vector generation
│       └── pricing.py           # Cost calculation from pricing.yaml
├── tests/                       # pytest test suite (5 test files)
├── ui/
│   ├── main.py                  # Streamlit UI
│   ├── test_ui_basic.py         # UI smoke tests
│   └── Dockerfile               # UI container
├── pricing.yaml                 # Per-model token pricing config
├── prometheus.yml               # Prometheus scrape config
├── docker-compose.yml           # Full stack: gateway + Redis + UI + Prometheus
├── pyproject.toml               # Poetry dependencies
├── requirements.txt             # pip-installable dependencies
└── pytest.ini                   # Sets pythonpath = .
```

---

## Key Architecture Decisions

### Request Flow (`app/api/routes/chat.py`)
1. **PII sanitization** runs on every request/response via `PIISanitizerMiddleware`
2. **Exact cache check** — SHA-256 hash lookup in Redis, with stale-while-revalidate windows (fresh: 24h, stale: 48h)
3. **Semantic cache check** — cosine similarity via HNSW vector index in Redis (threshold: 0.12 default, tunable via `X-Semantic-Threshold` header)
4. **LLM routing** — `LLMRouter` tries the primary provider, falls back automatically on network/5xx errors; chaos mode via `X-Simulate-Error` header
5. **Cache store** — new responses stored in both exact and semantic indexes
6. **Metrics enrichment** — `Profiler` measures TTFT, total latency, TPS; cost calculated from `pricing.yaml`

### Provider Adapter Pattern
All providers implement `BaseLLMAdapter` (ABC) with `complete()` and `stream()` methods. The router is decoupled from provider specifics.

### Prometheus Metrics (exposed at `/metrics`)
- `llm_gateway_latency_ms` — request duration histogram
- `llm_gateway_cost_usd_total` — running cost counter
- `llm_gateway_requests_total` — success/failure counts per provider

### Custom Headers
| Header | Purpose |
|---|---|
| `X-LLM-Provider` | Force a specific provider |
| `X-Simulate-Error` | Trigger chaos/failover simulation |
| `X-Disable-Cache` | Bypass cache entirely |
| `X-Semantic-Threshold` | Override cosine similarity threshold |
| `X-Gateway-Metrics` | Response header containing full metrics JSON |

---

## How to Run the Project

### Option 1 — Full Stack (Docker Compose, recommended)
```bash
cp env.example .env   # fill in OPENAI_API_KEY and/or ANTHROPIC_API_KEY
docker-compose up --build
```
- **API gateway:** http://localhost:8000
- **Streamlit UI:** http://localhost:8501
- **Prometheus:** http://localhost:9090

### Option 2 — Local Development
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install poetry
poetry install

# Start Redis (required for caching)
docker-compose up cache -d

# Set env vars
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Start the gateway
poetry run uvicorn app.main:app --reload
```
API available at http://localhost:8000/v1/chat/completions

### Key Endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/v1/chat/completions` | Main chat endpoint (OpenAI-compatible) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
| POST | `/v1/chat/admin/invalidate_cache` | Flush all cache entries |

---

## How to Run Tests

### Backend tests (from repo root)
```bash
poetry run pytest
# or
pytest
```

Test files in `tests/`:
- `test_chat_endpoint.py` — main completion endpoint
- `test_cache_and_security.py` — hybrid cache hit/miss and PII redaction
- `test_metrics.py` — Prometheus metrics
- `test_pricing.py` — cost calculation
- `test_router.py` — failover behavior

`conftest.py` auto-loads `.env` before all tests.

### UI tests (requires running backend)
```bash
cd ui
pytest test_ui_basic.py
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes (if using OpenAI) | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes (if using Anthropic) | — | Anthropic API key |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection string |
| `DEFAULT_PROVIDER` | No | `openai` | Primary LLM provider |
| `PRICING_PATH` | No | `pricing.yaml` | Path to pricing config |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `ECHO_MODE` | No | — | Test mode: echoes requests without calling LLMs |

---

## Test Coverage Areas
- Cache hit/miss (exact and semantic)
- PII redaction for requests and responses
- Provider failover and metrics emission
- Cost calculation via `pricing.yaml`
- Prometheus metric correctness
