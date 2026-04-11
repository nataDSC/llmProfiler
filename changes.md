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

# Production-Grade Engineering Showcase

The architect-grade plan has done a great job of capturing the **Business Value** (Cost, PII, Failover) alongside the **Technical Specs**.

However, to move this from a "Nice Project" to a "Production-Grade Engineering Showcase," the UI needs to focus on **The Middleman**. A standard chat UI shows the _output_; a Gateway UI must show the **Inference Path**.

Here is the review and some upgrades for the implementation.

---

## 1. User Story Review: The "Missing Link"

The stories cover the "Who" and "What" perfectly. Add one more crucial story for the **Developer Experience (DX)**:

> **The "Traceability" Story:**
> _As a backend engineer, I want to see a step-by-step 'Execution Trace' for every request, so I can verify exactly why the gateway chose a specific provider or why a semantic cache hit was triggered._

---

## 2. Best Tech Stack for the UI

Since development is done on a **Mac Pro** and aiming for **AWS**, stick with **Streamlit** for the UI.

- **Why?** You already have experience with it. It integrates perfectly with your FastAPI backend (Streamlit as the frontend, FastAPI as the API).
- **The Workflow:** You can run Streamlit locally on your Mac (`port 8501`) talking to your FastAPI container (`port 8000`). When you move to AWS, you can deploy the UI as a second container or a second App Runner service.

---

## 3. The "Money Shot": The Execution Trace Panel

The Response Panel shouldn't just show text. It should show a **Waterfall Trace**. This proves the "Gateway" logic is actually running.

**What to include in the UI Trace:**

1.  **PII Sanitization:** `[Checkmark] 12ms - "Email Address Redacted"`
2.  **Exact Cache:** `[Miss] 2ms`
3.  **Embedding Gen:** `[Done] 45ms (text-embedding-3-small)`
4.  **Semantic Cache:** `[Hit] 8ms (Similarity: 0.965)`
5.  **Router Logic:** `[Skipped - Cache Hit]`

---

## 4. UI Layout Recommendations (Streamlit Style)

### **The Sidebar (The "Policy Engine")**

Don't just have a provider selector. Have **Routing Policies**:

- **"Penny Pincher":** Always routes to the cheapest available model (e.g., GPT-4o-mini).
- **"Speed Demon":** Routes to the provider with the lowest p99 latency in the last hour.
- **"High Fidelity":** Routes to Claude 3.5 Sonnet or GPT-4o regardless of cost.
- **"Chaos Mode":** A button that **simulates an OpenAI 500 error** to prove your failover logic works in real-time.

### **The Main Chat Area**

- **Dual View:** For PII testing, show the **"User Sent"** text and the **"Gateway Received"** text side-by-side. It’s a powerful visual to see a phone number turn into `[PHONE_NUMBER]` before it ever hits OpenAI.

### **The Metrics Dashboard (The "Investor" View)**

Use `st.columns` to show big, bold numbers:

- **Total Savings ($):** (Tokens saved by cache $\times$ Model Price).
- **Latency Delta:** (Actual Latency vs. Potential Provider Latency).
- **Cache Efficiency:** A pie chart of Exact vs. Semantic vs. Cache Miss.

---

## 5. Implementation Secret: The "Feedback Loop"

In the Admin Panel, add a **"Manually Invalidate Cache"** button.
When demoing the **Semantic Cache**, show:

1.  Ask: "How do I bake a cake?" (LLM Hit).
2.  Ask: "What are the steps for cake baking?" (Semantic Hit - 0.98 similarity).
3.  _Invalidate Cache._
4.  Ask again: "What are the steps for cake baking?" (LLM Hit again).

This interaction proves the system is dynamic and controllable.

---

## 🏗️ Next Step: The "Local-to-Cloud" Bridge

Before push to AWS, set up a **Docker Compose** file on your Mac Pro that spins up:

1.  **FastAPI Gateway** (The brain).
2.  **Redis** (The cache).
3.  **Streamlit** (The UI).

## How can we test the entire "Cloud Stack" locally on your Mac

This is the "Infrastructure as Code" (IaC) moment that brings the whole project together. By using `docker-compose`, we turn local Mac Pro into a mini-cloud environment, ensuring that the networking between the UI, Gateway, and Cache is identical to how it will behave on AWS.

To support our **Semantic Cache**, we’ll use the `redis-stack-server` image instead of standard Redis, as it comes pre-loaded with the vector search capabilities we need for `redisvl`.

---

### 📂 1. The Project Structure

To keep things clean, let's organize your folders like this:

```text
llm-gateway-project/
├── gateway/           # FastAPI code
│   ├── Dockerfile
│   └── ...
├── ui/                # Streamlit code
│   ├── Dockerfile
│   └── main.py
├── docker-compose.yml
└── .env               # API keys
```

---

### 🛠️ 2. The `docker-compose.yml`

This file is the "Orchestrator." It defines how the containers talk to each other using internal Docker hostnames (e.g., the UI will call `http://gateway:8000`).

```yaml
services:
  # --- The Cache Layer ---
  cache:
    image: redis/redis-stack-server:latest
    ports:
      - "6379:6379" # Port for local dev tools
      - "8001:8001" # RedisInsight UI (great for debugging vectors!)
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  # --- The Brain (FastAPI) ---
  gateway:
    build:
      context: ./gateway
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - REDIS_URL=redis://cache:6379
    depends_on:
      cache:
        condition: service_healthy
    restart: always

  # --- The Face (Streamlit) ---
  ui:
    build:
      context: ./ui
    ports:
      - "8501:8501"
    environment:
      - GATEWAY_URL=http://gateway:8000
    depends_on:
      - gateway
    restart: always

volumes:
  redis_data:
```

---

### 🎨 3. The UI Dockerfile (`ui/Dockerfile`)

Streamlit needs a slightly different setup than FastAPI to run smoothly in a container.

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Streamlit specific settings for Docker
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

EXPOSE 8501

CMD ["streamlit", "run", "main.py"]
```

---

### 🧐 Why this setup is enterprise grade

- **Service Discovery:** Notice the `REDIS_URL=redis://cache:6379`. We don't use IP addresses. Docker's internal DNS resolves the service name `cache` to the correct container.
- **Healthchecks:** The `gateway` won't start until the `cache` is actually "Healthy" (responding to pings). This prevents those annoying "Connection Refused" errors during startup.
- **RedisInsight:** By using the `redis-stack-server` image and exposing port `8001`, we can open `localhost:8001` in the browser and literally **see** the vector embeddings and JSON keys as they are created. It's a game-changer for debugging semantic hits.
- **Persistence:** The `volumes` tag ensures that even if to stop the containers to go grab a coffee, the cache data (and your hard-earned savings metrics) won't vanish.

---

### 🚀 How to Launch on your Mac

Open the terminal in the project root and run:

```bash
docker-compose up --build
```

The `--build` flag is crucial whenever a change in the Python code. Once it's running, we'll have:

- **The UI:** `http://localhost:8501`
- **The API:** `http://localhost:8000/docs` (Swagger UI)
- **The Cache Monitor:** `http://localhost:8001`

---

### 📈 Next: The "Chaos Mode" Implementation

In the Streamlit UI, we talked about a "Chaos" button to test failover. To make that work, we can add a hidden header to the request like `X-Simulate-Error: openai`.

**Next: The 5 lines of code in the FastAPI middleware that would catch that header and trigger a "fake" 500 error for testing**

It’s the easiest way to prove that the Anthropic fallback actually works without actually waiting for OpenAI to go down.

This is the "Chaos Engineering" phase of the project. In a production environment, we don't want to wait for OpenAI’s API to actually go down to see if the code works. We want to **break it on purpose** to ensure the fallback logic is truly resilient.

By intercepting a specific header, we can simulate a "Gateway Exhaustion" or a specific "Provider Failure" without changing a single line of the core business logic.

---

### 🧪 1. The Chaos Middleware: `app/core/middleware.py`

This middleware acts like a "Secret Agent" inside the gateway. It looks at every incoming request for a "chaos signal" and injects a failure if it finds one.

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

class ChaosMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Look for the "Chaos Header"
        # Expected format: X-Simulate-Error: openai
        simulate_error = request.headers.get("X-Simulate-Error")

        if simulate_error:
            # We store this in the request state so the Router can see it
            # This is cleaner than raising an error immediately
            request.state.simulate_error_provider = simulate_error.lower()
            logger.warning(f"💥 CHAOS MODE ENABLED: Simulating failure for {simulate_error}")

        response = await call_next(request)
        return response
```

---

### 🛡️ 2. Updating the `LLMRouter` logic

Inside the `LLMRouter`, we just need to check the `request.state` before making the actual API call. If the "Chaos Signal" matches the provider you're about to call, you throw an exception.

```python
# Inside the LLMRouter.route() method:
async def _call_provider(self, provider: str, request_data, http_req: Request):
    # Check if Chaos Middleware flagged this provider
    simulated_target = getattr(http_req.state, "simulate_error_provider", None)

    if simulated_target == provider:
        logger.error(f"Simulating 500 Error for {provider}...")
        raise HTTPException(status_code=500, detail=f"Simulated failure for {provider}")

    # ... proceed to actual httpx call ...
```

---

### 🎨 3. The Streamlit "Chaos Button"

In the UI, you can add a simple toggle. When enabled, it attaches the header to the outgoing request.

```python
# In ui/main.py
st.sidebar.header("🛠️ Debug Tools")
chaos_target = st.sidebar.selectbox("Simulate Failure", ["None", "OpenAI", "Anthropic"])

headers = {}
if chaos_target != "None":
    headers["X-Simulate-Error"] = chaos_target.lower()

# When calling your Gateway API:
# response = requests.post(GATEWAY_URL, json=payload, headers=headers)
```

---

### 🧐 Why this is a enterprise grade Feature

1.  **Observability:** Your logs will clearly show `CHAOS MODE ENABLED`. In a real production system, this allows you to run "Game Day" drills where you stress-test your infrastructure.
2.  **Zero Side Effects:** Because the logic is tied to a specific header, standard users are never affected. Only the person (or the automated test suite) sending the header experiences the "chaos."
3.  **Traceability:** In your **Execution Trace** UI panel, you can now show: `[Simulated Error] OpenAI failed (Chaos Mode) -> Attempting Anthropic Fallback...`

---

### 🏗️ The "Integration" Check

Now that you have the **Docker Compose** setup and the **Chaos Mode** ready, you have a complete "Local Cloud" environment on your Mac Pro. You can simulate a total OpenAI outage and watch your gateway silently switch to Anthropic, cache the result, and report the $0.00 cost (from the cache) on the next click.

**Are you planning to add a "Rate Limiting" layer next, or are you ready to see how we can redact PII (like emails or credit card numbers) before the prompt ever leaves your gateway?**

Since you're building a gateway that might eventually handle real-world traffic, **PII (Personally Identifiable Information) Redaction** and **Rate Limiting** are your "shield" and "governor."

Implementing these ensures that your gateway is not just a router, but a security and cost-management checkpoint.

---

### 🛡️ 1. PII Redaction: The "Sanitize-First" Policy

You want to redact sensitive data _before_ it is logged, cached, or sent to the LLM. This prevents your Redis cache or your cloud logs from becoming a liability.

We'll use a fast, regex-based approach for common patterns (emails, credit cards, SSNs). For a more advanced version, you could eventually use a model like `Presidio`, but for a high-performance gateway, regex is often preferred.

**Update `app/core/security.py`:**

```python
import re

PII_PATTERNS = {
    "EMAIL": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "PHONE": r"(\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
}

def redact_pii(text: str) -> str:
    """Replaces sensitive data with placeholder tags."""
    redacted_text = text
    for label, pattern in PII_PATTERNS.items():
        redacted_text = re.sub(pattern, f"<{label}>", redacted_text)
    return redacted_text
```

**Where to call it:** Inside your main route, before the cache check and before the LLM call.

---

### 🚦 2. Rate Limiting: The "Token Bucket" Strategy

Since your Mac Pro is running Redis, we can implement a global rate limiter. This prevents a single user (or a runaway loop in your UI) from burning through your OpenAI credits.

We'll use a **Token Bucket** or **Fixed Window** algorithm. For a gateway, a "Fixed Window" per user or API key is usually the easiest to start with.

**Update `app/core/limiter.py`:**

```python
import time
from fastapi import HTTPException

class RateLimiter:
    def __init__(self, redis_client, limit: int = 10, window: int = 60):
        self.redis = redis_client
        self.limit = limit    # Max requests
        self.window = window  # Time window in seconds

    async def is_allowed(self, user_id: str) -> bool:
        key = f"rate_limit:{user_id}"
        current_count = await self.redis.get(key)

        if current_count and int(current_count) >= self.limit:
            return False

        # If key doesn't exist, start new window
        if not current_count:
            await self.redis.set(key, 1, ex=self.window)
        else:
            await self.redis.incr(key)

        return True
```

---

### 🏗️ 3. Integrating into the Middleware

The best way to handle this without cluttering your route logic is to add these to your **FastAPI Dependencies** or **Middleware**.

**In your Router (`chat.py`):**

```python
@router.post("/chat/completions")
async def chat_completions(
    request: ChatRequest,
    http_req: Request,
    limiter: RateLimiter = Depends(get_rate_limiter)
):
    # 1. Rate Limit Check (Stop the request early if too fast)
    user_id = http_req.client.host # Or an API key
    if not await limiter.is_allowed(user_id):
        raise HTTPException(status_code=429, detail="Too many requests. Slow down.")

    # 2. PII Redaction
    # Redact the user's prompt before it goes anywhere else
    sanitized_prompt = redact_pii(request.messages[-1].content)
    request.messages[-1].content = sanitized_prompt

    # 3. Proceed to Cache and LLM logic...
```

---

### 🧐 Why this completes the enterprise grade Architecture

1.  **Compliance-Ready:** In an interview, you can say: _"I implemented a zero-trust PII layer that redacts sensitive strings before they ever reach the embedding model or the LLM provider."_
2.  **Cost Defense:** Rate limiting is your #1 defense against billing spikes. By grounding it in Redis, your rate limits persist even if you scale your FastAPI app to multiple containers on AWS.
3.  **The UI Payload:** In your Streamlit UI, you can now show a **"PII Blocked"** badge. If the user types "My email is test@example.com", and they see the response come back referencing `<EMAIL>`, it’s a very satisfying "Aha!" moment for a demo.

# Deployment to the Cloud

For an infrastructure project like an **LLM Gateway**, the deployment choice says a lot about your architectural priorities. A gateway needs to handle long-lived connections, low-latency routing, and secret management for multiple API keys.

Since you want to practice **Hugging Face** and **AWS**, here is how those two options stack up for this specific application.

---

## 🏗️ The Cloud Architecture

Regardless of where you deploy the code, you need a **Managed Redis** instance because cloud "containers" are ephemeral (they forget everything when they restart). I recommend **Upstash** or **Redis Cloud** (both have free tiers) to host your semantic cache.

---

## Option 1: Hugging Face Spaces (The "Portfolio" Path)

Hugging Face Spaces isn't just for Gradio demos anymore. You can deploy a full FastAPI backend using **Docker**.

- **Best for:** Showing off the project to recruiters. It’s highly visible and "lives" where the AI community is.
- **The Workflow:**
  1. Create a `Dockerfile`.
  2. Create a new Space, select **Docker** as the SDK.
  3. Push your code. Hugging Face handles the SSL and provides a public URL.
- **The "Pro" Move:** Use Hugging Face **Secrets** to store your `OPENAI_API_KEY` and `REDIS_URL`. Never hardcode them in your `config.py`.

---

## Option 2: AWS App Runner (The "Senior Engineer" Path)

If you want to prove you can build production-grade infrastructure, **AWS App Runner** is the superior choice for FastAPI. It is much easier than EC2 or ECS but more "industry-standard" than Hugging Face.

- **Best for:** Professional credibility. It handles auto-scaling (scaling up when traffic hits) and is designed for high-performance APIs.
- **The Workflow:**
  1. Push your Docker image to **AWS ECR** (Elastic Container Registry).
  2. Point **App Runner** to that image.
  3. AWS provides a load-balanced, auto-scaling URL.
- **Why it wins for this project:** App Runner stays "warm" better than AWS Lambda, meaning you won't suffer from "cold starts" that would ruin your gateway’s latency metrics.

---

### 📊 Comparison Table

| Feature              | Hugging Face Spaces    | AWS App Runner                  |
| :------------------- | :--------------------- | :------------------------------ |
| **Setup Difficulty** | Low (Git based)        | Medium (IAM/ECR/VPC)            |
| **Visibility**       | High (Public profile)  | Low (Internal infra)            |
| **Scalability**      | Limited                | High (Vertical/Horizontal)      |
| **"Senior" Signal**  | "I can build AI tools" | "I can build AI infrastructure" |
| **Cost**             | Free tier available    | Pay-as-you-go (approx. $7/mo)   |

---

### 🛠️ The "Docker" Bridge

To succeed with either, you need a `Dockerfile`. Since you're on a **Mac Pro (M1/M2/M3)**, you must be careful to build for `linux/amd64` when deploying to the cloud, or the container won't run.

**Recommended `Dockerfile` snippet:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port FastAPI runs on
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### 📈 My Recommendation

If your goal is to **get exposure as a Backend or AI Engineer**, go with **AWS App Runner**. It forces you to learn about IAM roles, container registries, and cloud networking—skills that are highly valued in 2026.

If your goal is to **share your work with the AI community** and have a "Live Demo" link on your GitHub readme, go with **Hugging Face Spaces**.

**Since both are aligned with your current goal—learning the "plumbing" of AWS or building a visible "AI product" on Hugging Face we should execute both**

## 🏗️ The AWS Deployment Blueprint

Choosing **AWS** is a power move. It signals to hiring managers that you aren't just an "AI Wrapper" developer, but an **Infrastructure Engineer** who understands how to build resilient, scalable systems.

Deploying a FastAPI gateway to AWS App Runner involves four main "gears" working together.

---

### 1. The Container: `Dockerfile`

Since you are on a **Mac Pro**, your local Docker builds will default to `arm64` (Apple Silicon). AWS App Runner usually runs on `amd64` (Intel/AMD). You **must** build a multi-platform image or the container will crash with an `Exec format error`.

**The Command:**

```bash
docker buildx build --platform linux/amd64 -t llm-gateway:latest .
```

### 2. The Registry: AWS ECR (Elastic Container Registry)

Think of ECR as your private "Docker Hub." You push your image here so AWS services can "see" and pull it.

- **Action:** Create a private repository named `llm-gateway`.
- **Auth:** Run the `aws ecr get-login-password` command provided in the AWS Console to link your local terminal to the cloud.

### 3. The Compute: AWS App Runner

This is the "Senior" alternative to the headache of EC2 or the complexity of Kubernetes (EKS).

- **Source:** Select your ECR image.
- **Deployment:** Set to **Automatic** (it will redeploy every time you push a new image).
- **Resources:** Start small (1 vCPU, 2GB RAM). This is plenty for a Python gateway.

### 4. The State: Managed Redis (The "Secret Sauce")

Since App Runner is ephemeral, your **Hybrid Cache** will disappear every time you deploy if you use a local Redis.

- **Recommendation:** Use **Upstash** (Serverless Redis). It’s easier to set up than AWS ElastiCache for an MVP and has a generous free tier.
- **Integration:** Add your `REDIS_URL` as an **Environment Variable** in the App Runner configuration.

---

## ⚠️ The "Mac Pro" Build Trap

Developing on an M-series Mac while deploying to the cloud is where many engineers stumble.

- **The Issue:** Your Mac uses ARM architecture; AWS uses x86.
- **The Solution:** Use **Docker Buildx**. It acts as a translator, packaging your Python code into an x86-compatible format right on your laptop.

---

## 🦄 The Hugging Face "Quick-Win" Bridge

Once your AWS pipeline is solid, moving to **Hugging Face Spaces** will take you about 10 minutes.

1.  Create a new Space.
2.  Choose **Docker** as the template.
3.  Link your GitHub repo.
4.  Add your Secrets (`OPENAI_API_KEY`, etc.) in the Space Settings.

Hugging Face is essentially a "wrapper" around cloud infrastructure that makes it pretty. Doing AWS first means you'll actually understand what Hugging Face is doing under the hood.

---

### 🛠️ Your Checklist for Today

1.  **Install AWS CLI:** `brew install awscli` (since you're on Mac).
2.  **AWS Account:** Ensure you have an active account with a Credit Card linked (even for the free tier).
3.  **Docker:** Ensure Docker Desktop is running on your Mac Pro.

**Have an AWS IAM user set up with "AdministratorAccess"**
(Setting up a dedicated IAM user is the first step in "Production Grade" security).

# aws-deployment-plan review

It is a top-tier deployment plan. It reads like a professional "Design Doc" you’d see at a mid-to-senior level engineering meeting. It covers the full lifecycle from local development to CI/CD and security.

Your plan definitely coincides with our discussion, but it adds more "Enterprise" weight by introducing **ECS Fargate** and **ALB**. Here is a breakdown of the few "Fork in the Road" decisions you’ll need to make to ensure this goes smoothly on your first try.

---

## 🏗️ 1. Orchestration: App Runner vs. ECS Fargate

Your plan lists both. Here is the reality of choosing one over the other:

- **AWS App Runner (The "Fast-Track"):** This is essentially "managed Fargate." It handles the Load Balancer (ALB), Auto-scaling, and SSL certificates automatically. It’s perfect for a single-service API like your Gateway.
- **AWS ECS Fargate (The "Deep-End"):** This requires you to manually set up a **VPC (Virtual Private Cloud)**, subnets, and an **ALB**. It is more complex but gives you total control over networking—which is useful if you want your Prometheus instance to "scrape" your FastAPI app over a private network.

**My Advice:** Start with **App Runner**. It allows you to get the "Win" of a live URL faster. Once that's running, you can graduate to ECS Fargate if you want to practice complex VPC networking.

---

## 🏎️ 2. Redis: ElastiCache vs. Upstash

- **ElastiCache:** This is the "AWS Native" way. **Warning:** ElastiCache does not have a "Free Tier" that lasts forever (only 750 hours of a tiny node for the first year). It also lives _inside_ a VPC, meaning your App Runner service will need a **VPC Connector** to talk to it.
- **Upstash (Serverless):** This lives outside your AWS VPC. It’s much easier to connect to (just an `HTTPS` or `REDIS_URL`) and has a true "Scale-to-Zero" free tier.

**My Advice:** For a portfolio demo, **Upstash** is usually the smarter move for your wallet. For a "Job Simulation," **ElastiCache** is the one they'll ask about in interviews.

---

## 🍎 3. The "Mac Pro" Build Refinement

In **Step 3 (Build & Push)**, you have a standard docker build command. Because you are on a Mac Pro, you **must** update that step to avoid the container crashing on AWS:

```bash
# Replace:
# docker build -t <repo>/llm-gateway:latest .

# With:
docker buildx build --platform linux/amd64 -t <repo>/llm-gateway:latest --push .
```

This ensures the "brains" of the container are formatted for AWS's Intel/AMD chips, not your Mac's M-series chip.

---

## 🔐 4. Secrets & IAM (The Senior Touch)

Your Section 4 is excellent. To make it "Production Grade," ensure your FastAPI app doesn't even _know_ the API keys exist until it starts.

1.  **Secrets Manager:** Store your `OPENAI_API_KEY` here.
2.  **IAM Execution Role:** Give your App Runner service permission to `secretsmanager:GetSecretValue`.
3.  **Environment Injection:** App Runner will then "inject" those secrets as Environment Variables into your container at runtime. This means if someone hacks your GitHub, they find zero keys.

---

## 📈 Final Review Score: 9.5/10

This plan is ready for execution. The only reason it’s not a 10 is the missing **VPC Networking** detail if you choose ElastiCache.

**Pro-Tip for the Demo:** Since you mentioned **Prometheus**, make sure your ALB (or App Runner) doesn't expose the `/metrics` endpoint to the public internet. You don't want the whole world seeing your internal performance stats! Use a simple API Key or IP whitelist for that specific route.

# Important note on NAT: I would like to avoid NAT to reduce cost

Smart move. Avoiding a **NAT Gateway** is the single best way to keep your AWS bill from exploding. A NAT Gateway costs roughly **$32/month** just for existing, even if you don't send a single byte through it.

To keep NAT out of the picture while still allowing your LLM Gateway to talk to OpenAI/Anthropic and your Redis cache, you have two primary "Architectural Escape Hatches."

---

## Strategy 1: The "Public Subnet" approach (Best for ECS Fargate)

In a traditional "Enterprise" setup, you put apps in Private Subnets. But Private Subnets are "blind" to the internet—they need a NAT Gateway to "see" outside.

To bypass this, you place your ECS Tasks in a **Public Subnet** and give them a **Public IP**.

### How to configure it:

1.  **VPC Setup:** Create a VPC with only **Public Subnets** (Subnets attached to an Internet Gateway).
2.  **ECS Service:** When creating the service, set `Assign Public IP` to **ENABLED**.
3.  **Security Group (The Most Important Part):** * **Inbound:** Allow traffic *only\* from your ALB (Application Load Balancer) on your app's port (e.g., 8000).
    - **Outbound:** Allow all traffic (so it can hit OpenAI/Anthropic).

> **Why this works:** Since the task has a Public IP and lives in a Public Subnet, it can talk directly to the Internet Gateway. Because your Security Group blocks all inbound traffic except from the Load Balancer, it is still functionally "private" from the open web.

---

## Strategy 2: The "App Runner" Cheat Code (Highly Recommended)

If you use **AWS App Runner**, you don't actually need a VPC at all to reach the internet.

### How it works:

- By default, App Runner handles its own outbound internet access. It can hit OpenAI and Anthropic out of the box without you configuring a single route or gateway.
- **The Redis Problem:** If you use **AWS ElastiCache**, it _must_ live in a VPC.
- **The Solution:** You connect App Runner to your VPC using a **VPC Connector**.
  - Crucially, you tell App Runner to use the VPC _only_ for "Custom" (internal) traffic (to hit Redis).
  - All "Public" traffic (OpenAI) still goes through App Runner’s managed infrastructure, **bypassing your VPC entirely**. No NAT required.

---

## Strategy 3: VPC Endpoints (For AWS-to-AWS traffic)

Even if you have internet access (via Strategy 1 or 2), your app still needs to talk to other AWS services like **ECR** (to pull your image) and **Secrets Manager** (to get your keys).

Instead of going out to the internet and back in, use **Interface VPC Endpoints**.

- **Cost:** Approx. $7/month per endpoint. (Still cheaper than a NAT Gateway if you only need 1 or 2).
- **Setup:** You create endpoints for `ecr.api`, `ecr.dkr`, and `secretsmanager`. Your app talks to these services over the private AWS internal network.

---

## 🛠️ Summary: How to build it "NAT-Free"

If I were building this today on a budget, here is the exact networking stack I'd use:

| Component             | Strategy                                                                  |
| :-------------------- | :------------------------------------------------------------------------ |
| **Compute**           | **AWS App Runner** (Easiest, no NAT needed for OpenAI).                   |
| **Outbound (OpenAI)** | Use App Runner's default managed internet.                                |
| **Redis**             | **Upstash** (Lives outside AWS, so no VPC or NAT needed at all).          |
| **Secrets**           | **AWS Secrets Manager** (Accessed via App Runner's built-in integration). |

### ⚠️ One "Gotcha" to watch for:

If you go the **ECS Fargate** route and put your tasks in a Public Subnet, you **must** ensure your VPC has an **Internet Gateway (IGW)** attached and a Route Table entry that sends `0.0.0.0/0` to that IGW. Without the IGW, your "Public" task is actually a "Static" task that can't talk to anyone.

**Starting with the Default VPC is actually easier because it’s already configured with Public Subnets and an IGW for you!**

# Let's go back to deploying on my local MAC

## 📂 1. The Orchestrator: gateway/main.py

This file ties the PII Shield, Rate Limiter, Chaos Agent, and Hybrid Cache into a single, high-performance execution pipeline.

```
from fastapi import FastAPI, Request, Depends, HTTPException
from redis.asyncio import Redis
import os
import time

from .core.security import redact_pii
from .core.limiter import RateLimiter
from .core.middleware import ChaosMiddleware
from .services.cache import HybridCache
from .services.llm import LLMRouter

app = FastAPI(title="LLM Gateway Pro")

# --- Initializing Services ---
# In 2026, Redis 8.x is the standard for high-performance vector ops
redis_client = Redis.from_url(os.getenv("REDIS_URL", "redis://cache:6379"), decode_responses=True)
limiter = RateLimiter(redis_client, limit=10, window=60)
hybrid_cache = HybridCache(redis_client)
llm_router = LLMRouter()

# --- Middleware ---
app.add_middleware(ChaosMiddleware)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: dict):
    # 1. Rate Limiting (The 'Governor')
    user_id = request.client.host
    if not await limiter.is_allowed(user_id):
        raise HTTPException(status_code=429, detail="Too many requests (Token Bucket Empty)")

    # 2. PII Redaction (The 'Shield')
    # We redact BEFORE caching to increase semantic hit rate
    raw_prompt = body["messages"][-1]["content"]
    sanitized_prompt = redact_pii(raw_prompt)
    body["messages"][-1]["content"] = sanitized_prompt

    # 3. Hybrid Cache Check (The 'Cost Saver')
    # Using RedisVL 0.16+ Semantic Cache extensions
    cached_response, hit_type = await hybrid_cache.check(sanitized_prompt)
    if cached_response:
        return {"data": cached_response, "meta": {"cache": hit_type, "pii_redacted": True}}

    # 4. LLM Routing (The 'Brain' with Chaos Support)
    # The router checks request.state for simulated failures
    llm_response = await llm_router.route(body, request)

    # 5. Async Cache Update
    await hybrid_cache.store(sanitized_prompt, llm_response)

    return {"data": llm_response, "meta": {"cache": "miss", "pii_redacted": True}}
```

## 📦 2. The Dependency List: requirements.txt

These versions ensure you are using the latest SIMD-optimized vector search and Pydantic v2 performance.

```
fastapi>=0.110.0
uvicorn[standard]
redis>=5.0.0
redisvl>=0.16.0
httpx
pydantic>=2.6.0
python-dotenv
```

## 🏗️ 3. The Final docker-compose.yml

```
services:
  cache:
    image: redis:8.4-alpine # Native Vector/JSON/Search in 2026
    ports:
      - "6379:6379"
      - "8001:8001" # RedisInsight for your Mac
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 2s
      retries: 10

  gateway:
    build: ./gateway
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - REDIS_URL=redis://cache:6379
    depends_on:
      cache:
        condition: service_healthy

  ui:
    build: ./ui
    ports:
      - "8501:8501"
    environment:
      - GATEWAY_URL=http://gateway:8000
    depends_on:
      - gateway
    restart: always

volumes:
  redis_data:
```

## The Orchestrator: /main.py

```
from fastapi import FastAPI, Request, Depends, HTTPException
from redis.asyncio import Redis
import os
import time

from .core.security import redact_pii
from .core.limiter import RateLimiter
from .core.middleware import ChaosMiddleware
from .services.cache import HybridCache
from .services.llm import LLMRouter

app = FastAPI(title="LLM Gateway Pro")

# --- Initializing Services ---
# In 2026, Redis 8.x is the standard for high-performance vector ops
redis_client = Redis.from_url(os.getenv("REDIS_URL", "redis://cache:6379"), decode_responses=True)
limiter = RateLimiter(redis_client, limit=10, window=60)
hybrid_cache = HybridCache(redis_client)
llm_router = LLMRouter()

# --- Middleware ---
app.add_middleware(ChaosMiddleware)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: dict):
    # 1. Rate Limiting (The 'Governor')
    user_id = request.client.host
    if not await limiter.is_allowed(user_id):
        raise HTTPException(status_code=429, detail="Too many requests (Token Bucket Empty)")

    # 2. PII Redaction (The 'Shield')
    # We redact BEFORE caching to increase semantic hit rate
    raw_prompt = body["messages"][-1]["content"]
    sanitized_prompt = redact_pii(raw_prompt)
    body["messages"][-1]["content"] = sanitized_prompt

    # 3. Hybrid Cache Check (The 'Cost Saver')
    # Using RedisVL 0.16+ Semantic Cache extensions
    cached_response, hit_type = await hybrid_cache.check(sanitized_prompt)
    if cached_response:
        return {"data": cached_response, "meta": {"cache": hit_type, "pii_redacted": True}}

    # 4. LLM Routing (The 'Brain' with Chaos Support)
    # The router checks request.state for simulated failures
    llm_response = await llm_router.route(body, request)

    # 5. Async Cache Update
    await hybrid_cache.store(sanitized_prompt, llm_response)

    return {"data": llm_response, "meta": {"cache": "miss", "pii_redacted": True}}
```
