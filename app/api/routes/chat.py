from asyncio.log import logger

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.models.chat import ChatRequest, ChatResponse
from app.services.profiler import Profiler
from app.services.pricing import calculate_request_cost
from app.services.router import LLMRouter
from app.core.http import get_http_client # Shared connection pool

router = APIRouter(prefix="/v1")

@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: ChatRequest,
    http_req: Request,
    response: Response,
    http_client = Depends(get_http_client)
):
    # 1. Initialize your Stateful Profiler (The Stopwatch)
    p = Profiler()
    p.start()

    try:
        # 2. Extract Routing Hints
        provider_hint = http_req.headers.get("X-LLM-Provider")
        if provider_hint:
            request.provider_hint = provider_hint

        # 3. Initialize the Resilient Router
        # (Pass the shared http_client for connection pooling)
        config = {"default_provider": "openai", "enable_fallback": True}
        llm_router = LLMRouter(config, http_client)

        # 4. Execute the Request
        # The router handles 4xx/5xx logic and fallbacks internally
        llm_response = await llm_router.route(request)

        # 5. Stop the Clock
        p.end()

        # 6. Calculate the "Receipt" (Cost & Metrics)
        provider_used = llm_response.metrics.provider_used
        model_used = llm_response.metrics.model_used

        input_tokens = llm_response.usage.get("prompt_tokens", 0)
        output_tokens = llm_response.usage.get("completion_tokens", 0)

        cost = calculate_request_cost(
            provider_used,
            model_used,
            input_tokens,
            output_tokens
        )

        # 7. Use your Profiler helper to build the final Metrics object
        # This keeps the route logic clean and standardized
        final_metrics = p.get_metrics(
            provider=provider_used,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost
        )

        # Update the response object with our finalized telemetry
        llm_response.metrics = final_metrics

        # 8. Inject Telemetry into Headers for Observability
        # This allows external monitors to see performance without parsing JSON
        response.headers["X-Gateway-Metrics"] = final_metrics.json()

        return llm_response

    except Exception as e:
        # If the router exhausts all fallbacks, we report the final failure
        logger.error(f"Gateway Exhaustion: {str(e)}")
        raise HTTPException(status_code=500, detail="All LLM providers unavailable.")

    finally:
        # 9. Stop the Clock
        p.end()
