import os
import yaml
from typing import Dict, Any

class Settings:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.default_provider = os.getenv("DEFAULT_PROVIDER", "openai")
        self.pricing_path = os.getenv("PRICING_PATH", "pricing.yaml")
        self.model_aliases = {
            # User-facing name : provider model name
            "claude-3-sonnet": "claude-3-5-sonnet-20240620",
            "claude-3-haiku": "claude-3-5-haiku-20240620",
        }
        self.providers = {
            "openai": {"api_key": self.openai_api_key},
            "anthropic": {"api_key": self.anthropic_api_key},
        }
        self.pricing = self._load_pricing()

    def _load_pricing(self) -> Dict[str, Any]:
        with open(self.pricing_path, "r") as f:
            return yaml.safe_load(f)

settings = Settings()
