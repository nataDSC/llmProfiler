from pydantic import BaseModel, Field
from typing import Dict

class ModelPricing(BaseModel):
    input: float
    output: float

class ProviderPricing(BaseModel):
    __root__: Dict[str, ModelPricing]

class PricingConfig(BaseModel):
    openai: ProviderPricing
    anthropic: ProviderPricing
