from app.core.config import settings
from typing import Optional

def get_model_pricing(provider: str, model: str) -> Optional[dict]:
    providers = settings.pricing.get("providers", {})
    provider_pricing = providers.get(provider, {})
    # Use model alias if present
    model_key = settings.model_aliases.get(model, model)
    model_pricing = provider_pricing.get(model_key) or provider_pricing.get(model)
    if not model_pricing:
        return None
    # Normalize keys for test compatibility
    return {
        "input": model_pricing.get("input_cost_1m", 0),
        "output": model_pricing.get("output_cost_1m", 0)
    }

def calculate_request_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    # Get rates (using your existing logic)
    rates = get_model_pricing(provider, model)
    if not rates:
        return 0.0

    # Math: (Tokens / 1M) * Rate_Per_1M
    in_cost = (input_tokens / 1_000_000) * rates.get("input", 0)
    out_cost = (output_tokens / 1_000_000) * rates.get("output", 0)

    return in_cost + out_cost
