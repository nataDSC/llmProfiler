# AnthropicAdapter Changes

## The System Message Trap

- Anthropic does not allow a "system" role inside the messages array.
- It expects a top-level `system` parameter.
- Sending a system message in the array will cause the API to throw a 400 error.

## HTTP Client Efficiency

- Previously, a new `httpx.AsyncClient()` was created for every request.
- This is expensive due to requiring a new TCP handshake each time.
- Use the shared client from your `app.core.http` module instead.

## Required Headers

- Anthropic requires the `anthropic-version` header (e.g., `2023-06-01`).
- Requests without this header will fail.

## Data Mapping

- Anthropic returns a `content` array with text blocks.
- OpenAI returns `choices` with a message.
- The adapter needs to translate this format so the rest of the app remains agnostic about the provider.

## Metric Consistency

- Use the `_create_metrics` helper built into `BaseLLMAdapter` to ensure telemetry is consistent across providers.

## The System Parameter

- Filtering messages ensures requests won't crash if users include a system prompt.

## Performance

- Passing the client as an argument (Dependency Injection) allows maintaining a Connection Pool.
- This significantly improves speed under high load.

## Identical Output

- Choices mapping ensures frontend/UI works seamlessly regardless of whether data comes from Anthropic or another provider.

# The Router Changes

## Handling Logic: "If OpenAI returns a 503, wait 500ms and try Anthropic"

- Distinguish between User Errors (400 Bad Request) and Provider Failures (500 Internal Server Error or Timeout).
- Retry or fallback only if the provider is actually "broken," not if user input is invalid.

## Additional Logic Implementations:

1. **The 4xx vs 5xx Distinction**
   - If user prompts violate safety filters or use invalid parameters, Anthropic will likely reject them too.
   - Failing fast on 4xx errors saves money and provides immediate feedback instead of fallback on 400 Bad Request.
2. **Exponential Backoff (Light)**
   - Using `await asyncio.sleep(0.5)` helps avoid repeated failures during momentary blips in OpenAI's service.
   - A 500ms delay allows load balancers to find healthy nodes.
3. **Connection Pooling**
   - Passing `self.http_client` into adapters uses a single pool of TCP connections.
   - This reduces overhead, allowing handling of thousands of concurrent requests efficiently.

## The profiler changes (refinement)

1. Profiler.py: added a helper to "output" the Pydantic model we need.
2. Pricing.py: ensure we don't return None (which causes crashes) and handle the 1M token math.
3. Chat.py route: initial implementation

## High performance client

1. http.py: manages a single, high-performance client that all your requests will share.
2. main.py: for the shared client to work, FastAPI needs to "turn it on" when the server starts and "turn it off" when it stops. We do this using a lifespan function.

   Now, when chat.py calls from app.core.http import get_http_client, the function exists and is ready to be used as a FastAPI Depends().
   Stability: The Limits we set (max_connections=100) prevent the gateway from accidentally DOS-ing itself or opening too many file handles on the Mac.

3. config.py: error handling and pathing update.

   The Path Library: Using Path(**file**) ensures that the app always finds pricing.yaml in the project root, even if we run the command from ~/Documents or /Users/nataliep/code.
   Graceful Degradation: By returning {"providers": {}} instead of raising an exception, the API will still start. We'll just get $0.00 for your cost metrics until we fix the YAML file. This is much better than a "silent death" where the server won't even boot.
   Logging: Using logger.error instead of a standard print(). It allows these errors to show up in the Docker logs or cloud monitoring tools later.

# Hybrid matching

By combining Exact Match and Semantic Caching, we are building what’s known as a Hybrid Cache.
In production, this is how you save thousands of dollars:

1. Exact Match: Instant, $O(1)$ lookup for identical strings (e.g., "What is the capital of France?").
2. Semantic Match: A "fuzzy" lookup using vector similarity (e.g., "Tell me France's capital" vs. "What is the capital city of France?").

## 🏗️ The Strategy: "The Two-Tier Lookup"

The CacheService should follow this logic for every request:

1. Level 1 (The Hash): Create a SHA-256 hash of the prompt. If it exists in Redis, return it immediately. This costs almost zero $ms$.
2. Level 2 (The Vector): If Level 1 fails, convert the prompt into an Embedding (a list of numbers). Search the vector database (Redis) for a "neighbor" with a similarity score $> 0.95$.
3. The Result: If either hits, then bypass the LLM entirely.

## 🛠️ The Implementation: cache.py

We’ll need redisvl (Redis Vector Library) or similar to handle the semantic part efficiently on the Mac Pro.

## 🔌 3. Wiring it into the Router

The best place to put this is in your Router or a new Orchestrator service. It needs to happen before the llm_router.route() call.

Inside your chat.py route logic:

```Python

   cache = HybridCache(settings.redis_url)

   # 1. Get embedding (only if exact match fails or to prepare for semantic)

   # Note: You need a cheap model like 'text-embedding-3-small' for this

   vector = await get_embedding(request.messages[-1].content)

   # 2. Check Cache

   cached_response, hit_type = await cache.check(request.messages[-1].content, vector)

   if cached*response: # Build a "Fake" ChatResponse but mark it as a Cache Hit
     return ChatResponse(
       ...
       metrics=GatewayMetrics(..., provider_used=f"cache*{hit_type}", estimated_cost_usd=0.0)
     )
```

## 🧐 The Trade-offs

- The Embedding Tax: Semantic caching isn't free. We have to call an embedding API (like OpenAI's) which costs a tiny amount of money and time (approx. $50ms$). Only do this if the prompt is long enough to justify the "gamble."
- The Threshold Problem: Setting the similarity threshold is an art. If it's too loose ($<0.90$), the gateway might return an answer to a different question. If it's too strict ($>0.98$), you'll almost never get a hit. Start at 0.95.
- Privacy: If the gateway handles PII (Personal Identifiable Information), we should never semantically cache those requests, as User A might receive User B's private data if their questions are semantically similar.

# Questions/concerns

## 1. Embedding Generation:

- The cache expects a vector (embedding) for semantic search. Should the cache service itself call the embedding model (e.g., OpenAI/Anthropic) if the vector is not provided, or should the caller always supply the embedding?

## 2. Response Format:

- Should the cache always return the full LLM response (including metrics), or just the text? Your current code stores a dict with both prompt and response.

## 3. Vector Dimensions:

- The code uses 1536 dims (OpenAI embedding size). Is this fixed, or should it be configurable for other providers?

## 4. Error Handling:

- Should the cache fail open (continue to LLM if Redis is down), or fail closed (raise error)?

# The answers

## 1. Embedding Generation:

The "Caller" should handle it
The HybridCache should remain storage-agnostic. Its only job is to talk to Redis. If you bake the OpenAI embedding call into the cache, you make it much harder to swap in that local model later.

### The Strategy:

Create a separate EmbeddingService. The Router (the orchestrator) should call the Embedding Service first, then pass that vector into the HybridCache.

### Pro Tip:

This allows you to skip the embedding call entirely if an Exact Match (the hash) is found first, saving you that $50ms$ and the tiny API cost.

## 2. Response Format:

Store the "Standardized Payload"Don't just store the text. Store a serialized version of the choices and usage dictionary.

### Why?

If you only store the text, your Gateway has to "invent" a fake response ID, model name, and usage stats every time there's a cache hit.

### The "Senior" Way:

Store the full JSON payload but strip the metrics. When you return a cached response, the Profiler can then attach new metrics (e.g., provider: "cache_semantic", latency: 12ms, cost: 0.00) so the user knows exactly why the response was so fast.

## 3. Vector Dimensions:

Make it ConfigurableWhile 1536 is the standard for OpenAI, you should definitely make this a config variable.

- If you switch to a local model like bge-small-en-v1.5, you'll be dealing with 384 or 768 dimensions.
- Warning: In Redis, once an index is created with 1536 dimensions, you can't just "change" it. You have to drop and recreate the index. Coding this as a variable now will save you a massive headache during your first migration.

## 4. Error Handling: Always "Fail Open"

For a Gateway, the cache is an optimization, not a critical path.

- The Rule: If Redis is down, log the error and proceed to the LLM.
- The Logic: It is better to spend $0.03 and wait 2 seconds for a "live" answer than to return a 500 error to the user because your cache was grumpy.

# 🛠️ The "Agent-Ready" Guidance

## The Orchestration Logic

```
  # 1. Check Exact Match (Fast/Free)

  cached_hit, type = await cache.check_exact(prompt)
  if cached_hit: return cached_hit

  # 2. Get Embedding (Costs time/money)

  vector = await embedding_service.get_vector(prompt)

  # 3. Check Semantic Match

  cached_hit, type = await cache.check_semantic(vector)
  if cached_hit: return cached_hit

  # 4. Fallback to LLM

  # 5. Store result in Cache (Background Task)
```
