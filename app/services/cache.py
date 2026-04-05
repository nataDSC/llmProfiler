import hashlib
import json
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from app.core.config import settings

class HybridCache:
    def __init__(self, redis_url: str):
        self.index_name = "llm_cache"
        # 1. Exact Match uses standard Redis Key-Value
        # 2. Semantic Match uses Redis Search/Vector features
        self.index = SearchIndex.from_dict({
            "index": {"name": self.index_name, "prefix": "cache"},
            "fields": [
                {"name": "prompt_hash", "type": "tag"},
                {"name": "prompt_vector", "type": "vector", "attrs": {
                    "dims": 1536, "algorithm": "hnsw", "distance_metric": "cosine"
                }}
            ]
        })
        self.index.connect(redis_url)

    def _get_hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    async def check(self, prompt: str, vector: list[float] = None):
        # --- Tier 1: Exact Match ---
        prompt_hash = self._get_hash(prompt)
        exact_hit = await self.index.client.get(f"exact:{prompt_hash}")
        if exact_hit:
            return json.loads(exact_hit), "exact"

        # --- Tier 2: Semantic Match ---
        if vector:
            query = VectorQuery(
                vector=vector,
                vector_field_name="prompt_vector",
                return_fields=["response", "dist"],
                num_results=1
            )
            results = self.index.query(query)
            # Threshold: 0.05 distance = 95% similarity
            if results and float(results[0]["dist"]) < 0.05:
                return json.loads(results[0]["response"]), "semantic"

        return None, None

    async def store(self, prompt: str, response: str, vector: list[float]):
        """Stores result in both Exact and Semantic indexes."""
        prompt_hash = self._get_hash(prompt)
        data = {"prompt": prompt, "response": response}
        
        # Store Exact
        await self.index.client.set(f"exact:{prompt_hash}", json.dumps(data), ex=3600)
        
        # Store Semantic
        await self.index.load([{
            "prompt_hash": prompt_hash,
            "prompt_vector": vector,
            "response": json.dumps(data)
        }])
    