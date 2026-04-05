
import os
from app.core.config import settings
import openai

class EmbeddingService:
    def __init__(self, provider: str = None, dims: int = 1536):
        # Provider can be 'openai' or 'local'.
        self.provider = provider or os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        self.dims = dims
        if self.provider == "openai":
            self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        else:
            self.client = None  # Local model will be handled in get_vector

    async def get_vector(self, prompt: str) -> list[float]:
        if self.provider == "openai":
            resp = await self.client.embeddings.create(
                input=prompt,
                model="text-embedding-3-small"
            )
            return resp.data[0].embedding
        elif self.provider == "local":
            # TODO: Replace with actual local embedding model call
            # Example: from my_local_embedding import embed; return embed(prompt)
            raise NotImplementedError("Local embedding model not implemented yet.")
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")
