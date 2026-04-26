---
title: LLM Gateway
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---

# 🚀 LLM Gateway & Performance Profiler

A high-performance, asynchronous **LLM Proxy** built with FastAPI. This gateway provides a single entry point for multiple LLM providers (OpenAI, Anthropic, Local) while offering enterprise-grade failover, hybrid (exact + semantic/vector) caching, PII sanitization, and real-time performance profiling.
<br><br>
Link to the public deployment of the application on Hugging Face: [ LLM Gateway and Performance Profiler ](https://maarseek-llm-gateway-ui.hf.space)

## 🌟 Key Features

- **Provider Agnostic:** Unified OpenAI-compatible API for switching between models without changing client-side code.
- **Intelligent Failover:** Automatically reroutes requests to a fallback provider (e.g., OpenAI → Anthropic) if the primary service experiences downtime.
- **Performance Profiling:** Tracks critical metrics including **TTFT** (Time to First Token), **Total Latency**, and **TPS** (Tokens Per Second).
- **Cost Management:** Real-time USD cost estimation based on per-provider token pricing.
- **Hybrid Caching:** Integrated Redis layer for both exact-match and semantic (vector) caching. Dramatically reduces costs and latency for repeated or similar queries. Uses RedisVL for vector search and OpenAI/local embeddings.
- **Cloud Native:** Instrumented with **Prometheus** for real-time monitoring and Grafana dashboards.
- **PII Security:** All requests and responses are sanitized for common PII (email, SSN, credit card) using built-in middleware.

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, Pydantic V2, Asyncio
- **Data Stores:** Redis (Caching), Prometheus (Metrics)
- **Providers:** OpenAI SDK, Anthropic (via Adapter Pattern)
- **Logic:** Plan-Act-Reflect reasoning loops

---

## 📈 Performance Metrics

The gateway calculates performance using standardized formulas to ensure unbiased provider comparisons:

### **Tokens Per Second (TPS)**

This metric measures the raw throughput of the model once it begins responding:
$$TPS = \frac{\text{Total Output Tokens}}{\text{Total Latency} - \text{TTFT}}$$

### **Cost Estimation**

Calculated per request based on the provider's specific pricing tier ($1M$ token standard):
$$\text{Cost}_{USD} = \left( \frac{\text{Input Tokens}}{10^6} \times \text{Price}_{in} \right) + \left( \frac{\text{Output Tokens}}{10^6} \times \text{Price}_{out} \right)$$

---

## 🚀 Quick Start

1.  **Clone and Install:**

    ```bash
    git clone https://github.com/your-username/llm-gateway.git
    pip install -r requirements.txt
    ```

2.  **Configure Environment:**
    Create a `.env` file with your API keys:

    ```env
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    REDIS_URL=redis://localhost:6379  # Required for caching
    ```

3.  **Run the Gateway:**
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```

---

## 🗄️ Caching & Redis

This gateway uses a hybrid cache:

- **Exact match:** Fast key-value lookup for identical prompts.
- **Semantic/vector match:** Uses RedisVL and OpenAI/local embeddings to find similar prompts and reuse responses.

**Redis is required** for all caching features. The default config expects Redis at `redis://localhost:6379` (see `.env`).

To run Redis locally (with Docker Compose):

```bash
docker-compose up redis
```

## 🛡️ Observability & Security

Access the Prometheus metrics endpoint at `/metrics` to monitor:

- `llm_gateway_latency_ms`: Histogram of request durations.
- `llm_gateway_cost_usd_total`: Running counter of total spend.
- `llm_gateway_requests_total`: Success/Failure counts per provider.

---

## 🎯 Why Use This?

In a production environment, calling LLM APIs directly creates **vendor lock-in** and **unpredictable costs**. This gateway acts as a "Control Plane," allowing engineering teams to optimize for speed or cost dynamically, ensure 99.99% availability through failover, and gain total visibility into AI infrastructure spend.

### Security

- All requests and responses are sanitized for common PII (email, SSN, credit card) using the built-in PII middleware.
- See `app/middleware/pii.py` for details and patterns. Extend as needed for your use case.

# 🚀 How to Launch

You can launch the entire stack (FastAPI, Redis, Prometheus) with a single command:

```bash
docker-compose up --build
```

**What happens next:**

- FastAPI starts at http://localhost:8000
- Prometheus starts at http://localhost:9090 (query TTFT and cost metrics)
- Redis starts in the background, handling all hybrid cache operations

---

## 🛠️ Setup

1. **Create a Python virtual environment:**
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies:**
   ```sh
   pip install --upgrade pip
   pip install poetry
   poetry install
   ```

## Running the Server

1. **Set environment variables:**
   - `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` (as needed)
   - Optionally: `DEFAULT_PROVIDER`, `PRICING_PATH`

2. **Start the FastAPI server:**
   ```sh
   poetry run uvicorn app.main:app --reload
   ```
   The API will be available at http://localhost:8000/v1/chat/completions

## Testing

Run all tests with:

```sh
poetry run pytest
```

## Running UI Tests

To run the automated UI tests (from the project root):

```
cd ui
pytest test_ui_basic.py
```

- Make sure the FastAPI backend is running and accessible at http://localhost:8000 before running UI tests.
- The tests will launch the Streamlit UI in the background and check both backend and UI endpoints.

## Project Structure

- `app/` - Main application code (adapters, routers, models, services)
- `tests/` - Test suite
- `pricing.yaml` - Model pricing configuration

## Test Coverage

- All critical paths are covered by tests, including:
  - Cache hit/miss logic (exact and semantic)
  - PII redaction for requests and responses
  - Provider failover and metrics
  - Cost calculation and Prometheus metrics

Run all tests with:

```sh
poetry run pytest
```

---

## Notes

- Metrics for streaming responses are included in the final JSON chunk.
