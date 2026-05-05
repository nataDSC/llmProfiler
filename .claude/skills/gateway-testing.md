---
name: gateway-testing
description: Use when writing or editing any file in tests/, when adding test coverage after a new feature is implemented, or when asked to run or debug the test suite. Covers pytest-asyncio patterns, Redis mocking, the autouse env fixture, and the coverage gaps that still need tests.
---

# Gateway Testing Skill

You are writing or maintaining tests for an async FastAPI gateway. This skill gives you the setup details, patterns, and known coverage gaps so you don't repeat mistakes that break async test execution or leave Redis connections open.

---

## Test infrastructure

### pytest configuration
`pytest.ini` sets `pythonpath = .`. All imports must be absolute from the project root. The test command is:

```bash
poetry run pytest
# or with verbosity:
poetry run pytest -v
# run a single file:
poetry run pytest tests/test_cache_and_security.py -v
```

### The autouse `.env` fixture
`tests/conftest.py` defines a session-scoped autouse fixture that loads `.env` before any test runs:

```python
@pytest.fixture(scope="session", autouse=True)
def load_env():
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"), override=True)
```

Do not add a second env-loading fixture. Do not call `load_dotenv()` inside individual test functions. If you need a new shared fixture, add it to `conftest.py`.

### Async tests
All test functions that `await` anything must be:
- Decorated with `@pytest.mark.asyncio`
- Defined with `async def`

```python
import pytest

@pytest.mark.asyncio
async def test_something_async():
    result = await some_async_function()
    assert result == expected
```

Forgetting `@pytest.mark.asyncio` will cause the test to pass vacuously without actually running the async body.

---

## Testing the FastAPI app

Use the FastAPI `TestClient` (synchronous) for endpoint tests — do not create your own HTTP session. Import the app from `app.main`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
```

For endpoints that require request headers (provider hint, chaos mode, cache control), pass them in `client.post(..., headers={...})`.

---

## Mocking external services

### OpenAI and Anthropic SDK
Use `unittest.mock.patch` or `pytest-mock` to mock SDK clients. Do not make real LLM calls in tests — they are slow, cost money, and fail in CI without API keys.

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_openai_adapter_complete():
    with patch("openai.AsyncOpenAI") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = ...  # build a fake response
        # test body
```

### Redis / HybridCache
For unit tests of cache logic, use `unittest.mock.MagicMock` or `AsyncMock` for the Redis client and index. For integration tests of the full request path (cache hit → return early), spin up a real Redis via Docker:

```bash
docker-compose up cache -d  # start Redis before running integration tests
```

Integration tests that hit real Redis should be clearly marked or placed in a separate file. If Redis is unavailable, the gateway is designed to fail-open — tests should cover this path too.

### The `ECHO_MODE` environment variable
Set `ECHO_MODE=true` in the test environment to make the OpenAI adapter echo requests without calling the real API. Useful for endpoint integration tests that don't need a real LLM response:

```python
import os
os.environ["ECHO_MODE"] = "true"
```

Or add it to a `.env.test` file and load it in a fixture.

---

## Existing test files and what they cover

| File | What it tests |
|---|---|
| `test_chat_endpoint.py` | `POST /v1/chat/completions` happy path, request/response shape |
| `test_cache_and_security.py` | Exact cache hit/miss, semantic cache hit/miss, PII redaction in request and response |
| `test_metrics.py` | Prometheus counter increments, label correctness |
| `test_pricing.py` | `calculate_request_cost()` for all providers and models in `pricing.yaml` |
| `test_router.py` | Provider failover, chaos mode simulation, provider selection from hint |

---

## Coverage gaps — open work

These areas have no tests yet. Write tests in the most appropriate existing file or create a new `test_<feature>.py`:

- [ ] **Rate limiting** (`test_rate_limiting.py`): once `app/core/limiter.py` is implemented, test: (a) request allowed under limit, (b) 429 returned when limit exceeded, (c) counter resets after window expires, (d) fail-open when Redis is unavailable.
- [ ] **Cache feedback endpoint** (`test_cache_and_security.py`): POST `/v1/cache/feedback` deletes the Redis key and subsequent requests get a cache miss.
- [ ] **Dynamic semantic threshold** (`test_cache_and_security.py`): short prompts use stricter threshold than long prompts; `X-Semantic-Threshold` header overrides both.
- [ ] **Stale-while-revalidate** (`test_cache_and_security.py`): a cached entry with age between `cache_fresh_window` and `cache_stale_window` is returned (stale hit) and triggers a background refresh.
- [ ] **Unreachable code audit** (`test_chat_endpoint.py`): verify that the `finally: p.end()` block in `chat.py` does not silently double-call `end()` on the profiler and corrupt latency metrics.
- [ ] **`X-Disable-Cache` header** (`test_cache_and_security.py`): when sent, cache lookup and store are skipped entirely.

---

## What not to do

- Do not mock the `FastAPI` app itself — use `TestClient` against the real app.
- Do not write sync tests for async functions (they pass vacuously).
- Do not add `time.sleep()` to wait for background tasks — use `asyncio.sleep()` inside an `async def` test, or refactor the test to not depend on background execution timing.
- Do not commit tests with `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` hardcoded — use the `.env` fixture.
