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

# 🧠 The Strategy: Tiered TTL

Setting a cache TTL (Time To Live) for an LLM Gateway isn't just about saving memory—it's about balancing "Cost Savings" against "Model Drift." If you cache an answer for a year, and OpenAI releases a better model next month, your users are stuck with "old" intelligence.
A hard-coded 3600 seconds (1 hour) is great for testing, but in production, you want a more nuanced strategy.

A one-size-fits-all TTL is rarely the right move. Instead, consider categorizing your traffic:

| Category TTL                                    | Duration         | Reasoning                                           |
| ----------------------------------------------- | ---------------- | --------------------------------------------------- |
| Fact-Based (e.g., "Capital of France")          | 7 - 30 Days      | Facts don't change often. Save the tokens.          |
| Creative/Subjective (e.g., "Write a poem")      | 1 - 12 Hours     | Users likely want fresh "creativity" or variations. |
| Code/Technical (e.g., "Python regex for email") | 3 - 7            | Days Stable, but libraries update.                  |
| Highly Volatile (e.g., "Stock price of Apple")  | 0 (Do Not Cache) | Real-time data should never be cached semantically. |
|                                                 |

## 🚀 Implementation Strategy: "The Buffer Zone"

Instead of a "Hard Expiry," many high-scale gateways use Stale-While-Revalidate:

- 0–24 hours: Return from cache immediately.
- 24–48 hours: Return from cache, but trigger a background task to refresh the answer from the LLM so the next user gets a fresh one.

## 🛠️ Implementation in HybridCache

Since we are using Redis for both exact and semantic matches, implementation differs slightly for each.

## 1. Exact Match (The Easy Part)

The current self.client.set(..., ex=3600) is correct for exact matches. To make it production ready, we will pull the TTL from a mapping or a default config.

```
   # In HybridCache.store
   # Logic: Allow the caller to suggest a 'priority' or 'category'
   default_ttl = settings.cache_ttl_seconds # e.g., 86400 (24h)

   await self.index.client.set(
      f"exact:{prompt_hash}",
      json.dumps(data),
      ex=custom_ttl or default_ttl
   )
```

## 2. Semantic Match (The HNSW Part)

Redis Vector searches (HNSW/Flat) usually store data in Hashes. Unlike simple keys, we can't set a TTL on an individual field inside a Hash, but we can set a TTL on the entire Hash key that represents the vector entry.
If you are using redisvl or raw Redis hashes:

```
   async def store_semantic(self, prompt_hash: str, vector: list, data: dict, ttl:  int):
      key = f"cache:{prompt_hash}"

      # 1. Store the data and vector
      await self.index.load([{
        "id": key,
        "prompt_vector": vector,
        "response": json.dumps(data)
      }])

      # 2. MANUALLY set the expiry on the hash key
      # RedisVL 'load' creates keys with the prefix you defined in the index
      await self.index.client.expire(key, ttl)
```

### 🔍 Pro-Tip: The "Metadata" Trick

If you want to get fancy, don't just rely on Redis to delete the key. Store a created_at timestamp inside your cached JSON.

```
data = {
    "response": llm_text,
    "cached_at": time.time(),
    "model": "gpt-4o"
}
```

### Why?

Because when you do a Semantic Search, Redis might return a "96% match" from 3 days ago. If your HybridCache.check sees that the match is "old" but the user asked for "High Freshness," you can choose to ignore the cache hit and hit the LLM instead.

### 📉 A Note on Redis Memory

If you don't set a TTL, your Redis instance will eventually hit its maxmemory limit and start evicting keys based on its policy (likely allkeys-lru). Setting an explicit TTL ensures you are the one deciding what stays and what goes, rather than leaving it to a "Least Recently Used" algorithm.

# 📈 Next Step: The "Cache Bypass"

Sometimes a user knows the cache is stale and wants a fresh answer. It's common to implement a header like X-Cache-Control: no-cache.
This will take to update the FastAPI route to respect a "No-Cache" header from the user. It’s a small change that makes the gateway feel much more "controllable."

Implementing a Cache Bypass is a standard "Quality of Life" feature for developers. It allows them to force a fresh response from the LLM without having to wait for the TTL to expire or manually clearing the Redis database.
Using the standard Cache-Control header makes your gateway feel like a first-class citizen of the web.

## 🚦 The Logic Flow

When a request hits the endpoint, we check the headers before doing any expensive vector math or cache lookups. If the user sends Cache-Control: no-cache, we treat it as a "Cache Miss" and go straight to the provider.

## 🛠️ Updating the Route: app/api/routes/chat.py

Here is how you modify the FastAPI endpoint to extract the header and toggle the cache logic.

```
from fastapi import APIRouter, Depends, Request, Response
# ... other imports ...

@router.post("/chat/completions")
async def chat_completions(
    request: ChatRequest,
    http_req: Request,
    response: Response,
    # ... dependencies ...
):
    # 1. Detect Cache Bypass Header
    # Check for 'no-cache' or 'no-store' in the standard header
    cache_header = http_req.headers.get("Cache-Control", "").lower()
    bypass_cache = "no-cache" in cache_header or "no-store" in cache_header

    # 2. Start Profiler
    p = Profiler()
    p.start()

    # 3. Conditional Cache Lookup
    cached_response = None
    if not bypass_cache:
        # Only run this if the user hasn't explicitly requested a fresh result
        cached_response, hit_type = await hybrid_cache.check(request.prompt)

        if cached_response:
            # Handle Cache Hit (Return early)
            p.end()
            return prepare_cached_response(cached_response, hit_type, p)

    # 4. Standard LLM Logic (If bypass=True OR Cache=Miss)
    llm_response = await llm_router.route(request)

    # 5. Background Task: Update Cache
    # We always update the cache with the newest response so the NEXT
    # request (without no-cache) is up to date.
    await hybrid_cache.store(request.prompt, llm_response)

    return finalize_response(llm_response, p)
```

### 🧐 Why this is the "Senior" Way

1. Standardization: Using Cache-Control: no-cache is better than creating a custom header like X-Skip-Cache. It allows standard tools (like Postman, Curl, or Chrome) to interact with your gateway using built-in features.
2. Telemetry Accuracy: When a user bypasses the cache, your GatewayMetrics should reflect that. You can set provider_used to something like openai (forced-refresh) so you can track in your analytics how often users feel the need to bypass your cache.
3. The "Passive Refresh" Pattern: Notice that even if the user bypasses the cache to read, we still write the new result back to Redis. This keeps the cache "fresh" without requiring a separate maintenance script.

## 🚀 How to test it

You can test this from your terminal on your Mac Pro:
Normal Request (Hits Cache):
Bash

curl -X POST http://localhost:8000/v1/chat/completions -d '{"prompt": "Hello"}'
Bypass Request (Forces OpenAI/Anthropic):
Bash

curl -H "Cache-Control: no-cache" -X POST http://localhost:8000/v1/chat/completions -d '{"prompt": "Hello"}'

# 📈 Next: The Semantic Threshold

Now that we have the bypass, we'll likely notice that Semantic Caching is sometimes "too aggressive" (returning answers that aren't quite right).
Let's implement a "Dynamic Threshold". This will allow us to be very strict for short queries (where every word matters) but more relaxed for long paragraphs.

Implementing a Dynamic Threshold solves the "Goldilocks" problem of semantic caching: fixed thresholds are often too loose for short, precise queries ("What is 2+2?") and too strict for long, rambling paragraphs where the core intent remains the same despite word changes.

By adjusting the required similarity score based on the character count or token count of the prompt, we ensure high precision where it matters most.

## 🧠 The Logic: The "Strictness Slope"

For short queries, the distance between "What is Apple's stock?" and "What is Apple's price?" is semantically small but contextually massive. We want a very high similarity requirement. For a 500-word essay prompt, a few different adjectives shouldn't break the cache hit.
A simple linear model for the threshold T could look like this:
$$T = \min(T_{max}, T_{base} + (L \cdot \alpha))$$
Where:

- $T_{base}$: Your starting strictness (e.g., 0.92).
- $L$: Length of the prompt.
- $\alpha$: The "Relaxation Constant."

## 🛠️ Implementation: app/services/cache.py

Update the check method to calculate the required score on the fly before querying Redis.

```
class HybridCache:
    # ... previous init code ...

    def _calculate_dynamic_threshold(self, prompt: str) -> float:
        """
        Adjusts the 'similarity' requirement based on prompt length.
        Short prompts = High Strictness (e.g., 0.98)
        Long prompts = Lower Strictness (e.g., 0.92)
        """
        length = len(prompt)

        # Define your bounds
        min_threshold = 0.92
        max_threshold = 0.98

        # Simple Step-Function (Easier to debug than linear decay)
        if length < 20:
            return max_threshold # Very strict for short commands
        elif length < 100:
            return 0.95
        else:
            return min_threshold # More relaxed for long context

    async def check(self, prompt: str, vector: list[float] = None):
        # 1. Tier 1: Exact Match (Still first, still fastest)
        # ... logic ...

        # 2. Tier 2: Semantic Match with Dynamic Threshold
        if vector:
            required_threshold = self._calculate_dynamic_threshold(prompt)

            # RedisVL uses 'distance' (0.0 is identical, 1.0 is opposite)
            # So Distance = 1.0 - Similarity
            max_distance = 1.0 - required_threshold

            query = VectorQuery(
                vector=vector,
                vector_field_name="prompt_vector",
                return_fields=["response", "dist"],
                num_results=1
            )
            results = self.index.query(query)

            if results:
                actual_dist = float(results[0]["dist"])
                if actual_dist <= max_distance:
                    return json.loads(results[0]["response"]), "semantic"

                logger.info(f"Close but no cigar: dist {actual_dist} > limit {max_distance}")

        return None, None
```

### 🧐 Why this is "Professionsl-Grade"

1. Precision Engineering: Most "LLM Wrappers" just pick 0.95 and hope for the best. Showing you’ve accounted for query length demonstrates you understand the nuances of Vector Embeddings.
2. Debuggability: By logging the "Close but no cigar" message, you can tune your threshold. If you see many results at 0.06 distance being rejected for short queries, you know your max_threshold might be too high.
3. User Experience: This prevents "Hallucinated Cache Hits"—one of the most frustrating bugs in AI apps where the user asks a specific question but gets a cached answer for a similar-sounding but different topic.

### 📉 The Trade-off: The "False Positive"

Even with a dynamic threshold, semantic caching is never 100% perfect. In your GatewayMetrics, you should always report the distance score for semantic hits. This allows you to audit your cache later and see if users are getting low-quality responses.

# 📈 Final Polish: Adding "Human Feedback"

To make this truly elite, we add a small endpoint /v1/cache/feedback where a user (or a frontend) can send a "Thumbs Down" on a response. If a response gets a "Thumbs Down" and was a cache hit, you can automatically delete that key from Redis.
