# Agentic Harness Plan — llmProfiler

## Purpose

This document records the design decisions behind the `.claude/skills/` harness added to this project. It captures what was found during analysis, which skill covers which domain, how multi-agent work should be coordinated, and what open work each agent is responsible for completing.

---

## Project Status at Time of Analysis (May 2026)

All 7 implementation phases are marked complete in `implementation-plan.md`, but code inspection revealed the following real gaps:

| Gap | File / Location | Priority |
|---|---|---|
| Rate limiting never implemented | `app/core/limiter.py` missing entirely | High |
| `BaseLLMAdapter.calculate_cost()` returns `0.0` placeholder | `app/providers/base.py:35` | High |
| Local embedding provider raises `NotImplementedError` | `app/services/embedding.py:26` | Medium |
| Cache feedback endpoint `/v1/cache/feedback` | discussed in `changes.md`, absent from routes | Medium |
| Dynamic semantic threshold (prompt-length scaling) | static `0.12` in code | Medium |
| `LLMCache` in `cache_manager.py` uses Pydantic V1 `parse_raw()` | `app/models/cache_manager.py:38` | Medium |
| Unreachable code block | `app/api/routes/chat.py:248-253` (after `return` on line 246) | Low |
| Debug `print()` statements in production path | `app/services/router.py:45,92` | Low |
| Vector dims hardcoded at call site | `app/api/routes/chat.py:70` — has a `TODO` comment | Low |
| AWS deployment not done | `docs/aws_deployment_plan.md` exists but not executed | Planned |

---

## Skill Files Created

All skills live in `.claude/skills/`. Each file is a markdown document with a YAML frontmatter `description` field that controls when it auto-triggers.

```
.claude/
└── skills/
    ├── gateway-backend.md       # Core API, providers, routing, middleware
    ├── gateway-cache-redis.md   # HybridCache, EmbeddingService, vector search
    ├── gateway-testing.md       # Test patterns, async fixtures, coverage gaps
    ├── gateway-ui.md            # Streamlit UI (separate container, separate concerns)
    └── gateway-deployment.md   # Docker, HF Spaces, AWS
```

---

## Domain Boundaries and Agent Assignments

### Why split into multiple agents?

Three areas of this codebase have sufficiently different knowledge requirements that a single skill would be too broad to be useful:

1. **Cache/Redis** (`gateway-cache-redis`) — RedisVL HNSW index management, vector serialization, and TTL strategy are operationally distinct from FastAPI. A mistake here (wrong vector dims, missing `expire()` call) corrupts the index and requires manual intervention.

2. **UI** (`gateway-ui`) — The Streamlit app in `ui/` has zero Python import relationship with `app/`. It communicates only via HTTP. An agent working here needs the gateway's external API contract, not its internals.

3. **Testing** (`gateway-testing`) — This project's tests require `pytest-asyncio`, an autouse `.env` fixture, and careful mocking of Redis and the OpenAI SDK. An agent without this context will write sync tests for async functions or forget to mock external services.

### Domain map

| Directory / File | Owning skill |
|---|---|
| `app/providers/` | gateway-backend |
| `app/services/router.py` | gateway-backend |
| `app/services/pricing.py` | gateway-backend |
| `app/middleware/` | gateway-backend |
| `app/core/` | gateway-backend |
| `app/api/routes/chat.py` | gateway-backend (orchestration), gateway-cache-redis (cache block) |
| `app/services/cache.py` | gateway-cache-redis |
| `app/services/embedding.py` | gateway-cache-redis |
| `app/models/cache_manager.py` | gateway-cache-redis |
| `app/models/chat.py` | gateway-backend |
| `tests/` | gateway-testing |
| `ui/` | gateway-ui |
| `Dockerfile`, `docker-compose*.yml`, `scripts/` | gateway-deployment |

---

## Multi-Agent Coordination Patterns

### Pattern 1: Sequential hand-off (new feature)

Used when implementing a new backend feature that needs tests and potentially UI changes.

```
1. gateway-backend   →  implements the feature, defines public API contract
2. gateway-testing   →  writes tests against the contract (can start once interface is defined)
3. gateway-ui        →  adds UI support if the feature is user-visible
```

**Example:** Rate limiting
- backend: `app/core/limiter.py` + wire into `chat.py`
- testing: `tests/test_rate_limiting.py`
- ui: 429 error state in `ui/main.py`

### Pattern 2: Parallel (cache + test)

When a cache-only improvement has no UI impact, the cache agent and testing agent can work in parallel once the interface is stable.

```
gateway-cache-redis  →  HybridCache._calculate_dynamic_threshold()
gateway-testing      →  tests/test_cache_and_security.py additions
                        (can run in parallel — no shared state)
```

### Pattern 3: UI-only (no backend change)

When fixing or improving the Streamlit UI without touching `app/`:

```
gateway-ui  →  works alone; uses gateway HTTP contract documented in the skill
```

---

## Open Work by Agent

### gateway-backend owns:
- [ ] Implement `app/core/limiter.py` — Redis-backed fixed-window rate limiter (~15 LOC)
- [ ] Wire `RateLimiter` into `app/api/routes/chat.py` as a FastAPI dependency
- [ ] Remove `print()` debug statements from `app/services/router.py:45,92`
- [ ] Remove unreachable code block in `app/api/routes/chat.py:248-253`
- [ ] Resolve `BaseLLMAdapter.calculate_cost()` — delegate to `calculate_request_cost()` or remove

### gateway-cache-redis owns:
- [ ] Implement prompt-length-based dynamic threshold in `HybridCache.check()`
- [ ] Implement `/v1/cache/feedback` POST endpoint (thumbs-down deletes Redis key)
- [ ] Implement local embedding provider in `EmbeddingService` (or formally mark as unsupported)
- [ ] Remove or rewrite `LLMCache` in `app/models/cache_manager.py` (Pydantic V1, unused)
- [ ] Make vector dims configurable via `Settings` (remove hardcoded 1536 at call site)

### gateway-testing owns:
- [ ] Tests for rate limiting (after `limiter.py` is implemented)
- [ ] Tests for cache feedback endpoint
- [ ] Tests for dynamic semantic threshold logic
- [ ] Coverage audit: identify untested branches in `chat.py`

### gateway-ui owns:
- [ ] 429 error state in UI (after rate limiting is implemented)
- [ ] Verify HF Spaces deployment matches local behavior for cache invalidation and semantic threshold slider

### gateway-deployment owns:
- [ ] AWS App Runner deployment (per `docs/aws_deployment_plan.md`)
- [ ] Verify `scripts/hf_deploy_gateway.sh` and `scripts/hf_deploy_ui.sh` use `--platform linux/amd64`

---

## Invariants Every Agent Must Respect

These cross-cut all skills and are repeated in each skill file:

1. **Fail-open**: cache, embeddings, and rate limiting are non-critical paths. Wrap in `try/except`, log, continue.
2. **Pydantic V2**: `model_dump()` not `.dict()`, `model_dump_json()` not `.json()`. Never use `parse_raw()`.
3. **Async discipline**: no blocking I/O (`requests`, `time.sleep`) in async functions.
4. **Shared HTTP client**: never create `httpx.AsyncClient` inside a method; use the singleton from `app/core/http.py`.
5. **Run tests before closing**: `poetry run pytest` must pass after any change to `app/` or `tests/`.
