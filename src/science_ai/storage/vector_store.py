"""Qdrant vector store for semantic paper/method/claim search."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from science_ai.config import settings

logger = logging.getLogger(__name__)

# Collection names for the three embedding types from the architecture
PAPER_COLLECTION = "papers"
METHOD_COLLECTION = "methods"
CLAIM_COLLECTION = "claims"

ALL_COLLECTIONS = [PAPER_COLLECTION, METHOD_COLLECTION, CLAIM_COLLECTION]


class VectorStore:
    """Qdrant vector store with three embedding types:

    - papers: title + abstract + method summary → find semantically related papers
    - methods: core_idea + description → build method-problem matrix
    - claims: key_evidence claims → find supporting/contradicting papers
    """

    def __init__(self) -> None:
        self.client: AsyncQdrantClient | None = None
        self.dimension = settings.embedding_dimension

    async def connect(self) -> None:
        """Connect to Qdrant and ensure collections exist."""
        self.client = AsyncQdrantClient(url=settings.qdrant_url)
        await self._ensure_collections()

    async def close(self) -> None:
        if self.client:
            await self.client.close()

    async def _ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        existing = await self.client.get_collections()
        existing_names = {c.name for c in existing.collections}

        for name in ALL_COLLECTIONS:
            if name not in existing_names:
                await self.client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=self.dimension,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection: %s", name)

    # ---- Paper-level embeddings ----

    async def upsert_paper(
        self,
        paper_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Index a paper embedding (title + abstract + method summary)."""
        await self.client.upsert(
            collection_name=PAPER_COLLECTION,
            points=[
                models.PointStruct(
                    id=self._stable_uuid(f"paper:{paper_id}"),
                    vector=vector,
                    payload={"paper_id": paper_id, **payload},
                )
            ],
        )

    async def search_papers(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Find semantically similar papers."""
        results = await self.client.query_points(
            collection_name=PAPER_COLLECTION,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            {"score": r.score, **r.payload}
            for r in results.points
        ]

    # ---- Method-level embeddings ----

    async def upsert_method(
        self,
        paper_id: str,
        method_name: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Index a method embedding (core_idea + description)."""
        await self.client.upsert(
            collection_name=METHOD_COLLECTION,
            points=[
                models.PointStruct(
                    id=self._stable_uuid(f"method:{paper_id}:{method_name}"),
                    vector=vector,
                    payload={"paper_id": paper_id, "method_name": method_name, **payload},
                )
            ],
        )

    async def search_methods(
        self,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find semantically similar methods."""
        results = await self.client.query_points(
            collection_name=METHOD_COLLECTION,
            query=query_vector,
            limit=limit,
        )
        return [
            {"score": r.score, **r.payload}
            for r in results.points
        ]

    async def get_all_methods(self) -> list[dict[str, Any]]:
        """Retrieve all indexed methods (for building the method-problem matrix)."""
        results = await self.client.scroll(
            collection_name=METHOD_COLLECTION,
            limit=1000,
            with_payload=True,
            with_vectors=True,
        )
        return [
            {"vector": r.vector, **r.payload}
            for r in results[0]
        ]

    # ---- Claim-level embeddings ----

    async def upsert_claim(
        self,
        paper_id: str,
        claim_text: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Index a claim embedding (key_evidence claim)."""
        await self.client.upsert(
            collection_name=CLAIM_COLLECTION,
            points=[
                models.PointStruct(
                    id=self._stable_uuid(f"claim:{paper_id}:{claim_text[:50]}"),
                    vector=vector,
                    payload={"paper_id": paper_id, "claim": claim_text, **payload},
                )
            ],
        )

    async def search_claims(
        self,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find claims related to a query."""
        results = await self.client.query_points(
            collection_name=CLAIM_COLLECTION,
            query=query_vector,
            limit=limit,
        )
        return [
            {"score": r.score, **r.payload}
            for r in results.points
        ]

    # ---- Bulk indexing from knowledge objects ----

    async def index_knowledge_object(
        self,
        knowledge_obj: dict[str, Any],
        embedding_fn,
    ) -> None:
        """Index all embeddings from a single Paper Knowledge Object.

        Args:
            knowledge_obj: Paper Knowledge Object from DeepReader.
            embedding_fn: async callable(text) -> list[float]
        """
        paper_id = knowledge_obj.get("paper_id", "")
        title = knowledge_obj.get("title", "")

        # 1. Paper-level embedding: title + abstract + method summary
        method = knowledge_obj.get("method", {})
        paper_text = f"{title}. {knowledge_obj.get('research_problem', {}).get('statement', '')}. {method.get('core_idea', '')}"
        paper_vector = await embedding_fn(paper_text)
        await self.upsert_paper(
            paper_id=paper_id,
            vector=paper_vector,
            payload={
                "title": title,
                "year": knowledge_obj.get("year"),
                "venue": knowledge_obj.get("venue", ""),
                "core_idea": method.get("core_idea", ""),
                "problem": knowledge_obj.get("research_problem", {}).get("statement", ""),
            },
        )

        # 2. Method-level embedding: core_idea + description
        if method.get("core_idea"):
            method_text = f"{method['core_idea']}. {method.get('description', '')}"
            method_vector = await embedding_fn(method_text)
            await self.upsert_method(
                paper_id=paper_id,
                method_name=method.get("core_idea", "")[:100],
                vector=method_vector,
                payload={
                    "description": method.get("description", ""),
                    "novelty_claim": method.get("novelty_claim", ""),
                    "problem": knowledge_obj.get("research_problem", {}).get("statement", ""),
                },
            )

        # 3. Claim-level embeddings: each key_evidence claim
        for evidence in knowledge_obj.get("key_evidence", []):
            claim = evidence.get("claim", "")
            if claim:
                claim_vector = await embedding_fn(claim)
                await self.upsert_claim(
                    paper_id=paper_id,
                    claim_text=claim,
                    vector=claim_vector,
                    payload={
                        "quote": evidence.get("quote", ""),
                        "section": evidence.get("section", ""),
                        "page": evidence.get("page"),
                    },
                )

        logger.info("Indexed knowledge object for paper '%s'", title[:60])

    @staticmethod
    def _stable_uuid(key: str) -> str:
        """Generate a deterministic UUID from a string key (for upsert idempotency)."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
