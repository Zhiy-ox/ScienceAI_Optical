"""Embedding service using OpenAI text-embedding-3-large."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from science_ai.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for papers, methods, and claims."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of 1536-dim vectors."""
        if not texts:
            return []

        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text."""
        results = await self.embed([text])
        return results[0]
