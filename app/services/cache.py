import hashlib
import json
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from app.core.config import settings

class HybridCache:

    async def invalidate_all(self):
        """Clear all exact and semantic cache entries."""
        # Delete all keys with prefix 'exact:' (exact match cache)
        for key in self.client.scan_iter("exact:*"):
            self.client.delete(key)
        # Delete all keys with prefix 'cache:' (semantic cache)
        for key in self.client.scan_iter("cache:*"):
            self.client.delete(key)
        # Optionally clear the vector index
        try:
            self.index.drop()
            self.index.create(overwrite=True)
        except Exception:
            pass
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
        }, connection=redis_url)
        # Ensure index and client are ready
        if not hasattr(self.index, 'client') or self.index.client is None:
            self.index.create(overwrite=False)
        self.client = self.index.client

    def _get_hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    async def check(self, prompt: str, vector: list[float] = None, trigger_refresh=None):
        import logging
        logger = logging.getLogger("semantic_cache")
        import time
        from app.core.config import settings
        # --- Tier 1: Exact Match ---
        prompt_hash = self._get_hash(prompt)
        logger.info(f"[CACHE CHECK] prompt='{prompt}' hash={prompt_hash} vector_shape={len(vector) if vector is not None else None}")
        logger.info(f"[CACHE CHECK] Redis index exists: {hasattr(self, 'index') and hasattr(self.index, 'client') and self.index.client is not None}")
        exact_hit = self.client.get(f"exact:{prompt_hash}")
        if exact_hit:
            data = json.loads(exact_hit)
            cached_at = data.get("cached_at", 0)
            age = time.time() - cached_at
            if age < settings.cache_fresh_window:
                return data, "exact"
            elif age < settings.cache_stale_window:
                # Stale-while-revalidate: return, but trigger refresh
                if trigger_refresh:
                    trigger_refresh(prompt, data)
                return data, "exact_stale"
            else:
                return None, None

        # --- Tier 2: Semantic Match ---
        if vector:
            query = VectorQuery(
                vector=vector,
                vector_field_name="prompt_vector",
                return_fields=["response", "dist"],
                num_results=1
            )
            results = self.index.query(query)
            # Lowered threshold: 0.12 distance = 88% similarity (was 0.05)
            if results:
                import logging
                logger = logging.getLogger("semantic_cache")
                result0 = results[0]
                # Support both 'dist' and 'vector_distance' for Redis/redisvl compatibility
                distance = None
                if "dist" in result0:
                    try:
                        distance = float(result0["dist"])
                    except Exception as e:
                        logger.error(f"Could not parse 'dist' from semantic cache result: {result0}, error: {e}")
                        return None, None
                elif "vector_distance" in result0:
                    try:
                        distance = float(result0["vector_distance"])
                    except Exception as e:
                        logger.error(f"Could not parse 'vector_distance' from semantic cache result: {result0}, error: {e}")
                        return None, None
                else:
                    logger.warning(f"Semantic cache result missing both 'dist' and 'vector_distance' fields: {result0}")
                    return None, None
                logger.info(f"Semantic cache distance for prompt '{prompt}': {distance}")
                # Attach distance to data for trace/debug
                data = json.loads(result0["response"])
                data["semantic_cache_distance"] = distance
                cached_at = data.get("cached_at", 0)
                age = time.time() - cached_at
                if distance < 0.3:
                    if age < settings.cache_fresh_window:
                        return data, "semantic"
                    elif age < settings.cache_stale_window:
                        if trigger_refresh:
                            trigger_refresh(prompt, data)
                        return data, "semantic_stale"
                # If not within threshold or too old
                return None, None

        return None, None

    async def store(self, prompt: str, response: dict, vector: list[float], category: str = None):
        import logging
        logger = logging.getLogger("semantic_cache")
        """Stores result in both Exact and Semantic indexes, with category-based TTL and metadata."""
        import time
        from app.core.config import settings
        prompt_hash = self._get_hash(prompt)
        logger.info(f"[CACHE STORE] prompt='{prompt}' hash={prompt_hash} vector_shape={len(vector) if vector is not None else None}")
        logger.info(f"[CACHE STORE] Redis index exists: {hasattr(self, 'index') and hasattr(self.index, 'client') and self.index.client is not None}")
        # Ensure vector is a list of floats for JSON, bytes for RedisVL
        vector_list = [float(x) for x in vector] if vector is not None else None
        # Determine TTL
        category_ttls = getattr(settings, "cache_category_ttls", {})
        default_ttl = getattr(settings, "cache_ttl_seconds", 86400)
        ttl = category_ttls.get(category, default_ttl)
        if ttl == 0:
            return  # Do not cache volatile queries
        # Add cached_at metadata
        data = {"prompt": prompt, "response": response, "cached_at": time.time()}
        # Store Exact
        self.client.set(f"exact:{prompt_hash}", json.dumps(data), ex=ttl)
        # Store Semantic (vector as bytes)
        if vector_list is not None:
            logger.info(f"[CACHE STORE] Storing semantic vector for hash={prompt_hash} shape={len(vector_list)}")
            import numpy as np
            vector_bytes = np.array(vector_list, dtype=np.float32).tobytes()
            key = f"cache:{prompt_hash}"
            try:
                await self.index.load([{
                    "id": key,
                    "prompt_hash": prompt_hash,
                    "prompt_vector": vector_bytes,
                    "response": json.dumps(data)
                }])
                # Manually set expiry on the hash key
                self.index.client.expire(key, ttl)
            except Exception as e:
                try:
                    self.index.load([{
                        "id": key,
                        "prompt_hash": prompt_hash,
                        "prompt_vector": vector_bytes,
                        "response": json.dumps(data)
                    }])
                    self.index.client.expire(key, ttl)
                except Exception as e2:
                    pass
    