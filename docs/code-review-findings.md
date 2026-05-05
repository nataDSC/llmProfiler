# Code Review Findings
*Review date: 2026-05-04*

---

## Security

### [CRITICAL] API key logged to stdout
**File:** `app/providers/anthropic.py:50`

```python
print(f"[DEBUG] Anthropic headers: {self.default_headers}")
```

`self.default_headers` contains `"x-api-key": self.api_key`. The full Anthropic API key is printed to stdout on every request. Line 33 correctly masks it with `[:6]...` — line 50 does not.

---

## Correctness Bugs

### [HIGH] PII middleware doesn't redact nested request body content
**File:** `app/middleware/pii.py:51-53`

```python
for k, v in data.items():
    if isinstance(v, str):
        data[k] = redact_pii(v)
```

User content lives at `data["messages"][n]["content"]` — two levels deep. This shallow loop misses it entirely, meaning PII-containing prompts are cached and forwarded to the LLM unredacted. The response path (line 77) correctly uses `redact_all_strings(data)`. Fix: replace the shallow loop with `data = redact_all_strings(data)`.

---

### [HIGH] Synchronous Redis calls block the event loop
**Files:** `app/services/cache.py:12-16, 54, 151, 166, 174`

`self.client.get()`, `self.client.set()`, `self.client.scan_iter()`, `self.client.delete()`, `self.client.expire()` are blocking sync calls inside `async def` methods. `self.client` is the synchronous Redis client from RedisVL (`self.index.client`). Under any load these stall the event loop while waiting on the network. Needs `redis.asyncio.Redis` or equivalent.

---

### [HIGH] `cache.check()` called twice — Tier 1 exact match runs twice per miss
**File:** `app/api/routes/chat.py:88, 131`

- Line 88: `cache.check(prompt)` — runs Tier 1 exact match
- Line 131: `cache.check(prompt, vector=vector, ...)` — runs Tier 1 exact match **again**, then Tier 2

`cache.check()` always starts with the exact match check regardless of whether `vector` is provided. Every Tier 1 miss pays for the exact lookup twice. Fix: split into `check_exact()` and `check_semantic()`, or restructure the caller to call `check()` once with the vector.

---

### [MEDIUM] Anthropic adapter creates a new `httpx.AsyncClient` per request
**File:** `app/providers/anthropic.py:14`

```python
async with httpx.AsyncClient() as client:
    return await self.complete(request, client)
```

CLAUDE.md explicitly prohibits this. The shared client from `app/core/http.py` is passed into the router but the Anthropic adapter ignores it and opens a fresh connection on every call. Under load this exhausts file descriptors.

---

### [MEDIUM] `Profiler.get_metrics()` crashes if `end()` was never called
**File:** `app/services/profiler.py:34`

```python
latency_ms = (self.end_time - self.start_time) * 1000
```

If `self.end_time` is `None`, this raises `TypeError`. No null guard exists.

---

### [MEDIUM] Test router stubs don't implement `call()`
**File:** `tests/test_router.py:25-32`

The router calls `self.adapters[provider_name].call(request)` (router.py:81), but both test stubs only implement `complete()`. The broad `except Exception` in the router catches the resulting `AttributeError` and treats it as a transient provider failure, causing the test to error rather than assert `result == "anthropic-success"`.

---

### [MEDIUM] Router mutates the shared `ChatRequest` object
**File:** `app/services/router.py:71`

```python
request.model = mapped_model
```

Permanently modifies the Pydantic object passed in from `chat.py`. After `route()` returns, `request.model` reflects the last-tried mapped model, not the user's original value. Fix: `request = request.model_copy(update={"model": mapped_model})`.

---

### [LOW] `cache.store()` silently drops vector store failures
**File:** `app/services/cache.py:176-177`

```python
except Exception as e2:
    pass
```

The fallback on a failed `index.load()` also fails silently — no log, no metric, no trace. Should at minimum `logger.error(...)`.

---

### [LOW] Startup crash if `pricing.yaml` is missing
**File:** `app/core/config.py:41`

`Settings()` is instantiated at module import time (line 44). If `pricing.yaml` doesn't exist, `FileNotFoundError` propagates during import with no useful error message.

---

## Design Problems

### Wrong logger namespace throughout
**Files:** `app/api/routes/chat.py:5`, `app/services/router.py:10`

```python
from asyncio.log import logger
```

Imports asyncio's internal logger. Log messages appear under `"asyncio"` and may be suppressed by asyncio-level log config. Should be `logger = logging.getLogger(__name__)`.

---

### `HybridCache` and `EmbeddingService` instantiated on every request
**File:** `app/api/routes/chat.py:67, 70`

Both create Redis connections / OpenAI SDK clients per-request. These should be singletons initialized at startup via FastAPI lifespan or `Depends()`.

---

### Router's broad `except Exception` hides programming bugs
**File:** `app/services/router.py:86`

```python
except Exception as e:
    last_exception = e
    logger.error(...)
```

`AttributeError`, `TypeError`, and other programming errors are treated as transient provider failures and cause silent fallover. Only `TimeoutException` and `NetworkError` should trigger fallover; everything else should propagate.

---

### `redact_all_strings` defined twice
**Files:** `app/middleware/pii.py:30` (module level) and `app/middleware/pii.py:66` (inside `dispatch()`)

Identical implementations. If one is updated the other isn't, request and response bodies get different redaction behavior. `dispatch()` should call the module-level function.

---

### `REDIS_URL` not in `Settings`
**File:** `app/core/config.py`

`REDIS_URL` is accessed via `os.getenv(...)` directly in two places in `chat.py` (lines 23 and 67). All config should route through `Settings` for consistency and testability.

---

### `claude-3-haiku-20240307` missing from `pricing.yaml`
**File:** `pricing.yaml`

The pricing file has `claude-3-5-sonnet` and `claude-3-opus` but not `claude-3-haiku-20240307`, which is the default Anthropic model in the router (router.py:62). `calculate_request_cost()` returns `0.0` for every Anthropic request because no pricing key matches.

---

## Code Quality

### Three `print("[DEBUG]")` statements in production code
- `app/services/router.py:45` — on every request
- `app/services/router.py:92` — on provider exhaustion
- `app/providers/anthropic.py:49-50` — on every Anthropic request (line 50 includes API key)

---

### Top-level `import openai` in `embedding.py`
**File:** `app/services/embedding.py:4`

Violates the stated rule: *"Avoid top-level imports of heavy dependencies."* Should be deferred to inside `__init__()` or `get_vector()`.

---

### Misplaced docstring in `cache.store()`
**File:** `app/services/cache.py:132`

```python
async def store(self, ...):
    import logging
    logger = logging.getLogger("semantic_cache")
    """Stores result in both Exact and Semantic indexes..."""  # NOT a docstring
```

The docstring appears after two statements, so Python treats it as a bare string expression. `store.__doc__` is `None`.

---

### Duplicate variable in `chat.py`
**File:** `app/api/routes/chat.py:206`

```python
user_prompt = request.messages[-1].content if request.messages else ""
```

Identical to `prompt` already computed at line 71. Just use `prompt`.

---

### Dead code in two places
- `app/api/routes/chat.py:248-253` — block after `return llm_response` on line 246; commented-out duplicate of headers already set
- `app/providers/anthropic.py:91-98` — second `return ChatResponse(...)` after the first; additionally uses `data["id"]` without `.get()`, unlike the live path which uses `data.get("id", "anthropic-unknown")`

---

### `test_chat_endpoint.py` is effectively empty
**File:** `tests/test_chat_endpoint.py`

Contains only a `pass` stub. The primary endpoint has zero meaningful test coverage.

---

## Priority Summary

| Priority | Severity | Issue | File |
|---|---|---|---|
| 1 | SECURITY | API key in plaintext `print()` | `anthropic.py:50` |
| 2 | HIGH BUG | PII middleware misses nested request body | `pii.py:51` |
| 3 | HIGH BUG | Sync Redis calls block event loop | `cache.py` |
| 4 | HIGH BUG | Double exact-cache lookup per request | `chat.py:88,131` |
| 5 | MEDIUM BUG | Anthropic creates new `AsyncClient` per request | `anthropic.py:14` |
| 6 | MEDIUM BUG | `Profiler.get_metrics()` crashes if `end()` not called | `profiler.py:34` |
| 7 | MEDIUM BUG | Test router stubs missing `call()` | `test_router.py` |
| 8 | MEDIUM BUG | Router mutates shared `ChatRequest.model` | `router.py:71` |
| 9 | DESIGN | Wrong logger namespace (`asyncio.log`) | `chat.py:5`, `router.py:10` |
| 10 | DESIGN | Cache/Embedding singleton pattern needed | `chat.py:67,70` |
| 11 | DESIGN | Broad `except Exception` in router hides bugs | `router.py:86` |
| 12 | DESIGN | `redact_all_strings` defined twice | `pii.py` |
| 13 | DESIGN | `REDIS_URL` not in Settings | `config.py` |
| 14 | DESIGN | `claude-3-haiku` missing from `pricing.yaml` | `pricing.yaml` |
| 15 | CLEAN | 3× `print("[DEBUG]")` in production | `router.py`, `anthropic.py` |
| 16 | CLEAN | Top-level `import openai` in `embedding.py` | `embedding.py:4` |
| 17 | CLEAN | Misplaced docstring in `cache.store()` | `cache.py:132` |
| 18 | CLEAN | Duplicate `user_prompt` variable | `chat.py:206` |
