# 🚀 LLM Gateway & Performance Profiler

A high-performance, asynchronous **LLM Proxy** built with FastAPI. This gateway provides a single entry point for multiple LLM providers (OpenAI, Anthropic, Local) while offering enterprise-grade failover, semantic caching, and real-time performance profiling.

## 🌟 Key Features

- **Provider Agnostic:** Unified OpenAI-compatible API for switching between models without changing client-side code.
- **Intelligent Failover:** Automatically reroutes requests to a fallback provider (e.g., OpenAI → Anthropic) if the primary service experiences downtime.
- **Performance Profiling:** Tracks critical metrics including **TTFT** (Time to First Token), **Total Latency**, and **TPS** (Tokens Per Second).
- **Cost Management:** Real-time USD cost estimation based on per-provider token pricing.
- **Semantic Caching:** Integrated Redis layer to cache frequent prompts, reducing costs and latency to near-zero for repetitive queries.
- **Cloud Native:** Instrumented with **Prometheus** for real-time monitoring and Grafana dashboards.

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
    REDIS_URL=redis://localhost:6379
    ```

3.  **Run the Gateway:**
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```

---

## 🛡️ Observability

Access the Prometheus metrics endpoint at `/metrics` to monitor:

- `llm_gateway_latency_ms`: Histogram of request durations.
- `llm_gateway_cost_usd_total`: Running counter of total spend.
- `llm_gateway_requests_total`: Success/Failure counts per provider.

---

## 🎯 Why Use This?

In a production environment, calling LLM APIs directly creates **vendor lock-in** and **unpredictable costs**. This gateway acts as a "Control Plane," allowing engineering teams to optimize for speed or cost dynamically, ensure 99.99% availability through failover, and gain total visibility into AI infrastructure spend.

# 🚀 How to Launch

You can launch the entire stack with a single command:

```bash
docker-compose up --build
```

**What happens next:**

- FastAPI starts at http://localhost:8000.
- Prometheus starts at http://localhost:9090 (One can query TTFT and Cost metrics here).
- Redis starts silently in the background, handling semantic cache.
