---
name: refactor-components
description: Use when fixing bugs, refactoring existing code, or resolving any issue identified in docs/code-review-findings.md. Covers the safe order of changes, what to read before touching a file, which invariants must be preserved, and how to verify each fix.
---

# Refactor Components Skill

You are fixing or refactoring code in an async FastAPI LLM gateway. Before making any change, read this skill in full. It tells you where to find context, what order to work in, and what must never break.

---

## Context documents to read before starting

These three documents give you everything you need. Read whichever ones are relevant to the files you are touching:

| Document | When to read it |
|---|---|
| `repo_analysis.md` | Orientation: request flow, module map, how components connect. Read this first if you are new to a subsystem. |
| `docs/code-review-findings.md` | The authoritative list of known bugs and design problems, with file:line references and severity ratings. Work from this list. |
| `docs/agentic-harness-plan.md` | Cross-domain coordination: which agent owns what, open work items by domain. Check before adding new features. |

The domain skills give you invariants specific to each area:

| Skill | Use for |
|---|---|
| `gateway-backend` | `app/providers/`, `app/services/router.py`, `app/middleware/`, `app/core/`, `app/api/routes/chat.py` |
| `gateway-cache-redis` | `app/services/cache.py`, `app/services/embedding.py`, cache orchestration in `chat.py` |
| `gateway-testing` | Any file in `tests/`, adding coverage after a fix |
| `gateway-ui` | Anything in `ui/` |
| `gateway-deployment` | `Dockerfile`, `docker-compose*.yml`, deployment scripts |

---

## Priority order for fixes

Work from the top of this list down. Do not skip to a lower-priority item while a higher-priority one in the same domain is unfixed.

| Priority | Severity | Issue | File |
|---|---|---|---|
| 1 | SECURITY | API key in plaintext `print()` | `app/providers/anthropic.py:50` |
| 2 | HIGH BUG | PII middleware misses nested request body | `app/middleware/pii.py:51` |
| 3 | HIGH BUG | Sync Redis calls block event loop | `app/services/cache.py` |
| 4 | HIGH BUG | Double exact-cache lookup per request | `app/api/routes/chat.py:88,131` |
| 5 | MEDIUM BUG | Anthropic creates new `AsyncClient` per request | `app/providers/anthropic.py:14` |
| 6 | MEDIUM BUG | `Profiler.get_metrics()` crashes if `end()` not called | `app/services/profiler.py:34` |
| 7 | MEDIUM BUG | Test router stubs missing `call()` | `tests/test_router.py` |
| 8 | MEDIUM BUG | Router mutates shared `ChatRequest.model` | `app/services/router.py:71` |
| 9 | DESIGN | Wrong logger namespace (`asyncio.log`) | `chat.py:5`, `router.py:10` |
| 10 | DESIGN | Cache/Embedding singleton pattern needed | `chat.py:67,70` |
| 11 | DESIGN | Broad `except Exception` in router hides bugs | `app/services/router.py:86` |
| 12 | DESIGN | `redact_all_strings` defined twice | `app/middleware/pii.py` |
| 13 | DESIGN | `REDIS_URL` not in Settings | `app/core/config.py` |
| 14 | DESIGN | `claude-3-haiku` missing from `pricing.yaml` | `pricing.yaml` |
| 15 | CLEAN | 3× `print("[DEBUG]")` in production paths | `router.py`, `anthropic.py` |
| 16 | CLEAN | Top-level `import openai` in `embedding.py` | `app/services/embedding.py:4` |
| 17 | CLEAN | Misplaced docstring in `cache.store()` | `app/services/cache.py:132` |
| 18 | CLEAN | Duplicate `user_prompt` variable | `app/api/routes/chat.py:206` |

---

## Invariants that must not break

These are non-negotiable. Any refactor that breaks one of these is wrong even if the new code looks cleaner.

**Fail-open**: Cache, embedding, and rate limiting are optimization paths, not critical paths. Every call to these services must be inside `try/except`. On failure: log with `logger.error()` and continue. Never let a Redis timeout or embedding error surface as a 500.

**Middleware order is load-bearing**: In `app/main.py`, `PIISanitizerMiddleware` runs first (registered first), `metrics_middleware` runs second. If reversed, Prometheus will record unredacted PII in label values and the cache will store unredacted prompts.

**Pydantic V2**: Use `model_dump()` not `.dict()`, `model_dump_json()` not `.json()`, `model_validate()` not `parse_obj()`. Never `parse_raw()`.

**Async discipline**: All I/O must be `async/await`. Never use `requests`, `time.sleep()`, or synchronous Redis calls in async functions. The Redis client issue (#3 above) is specifically about this — when fixing it, switch to `redis.asyncio.Redis`, not just wrapping sync calls in `asyncio.run_in_executor`.

**Shared HTTP client**: The singleton `httpx.AsyncClient` in `app/core/http.py` is the only HTTP client for outbound requests. Adapters must receive it via `Depends(get_http_client)` and never instantiate their own. This is the root cause of finding #5 (Anthropic adapter).

**Absolute imports only**: `from app.services.profiler import Profiler`, never `from ..services.profiler import Profiler`.

**Deferred heavy imports**: `openai`, `redisvl`, `anthropic` are imported inside methods, not at module top level. When fixing finding #16 (embedding.py), move `import openai` inside `__init__`.

**OpenAI-compatible response shape**: `ChatResponse` must remain structurally compatible with the OpenAI API shape. The `choices[0].message.content` and `choices[0].message.original_content` fields are consumed by the Streamlit UI and must not be renamed or removed.

---

## How to fix each category of finding

### Security fix (finding #1 — API key in print)
Delete the `print()` calls at `anthropic.py:49-50`. The `logger.info()` at line 47-48 is fine (it masks the key). Do not replace `print()` with `logger.debug()` for the headers line — it still exposes the key. Just remove it.

### PII fix (finding #2 — shallow request redaction)
In `app/middleware/pii.py`, replace the shallow loop in `dispatch()`:
```python
# Before (only top-level keys):
for k, v in data.items():
    if isinstance(v, str):
        data[k] = redact_pii(v)
body = json.dumps(data).encode()

# After (recursive, uses existing module-level function):
data = redact_all_strings(data)
body = json.dumps(data).encode()
```
Also remove the local `redact_all_strings` function defined inside `dispatch()` (lines 66-75) — it duplicates the module-level one. This fixes findings #2 and #12 together.

### Async Redis fix (finding #3)
`HybridCache` currently uses `self.index.client` which is RedisVL's synchronous Redis client. The fix:
1. Create a separate `redis.asyncio.Redis` instance from the same URL.
2. Use `await self.async_client.get()`, `await self.async_client.set()`, etc. in `check()` and `store()`.
3. The sync client can stay for `self.index` (RedisVL's vector query interface) since RedisVL may not have an async path — only the key-value operations need to be async.
4. In `invalidate_all()`, change `scan_iter` and `delete` to their async equivalents.
**Do not** change the RedisVL `SearchIndex` calls to async unless RedisVL explicitly supports it — check the library version first.

### Double cache check fix (finding #4)
The caller (`chat.py`) calls `cache.check()` twice. The fix is structural: split the exact-match check into its own call and only pass the vector to the semantic check:
```python
# Tier 1: exact only
exact_hit, cache_type = await cache.check_exact(prompt)
if exact_hit: ...

# Tier 2: semantic only (vector already computed)
semantic_hit, cache_type = await cache.check_semantic(prompt, vector, threshold)
if semantic_hit: ...
```
Add `check_exact()` and `check_semantic()` to `HybridCache` by splitting the existing `check()` body. Keep `check()` as a thin wrapper if any other caller uses it.

### Singleton pattern fix (finding #10)
Move `HybridCache` and `EmbeddingService` construction into the FastAPI lifespan in `app/main.py`, storing them in `app.state`. Then provide them as FastAPI dependencies:
```python
async def get_cache(request: Request) -> HybridCache | None:
    return request.app.state.cache

async def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service
```
Inject via `Depends()` in the route handler signature. The admin `invalidate_cache` endpoint should use the same dependency.

### Logger fix (finding #9)
Replace `from asyncio.log import logger` with:
```python
import logging
logger = logging.getLogger(__name__)
```
In `chat.py` and `router.py`. Also remove the per-call `import logging; logger = logging.getLogger(...)` pattern inside `cache.py` methods — create a single module-level logger instead.

### Router mutation fix (finding #8)
In `app/services/router.py`, replace:
```python
request.model = mapped_model
```
with:
```python
request = request.model_copy(update={"model": mapped_model})
```

### Router exception handling fix (finding #11)
Narrow the broad `except Exception` in the router's fallback loop. Only network/timeout errors should trigger fallover:
```python
except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
    last_exception = e
    logger.warning(...)
# Let all other exceptions (AttributeError, TypeError, etc.) propagate
```

### Settings fix (finding #13)
Add `redis_url` to `Settings`:
```python
self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
```
Then replace all `os.getenv("REDIS_URL", "redis://localhost:6379")` call sites with `settings.redis_url`.

### Pricing fix (finding #14)
Add `claude-3-haiku-20240307` to `pricing.yaml` under the `anthropic` provider. Current pricing (as of 2026): input $0.25/1M tokens, output $1.25/1M tokens. Verify current rates before committing.

---

## Verification after every change

After any edit to `app/` or `tests/`:

```bash
poetry run pytest
```

All tests must pass before the task is considered complete. If a test fails, fix the root cause — do not skip or mark xfail unless explicitly asked.

For the PII fix specifically, also run:
```bash
docker-compose up cache -d
ECHO_MODE=true poetry run uvicorn app.main:app --reload
# POST a message with a nested SSN and verify it is redacted
```

For the async Redis fix, verify manually with a running Redis instance before trusting tests alone — the event loop blocking issue won't be caught by synchronous TestClient tests.

---

## What not to do

- Do not refactor code that isn't broken just because it looks improvable. Scope every change to the finding being fixed.
- Do not change the `ChatResponse` or `GatewayMetrics` field names or shapes — the Streamlit UI and any HF Space integration depend on them.
- Do not remove the `trace` and `redacted_prompt` fields — they are the PII demo features.
- Do not add new top-level imports of `openai`, `redisvl`, or `anthropic`.
- Do not change middleware registration order in `app/main.py`.
- Do not swap `model_dump()` for `.dict()` or any other Pydantic V1 method.
- Do not use `requests` or `time.sleep()` anywhere in `app/`.
