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
