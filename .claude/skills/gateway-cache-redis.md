---
name: gateway-cache-redis
description: Use when working on app/services/cache.py, app/services/embedding.py, app/models/cache_manager.py, or the cache orchestration block inside app/api/routes/chat.py. Covers HybridCache, EmbeddingService, RedisVL vector index management, TTL strategy, and semantic search.
---

# Gateway Cache & Redis Skill

You are working on the **hybrid caching and embedding layer** of an LLM proxy gateway. This is the most operationally sensitive part of the codebase — a mistake in the Redis index schema requires manual intervention (drop + recreate). Read this skill fully before touching `cache.py` or the vector index.

---

## Two-tier architecture

Every cache lookup follows this strict order. Do not skip Tier 1 or reorder:

```
Tier 1 — Exact match:   SHA-256 hash → Redis key-value (`exact:{hash}`)
Tier 2 — Semantic match: OpenAI embedding → HNSW cosine search (`cache:{hash}`)
```

Tier 1 costs ~1ms and nothing in API credits. Only compute the embedding vector (Tier 2) if Tier 1 misses. The cache orchestration in `chat.py` already implements this split — preserve it.

---

## Redis index schema

The vector index is defined in `HybridCache.__init__()` with these fixed parameters:

| Parameter | Value | Notes |
|---|---|---|
| Index name | `"llm_cache"` | Do not rename — used in all queries |
| Key prefix | `"cache"` | Semantic entries stored as `cache:{hash}` |
| Vector field | `"prompt_vector"` | float32 bytes |
| Dimensions | `1536` | Matches `text-embedding-3-small`; see open work |
| Algorithm | `HNSW` | Approximate nearest neighbor |
| Distance metric | `cosine` | Lower = more similar; 0.0 = identical |

**Critical**: if you change the number of dimensions, you must drop and recreate the index:
```python
self.index.drop()
self.index.create(overwrite=True)
```
You cannot add or modify fields in an existing HNSW index without this step. Running with mismatched dims will silently return garbage results.

Exact match entries use a separate key pattern (`exact:{hash}`) and are plain Redis string keys — no index involved, just `client.set()` / `client.get()`.

---

## Cache entry format

Every stored entry is a JSON object with this structure:

```json
{
  "prompt": "<original prompt string>",
  "response": { "<full ChatResponse.model_dump()>" },
  "cached_at": 1746000000.0
}
```

`cached_at` is a Unix timestamp (`time.time()`). It is the source of truth for freshness decisions — do not rely solely on Redis TTL for stale detection, because the TTL counts down from write time and you need the original write time for stale-while-revalidate logic.

---

## TTL and freshness strategy

TTL is set at store time based on query category. The category is passed by the caller; if omitted, the default applies.

| Category | TTL | Reasoning |
|---|---|---|
| `"fact"` | 7 days (604800s) | Facts rarely change |
| `"code"` | 5 days (432000s) | Libraries update occasionally |
| `"creative"` | 6 hours (21600s) | Users want variation |
| `"volatile"` | 0 (no-cache) | Real-time data; bypass entirely |
| default | 24 hours (86400s) | Conservative safe default |

**Stale-while-revalidate windows** (from `Settings`):
- `cache_fresh_window = 86400` (24h): return from cache immediately
- `cache_stale_window = 172800` (48h): return from cache, trigger background refresh

On a cache hit, always compute `age = time.time() - cached_at` and apply:
```python
if age < settings.cache_fresh_window:    # Fresh hit — return immediately
elif age < settings.cache_stale_window:  # Stale hit — return + trigger_refresh()
else:                                     # Expired — treat as miss
```

---

## Semantic similarity threshold

The current implementation uses a fixed threshold of `0.12` cosine distance (lower = more similar). This is overridable per-request via the `X-Semantic-Threshold` header.

**Open work**: implement a prompt-length-based dynamic threshold. The logic described in `changes.md`:

```python
def _calculate_dynamic_threshold(self, prompt: str) -> float:
    length = len(prompt)
    if length < 20:
        return 0.05   # Very strict for short commands
    elif length < 100:
        return 0.10
    else:
        return 0.15   # More relaxed for long context
```

The per-request header (`X-Semantic-Threshold`) should override this when provided.

---

## EmbeddingService

`EmbeddingService` in `app/services/embedding.py` supports two providers:

- `"openai"` (default): calls `text-embedding-3-small`, returns 1536-dim float list
- `"local"`: raises `NotImplementedError` — this is a real open gap

The provider is selected by the `EMBEDDING_PROVIDER` env var (default: `"openai"`). The service is instantiated in `chat.py` with `EmbeddingService(dims=1536)` — dims are hardcoded there and should become a `Settings` field (open work).

The embedding call must always be wrapped fail-open:
```python
try:
    vector = await embedding_service.get_vector(prompt)
except Exception as e:
    logger.error(f"Embedding service failed open: {e}")
    vector = None
```
If `vector is None`, skip Tier 2 cache lookup and proceed directly to the LLM.

---

## LLMCache in cache_manager.py — legacy, do not use

`app/models/cache_manager.py` contains a class called `LLMCache`. This is **not** used anywhere in the live request path — `HybridCache` in `cache.py` is what runs in production. `LLMCache` calls `ChatResponse.parse_raw()` which is Pydantic V1 syntax and will fail. It should be removed. Do not add new code that imports from `cache_manager.py`.

---

## Open work items owned by this domain

- [ ] **Dynamic semantic threshold**: implement `HybridCache._calculate_dynamic_threshold(prompt)` using a step function on prompt length; use it as the default when no `X-Semantic-Threshold` header is present.
- [ ] **Cache feedback endpoint**: add `POST /v1/cache/feedback` — receives `{"prompt": "..."}`, computes the SHA-256 hash, deletes `exact:{hash}` and `cache:{hash}` from Redis. Useful for demoing cache invalidation after a thumbs-down.
- [ ] **Local embedding provider**: implement `EmbeddingService` for `provider == "local"` using a lightweight local model (e.g., `sentence-transformers/all-MiniLM-L6-v2`), or formally mark it as unsupported with a clear error message.
- [ ] **Remove LLMCache**: delete `app/models/cache_manager.py` or rewrite it using Pydantic V2 if any new use case justifies keeping it.
- [ ] **Configurable vector dims**: move the hardcoded `dims=1536` from `chat.py:70` into `Settings` as `embedding_dims`. Pass `settings.embedding_dims` to both `EmbeddingService` and the index schema.

---

## Verification

After any change to cache or embedding code, run:

```bash
poetry run pytest
```

For changes to the RedisVL index schema, also verify manually with a running Redis instance:

```bash
docker-compose up cache -d
poetry run uvicorn app.main:app --reload
# Send a test request and confirm semantic cache hit/miss behavior
```
