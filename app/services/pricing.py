from app.core.config import settings
from typing import Optional

def get_model_pricing(provider: str, model: str) -> Optional[dict]:
    provider_pricing = settings.pricing.get(provider, {})
    # Use model alias if present
    model_key = settings.model_aliases.get(model, model)
    return provider_pricing.get(model_key) or provider_pricing.get(model)
