"""Qdrant vector store client — Phase 2 placeholder."""

from __future__ import annotations


class VectorStore:
    """Qdrant vector store for semantic paper search.

    Will be implemented in Phase 2 with:
    - Paper-level embeddings (title + abstract + method summary)
    - Method-level embeddings (core_idea + description)
    - Claim-level embeddings (key_evidence claims)
    - Hybrid retrieval: 0.6*semantic + 0.3*BM25 + 0.1*citation_weight
    """

    async def connect(self) -> None:
        raise NotImplementedError("Phase 2")

    async def upsert(self, collection: str, vectors: list[dict]) -> None:
        raise NotImplementedError("Phase 2")

    async def search(self, collection: str, query_vector: list[float], limit: int = 10) -> list[dict]:
        raise NotImplementedError("Phase 2")
