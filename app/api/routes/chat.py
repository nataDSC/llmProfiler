from fastapi.responses import JSONResponse
from app.middleware.pii import redact_all_strings

import os
from asyncio.log import logger

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.models.chat import ChatRequest, ChatResponse
from app.services.profiler import Profiler
from app.services.pricing import calculate_request_cost
from app.services.router import LLMRouter
from app.core.http import get_http_client # Shared connection pool



router = APIRouter()  # Remove prefix here

# Admin endpoint to invalidate cache (must be after router is defined)
@router.post("/admin/invalidate_cache")
async def invalidate_cache():
    from app.services.cache import HybridCache
    import os
    cache = HybridCache(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"))
    await cache.invalidate_all()
    return JSONResponse({"status": "ok", "detail": "Cache invalidated"})


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(
    request: ChatRequest,
    http_req: Request,
    response: Response,
    http_client = Depends(get_http_client)
):


    # 1. Initialize your Stateful Profiler (The Stopwatch)
    from app.models.chat import GatewayMetrics, ChatResponse
    p = Profiler()
    p.start()
    trace_steps = []
    try:
        from app.core.config import settings
        from app.services.cache import HybridCache
        from app.services.embedding import EmbeddingService
        import asyncio

        # 2. Extract Routing Hints and Chaos Mode
        provider_hint = http_req.headers.get("X-LLM-Provider")
        if provider_hint:
            request.provider_hint = provider_hint
        simulate_error = http_req.headers.get("X-Simulate-Error")
        if simulate_error:
            request.simulate_error = simulate_error.lower()

        # 2.1. Check for cache disable and semantic threshold
        disable_cache = http_req.headers.get("X-Disable-Cache", "false").lower() == "true"
        semantic_threshold = http_req.headers.get("X-Semantic-Threshold")
        try:
            semantic_threshold = float(semantic_threshold) if semantic_threshold is not None else None
        except Exception:
            semantic_threshold = None

        # 3. Hybrid Cache Orchestration (fail open if Redis is unavailable)
        cache = None
        try:
            cache = HybridCache(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"))
        except Exception as e:
            logger.error(f"HybridCache unavailable, proceeding without cache: {e}")
        embedding_service = EmbeddingService(dims=1536)  # TODO: make dims configurable
        prompt = request.messages[-1].content if request.messages else ""

        # 3.1. Check Exact Match (with stale-while-revalidate)
        async def refresh_cache(prompt, cached_data):
            # This will run in the background for stale cache entries
            try:
                logger.info(f"Refreshing stale cache for prompt: {prompt}")
                # Re-run LLM and update cache
                new_vector = await embedding_service.get_vector(prompt)
                new_llm_response = await llm_router.route(request)
                await cache.store(prompt, new_llm_response.model_dump(), new_vector)
            except Exception as e:
                logger.error(f"Background cache refresh failed: {e}")

        if cache and not disable_cache:
            try:
                trace_steps.append("Checked cache for exact match")
                cached_hit, cache_type = await cache.check(prompt, trigger_refresh=lambda p, d: asyncio.create_task(refresh_cache(p, d)))
                if cached_hit:
                    from app.models.chat import GatewayMetrics, ChatResponse
                    p.end()
                    metrics = p.get_metrics(
                        provider=f"cache_{cache_type}",
                        model=request.model,
                        input_tokens=0,
                        output_tokens=0,
                        cost=0.0
                    )
                    # Calculate cache stats for UI
                    metrics.savings = cached_hit["response"].get("metrics", {}).get("estimated_cost_usd", 0.0)
                    metrics.latency_delta = cached_hit["response"].get("metrics", {}).get("total_latency_ms", 0.0)
                    metrics.cache_efficiency = 100
                    resp_data = dict(cached_hit["response"])
                    resp_data.pop("metrics", None)
                    # Redact PII in the outgoing response
                    redacted_resp_data = redact_all_strings(resp_data)
                    resp_obj = ChatResponse(**redacted_resp_data, metrics=metrics)
                    response.headers["X-Gateway-Metrics"] = metrics.model_dump_json()
                    logger.info(f"Cache {cache_type} hit for prompt. Returning cached response.")
                    trace_steps.append(f"Cache {cache_type} hit for prompt. Returning cached response.")
                    resp_obj.trace = " | ".join(trace_steps)
                    return resp_obj
            except Exception as e:
                logger.error(f"Cache exact match failed open: {e}")

        # 3.2. Get Embedding (only if no exact match)
        try:
            trace_steps.append("Getting embedding for prompt (semantic cache path)")
            logger.info("[CACHE] No exact cache hit, attempting semantic cache match (embedding generation)")
            vector = await embedding_service.get_vector(prompt)
        except Exception as e:
            logger.error(f"Embedding service failed open: {e}")
            vector = None

        # 3.3. Check Semantic Match (with stale-while-revalidate)
        if cache and not disable_cache:
            try:
                if vector:
                    logger.info("[CACHE] Checking semantic cache for prompt (vector present)")
                    trace_steps.append("Checking semantic cache for prompt (vector present)")
                    cached_hit, cache_type = await cache.check(prompt, vector=vector, trigger_refresh=lambda p, d: asyncio.create_task(refresh_cache(p, d)), threshold=semantic_threshold)
                    # Always show the distance and threshold in the trace
                    distance = cached_hit.get("semantic_cache_distance") if cached_hit else None
                    threshold_used = semantic_threshold if semantic_threshold is not None else 0.12
                    if distance is not None:
                        trace_steps.append(f"Semantic cache distance: {distance:.4f} (threshold: {threshold_used})")
                        if distance < threshold_used:
                            trace_steps.append("Semantic cache HIT (distance < threshold)")
                        else:
                            trace_steps.append("Semantic cache MISS (distance >= threshold)")
                    else:
                        trace_steps.append("Semantic cache distance unavailable (no result or error)")
                    if cached_hit and distance is not None and distance < threshold_used:
                        trace_steps.append("Checked cache for semantic match")
                        from app.models.chat import GatewayMetrics, ChatResponse
                        p.end()
                        metrics = p.get_metrics(
                            provider=f"cache_{cache_type}",
                            model=request.model,
                            input_tokens=0,
                            output_tokens=0,
                            cost=0.0
                        )
                        # Calculate cache stats for UI
                        metrics.savings = cached_hit["response"].get("metrics", {}).get("estimated_cost_usd", 0.0)
                        metrics.latency_delta = cached_hit["response"].get("metrics", {}).get("total_latency_ms", 0.0)
                        metrics.cache_efficiency = 100
                        resp_data = dict(cached_hit["response"])
                        resp_data.pop("metrics", None)
                        # Redact PII in the outgoing response
                        redacted_resp_data = redact_all_strings(resp_data)
                        resp_obj = ChatResponse(**redacted_resp_data, metrics=metrics)
                        response.headers["X-Gateway-Metrics"] = metrics.model_dump_json()
                        logger.info(f"Cache semantic hit for prompt. Returning cached response.")
                        trace_steps.append(f"Cache {cache_type} semantic hit for prompt. Returning cached response.")
                        resp_obj.trace = " | ".join(trace_steps)
                        return resp_obj
            except Exception as e:
                logger.error(f"Cache semantic match failed open: {e}")

        # 4. Fallback to LLM
        config = {
            "default_provider": settings.default_provider,
            "enable_fallback": True,
            "providers": settings.providers
        }
        trace_steps.append("Routing to LLM provider")
        llm_router = LLMRouter(config, http_client)
        llm_response = await llm_router.route(request)
        p.end()
        # Add the provider actually used to the trace
        provider_used = getattr(llm_response.metrics, "provider_used", None)
        if provider_used:
            trace_steps.append(provider_used)
        # Save the original LLM response content for UI display
        llm_response_dict = llm_response.model_dump()
        # Save the original content
        if "choices" in llm_response_dict and llm_response_dict["choices"]:
            original_content = llm_response_dict["choices"][0]["message"].get("content", "")
        else:
            original_content = ""
        # Redact ONLY the LLM output field
        redacted_content = redact_all_strings(original_content)
        # Insert both redacted and original content into the response
        llm_response_dict["choices"][0]["message"]["original_content"] = original_content
        llm_response_dict["choices"][0]["message"]["content"] = redacted_content
        # Add redacted prompt for UI display
        user_prompt = request.messages[-1].content if request.messages else ""
        llm_response_dict["redacted_prompt"] = redact_all_strings(user_prompt)
        llm_response = ChatResponse(**llm_response_dict)
        llm_response.trace = " | ".join(trace_steps)


        # 5. Store result in Cache (synchronously, not background)
        if cache and not disable_cache:
            try:
                logger.info("[CACHE] Storing result in cache")
                trace_steps.append("Storing result in cache")
                await cache.store(prompt, llm_response.model_dump(), vector)
            except Exception as e:
                logger.error(f"Cache store failed open: {e}")

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
        final_metrics = p.get_metrics(
            provider=provider_used,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost
        )
        # For LLM calls, set cache stats to 0
        final_metrics.savings = 0.0
        final_metrics.latency_delta = 0.0
        final_metrics.cache_efficiency = 0
        llm_response.metrics = final_metrics
        response.headers["X-Gateway-Metrics"] = final_metrics.model_dump_json()
        logger.info(f"Route: Injected telemetry into headers: {final_metrics.model_dump_json()}")
        return llm_response

        # 8. Inject Telemetry into Headers for Observability
        # This allows external monitors to see performance without parsing JSON
        response.headers["X-Gateway-Metrics"] = final_metrics.model_dump_json()
        # logger.info(f"Route: Injected telemetry into headers: {final_metrics.model_dump_json()}")

        return llm_response

    except Exception as e:
        # If the router exhausts all fallbacks, we report the final failure
        logger.error(f"Gateway Exhaustion: {str(e)}")
        raise HTTPException(status_code=500, detail="All LLM providers unavailable.")

    finally:
        # 9. Stop the Clock
        p.end()
