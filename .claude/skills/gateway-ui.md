---
name: gateway-ui
description: Use when working on any file inside ui/ — ui/main.py, ui/Dockerfile, ui/requirements.txt, or ui/test_ui_basic.py. The Streamlit UI is a separate container with no Python import relationship to app/. It communicates with the gateway exclusively over HTTP.
---

# Gateway UI Skill

You are working on the **Streamlit frontend** of an LLM gateway. This app lives in `ui/` and runs in its own Docker container. It has **no `import` relationship with `app/`** — it is a pure HTTP client of the gateway. You do not need to understand FastAPI internals to work here, but you do need to know the gateway's external API contract precisely.

---

## Gateway API contract

The UI sends requests to the gateway at `GATEWAY_URL` (env var, default: `http://localhost:8000` in local dev, `http://gateway:8000` inside Docker Compose).

### Request

```
POST {GATEWAY_URL}/v1/chat/completions
Content-Type: application/json

{
  "model": "gpt-3.5-turbo",          // or "claude-3-haiku-20240307" etc.
  "messages": [{"role": "user", "content": "..."}],
  "temperature": 0.7
}
```

Control headers the UI can attach:

| Header | Effect |
|---|---|
| `X-LLM-Provider: openai` | Force OpenAI |
| `X-LLM-Provider: anthropic` | Force Anthropic |
| `X-Simulate-Error: openai` | Chaos mode — simulate OpenAI failure, trigger fallback |
| `X-Simulate-Error: anthropic` | Chaos mode — simulate Anthropic failure |
| `X-Disable-Cache: true` | Bypass cache entirely |
| `X-Semantic-Threshold: 0.08` | Override cosine distance threshold |

### Response shape

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1746000000,
  "model": "gpt-3.5-turbo",
  "choices": [
    {
      "index": 0,
      "finish_reason": "stop",
      "message": {
        "role": "assistant",
        "content": "...",              // PII-redacted version
        "original_content": "..."     // unredacted (for side-by-side demo)
      }
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 45
  },
  "metrics": {
    "ttft_ms": 312.4,
    "total_latency_ms": 890.1,
    "tokens_per_second": 52.3,
    "input_tokens": 12,
    "output_tokens": 45,
    "estimated_cost_usd": 0.000031,
    "provider_used": "openai",
    "model_used": "gpt-3.5-turbo",
    "savings": 0.0,
    "latency_delta": 0.0,
    "cache_efficiency": 0
  },
  "trace": "Checked cache for exact match | Getting embedding | Routing to LLM provider | openai",
  "redacted_prompt": "..."
}
```

On a **cache hit**, `metrics.provider_used` will be `"cache_exact"` or `"cache_semantic"`, and `metrics.savings` / `metrics.latency_delta` / `metrics.cache_efficiency` will be non-zero.

### Other endpoints the UI uses

```
POST /v1/chat/admin/invalidate_cache    # clears all Redis cache entries
GET  /health                            # {"status": "ok"}
GET  /metrics                           # Prometheus text format (not used by UI directly)
```

---

## UI feature map

### Sidebar — Policy Engine
Maps routing policy selections to headers sent with each request:

| Policy | Headers to send |
|---|---|
| Penny Pincher | `X-LLM-Provider: openai` + use cheapest model in payload |
| Speed Demon | `X-LLM-Provider: openai` (historically lower latency) |
| High Fidelity | `X-LLM-Provider: anthropic` + `claude-3-haiku-20240307` |
| Chaos Mode | `X-Simulate-Error: openai` |

### Dual chat view
Show two columns: "User Sent" (`redacted_prompt` field) and "Gateway Received" (`choices[0].message.content`). This is the PII demo — the difference between the two shows what was redacted.

### Execution trace panel
`response.trace` is a pipe-delimited string: `"step 1 | step 2 | step 3"`. Split on `" | "` and render each step as a numbered list or waterfall. Steps may include cache hit/miss, semantic distance values, and the final provider used.

### Metrics dashboard
Extract from `response.metrics`:
- TTFT: `metrics.ttft_ms` ms
- Total latency: `metrics.total_latency_ms` ms
- TPS: `metrics.tokens_per_second`
- Estimated cost: `metrics.estimated_cost_usd` USD
- Cache efficiency: `metrics.cache_efficiency` % (100 = full cache hit, 0 = LLM call)
- Savings: `metrics.savings` USD (cost avoided by cache)

### Admin panel
- Cache invalidation button → `POST /v1/chat/admin/invalidate_cache`
- Semantic threshold slider → sends value as `X-Semantic-Threshold` float header

---

## Running the UI locally

```bash
# Start the backend first (required)
docker-compose up cache gateway -d

# Run Streamlit directly
cd ui
pip install -r requirements.txt
streamlit run main.py
# UI at http://localhost:8501
```

Or run the full stack including the UI container:
```bash
docker-compose up --build
# UI at http://localhost:8501
```

Inside Docker Compose, the UI reaches the gateway via `http://gateway:8000` (internal Docker DNS). Locally, it uses `http://localhost:8000`. The `GATEWAY_URL` env var controls this.

---

## UI tests

`ui/test_ui_basic.py` contains **integration smoke tests** — they require a running backend at `localhost:8000`. They are not unit tests and should not be run in CI without the backend. Run them manually:

```bash
# ensure backend is running first
cd ui
pytest test_ui_basic.py -v
```

---

## Streamlit-specific notes

- `STREAMLIT_SERVER_PORT=8501` and `STREAMLIT_SERVER_ADDRESS=0.0.0.0` must be set in the Dockerfile for the container to be reachable.
- Streamlit re-runs the entire script on every user interaction. Use `st.session_state` to persist data between runs (conversation history, cumulative metrics, etc.).
- Do not use blocking `requests.get()` calls from within Streamlit widget callbacks — use them in the main script body where Streamlit controls the execution flow.

---

## Open work items owned by this domain

- [ ] **Rate limiting error state**: once `app/core/limiter.py` is implemented and the backend returns 429, display a clear "Too many requests — slow down" message rather than a generic error.
- [ ] **HF Spaces regression check**: verify that the cache invalidation button, semantic threshold slider, and Chaos Mode all work correctly in the cloud deployment at the public HF Space URL, not just locally.
