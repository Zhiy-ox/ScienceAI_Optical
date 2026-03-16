"""Neo4j knowledge graph client — Phase 3 placeholder."""

from __future__ import annotations


class GraphStore:
    """Neo4j knowledge graph for citation analysis and gap detection.

    Will be implemented in Phase 3 with node types:
    - Paper, Method, Problem, Dataset, Assumption, Author

    And relationship types:
    - USES_METHOD, ADDRESSES, EVALUATED_ON, ASSUMES, CITES, EXTENDS, CRITICIZES, AUTHORED
    """

    async def connect(self) -> None:
        raise NotImplementedError("Phase 3")

    async def add_paper(self, paper: dict) -> None:
        raise NotImplementedError("Phase 3")

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        raise NotImplementedError("Phase 3")
