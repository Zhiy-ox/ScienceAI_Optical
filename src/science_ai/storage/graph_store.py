"""Neo4j knowledge graph for citation analysis and gap detection."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GraphStore:
    """Neo4j knowledge graph client.

    Node types: Paper, Method, Problem, Dataset, Assumption, Author
    Relationship types: USES_METHOD, ADDRESSES, EVALUATED_ON, ASSUMES,
                        CITES, EXTENDS, CRITICIZES, AUTHORED
    """

    def __init__(self, uri: str = "bolt://localhost:7687", auth: tuple = ("neo4j", "password")):
        self._uri = uri
        self._auth = auth
        self._driver = None

    async def connect(self) -> None:
        """Connect to Neo4j (requires neo4j async driver)."""
        from neo4j import AsyncGraphDatabase
        self._driver = AsyncGraphDatabase.driver(self._uri, auth=self._auth)
        logger.info("Connected to Neo4j at %s", self._uri)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        async with self._driver.session() as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            return records

    # ---- Populate graph from knowledge objects ----

    async def ingest_knowledge_object(self, ko: dict[str, Any]) -> None:
        """Create nodes and relationships from a Paper Knowledge Object."""
        paper_id = ko.get("paper_id", "")
        title = ko.get("title", "")
        year = ko.get("year")
        venue = ko.get("venue", "")

        # Create Paper node
        await self.query(
            "MERGE (p:Paper {paper_id: $pid}) "
            "SET p.title = $title, p.year = $year, p.venue = $venue",
            {"pid": paper_id, "title": title, "year": year, "venue": venue},
        )

        # Create authors
        for author in ko.get("authors", []):
            await self.query(
                "MERGE (a:Author {name: $name}) "
                "MERGE (p:Paper {paper_id: $pid}) "
                "MERGE (a)-[:AUTHORED]->(p)",
                {"name": author, "pid": paper_id},
            )

        # Create Problem node + ADDRESSES relationship
        problem = ko.get("research_problem", {}).get("statement", "")
        if problem:
            await self.query(
                "MERGE (prob:Problem {name: $problem}) "
                "MERGE (p:Paper {paper_id: $pid}) "
                "MERGE (p)-[:ADDRESSES]->(prob)",
                {"problem": problem, "pid": paper_id},
            )

        # Create Method node + USES_METHOD relationship
        method = ko.get("method", {})
        method_name = method.get("core_idea", "")
        if method_name:
            await self.query(
                "MERGE (m:Method {name: $method}) "
                "SET m.description = $desc, m.novelty_claim = $novelty "
                "MERGE (p:Paper {paper_id: $pid}) "
                "MERGE (p)-[:USES_METHOD]->(m)",
                {
                    "method": method_name,
                    "desc": method.get("description", ""),
                    "novelty": method.get("novelty_claim", ""),
                    "pid": paper_id,
                },
            )

        # Create Dataset nodes + EVALUATED_ON relationships
        for ds in ko.get("experiments", {}).get("datasets", []):
            await self.query(
                "MERGE (d:Dataset {name: $ds}) "
                "MERGE (p:Paper {paper_id: $pid}) "
                "MERGE (p)-[:EVALUATED_ON]->(d)",
                {"ds": ds, "pid": paper_id},
            )

        # Create Assumption nodes + ASSUMES relationships
        for assumption in ko.get("assumptions", []):
            desc = assumption.get("assumption", "")
            if desc:
                await self.query(
                    "MERGE (a:Assumption {name: $desc}) "
                    "SET a.type = $type "
                    "MERGE (p:Paper {paper_id: $pid}) "
                    "MERGE (p)-[:ASSUMES]->(a)",
                    {
                        "desc": desc,
                        "type": assumption.get("type", "explicit"),
                        "pid": paper_id,
                    },
                )

                # Method REQUIRES_ASSUMPTION
                if method_name:
                    await self.query(
                        "MATCH (m:Method {name: $method}) "
                        "MATCH (a:Assumption {name: $desc}) "
                        "MERGE (m)-[:REQUIRES_ASSUMPTION]->(a)",
                        {"method": method_name, "desc": desc},
                    )

    async def add_citation(self, citing_id: str, cited_id: str) -> None:
        """Add a CITES relationship between two papers."""
        await self.query(
            "MERGE (a:Paper {paper_id: $citing}) "
            "MERGE (b:Paper {paper_id: $cited}) "
            "MERGE (a)-[:CITES]->(b)",
            {"citing": citing_id, "cited": cited_id},
        )

    # ---- Gap detection queries (Mechanism C) ----

    async def find_community_silos(self) -> list[dict]:
        """Find sub-communities with low cross-citation (bridging opportunities)."""
        return await self.query(
            "MATCH (p1:Paper)-[:ADDRESSES]->(prob1:Problem) "
            "MATCH (p2:Paper)-[:ADDRESSES]->(prob2:Problem) "
            "WHERE prob1 <> prob2 "
            "OPTIONAL MATCH (p1)-[:CITES]->(p2) "
            "WITH prob1.name AS field1, prob2.name AS field2, "
            "     COUNT(DISTINCT p1) AS papers1, COUNT(DISTINCT p2) AS papers2, "
            "     COUNT(DISTINCT p1)-COUNT(DISTINCT p2) AS cross_citations "
            "WHERE cross_citations < 2 AND papers1 >= 2 AND papers2 >= 2 "
            "RETURN field1, field2, papers1, papers2, cross_citations "
            "ORDER BY cross_citations ASC LIMIT 10"
        )

    async def find_broken_chains(self) -> list[dict]:
        """Find methods that were criticized but no follow-up resolved the criticism."""
        return await self.query(
            "MATCH (critic:Paper)-[:CRITICIZES]->(base:Paper) "
            "WHERE NOT EXISTS { "
            "  MATCH (followup:Paper)-[:EXTENDS]->(base) "
            "  WHERE followup.year > critic.year "
            "} "
            "RETURN base.paper_id AS base_id, base.title AS base_title, "
            "       critic.paper_id AS critic_id, critic.title AS critic_title "
            "LIMIT 20"
        )

    async def find_stale_high_citation_nodes(self, min_citations: int = 5, years_stale: int = 3) -> list[dict]:
        """Find highly-cited papers with no recent extensions."""
        return await self.query(
            "MATCH (p:Paper) "
            "WHERE p.year <= date().year - $years "
            "OPTIONAL MATCH (citer:Paper)-[:CITES]->(p) "
            "WITH p, COUNT(citer) AS cite_count "
            "WHERE cite_count >= $min_cites "
            "AND NOT EXISTS { "
            "  MATCH (ext:Paper)-[:EXTENDS]->(p) "
            "  WHERE ext.year >= date().year - 1 "
            "} "
            "RETURN p.paper_id AS paper_id, p.title AS title, "
            "       p.year AS year, cite_count "
            "ORDER BY cite_count DESC LIMIT 10",
            {"years": years_stale, "min_cites": min_citations},
        )

    async def get_method_problem_coverage(self) -> list[dict]:
        """Get the method-problem coverage matrix from the graph."""
        return await self.query(
            "MATCH (p:Paper)-[:ADDRESSES]->(prob:Problem) "
            "MATCH (p)-[:USES_METHOD]->(m:Method) "
            "RETURN prob.name AS problem, m.name AS method, "
            "       COLLECT(DISTINCT p.paper_id) AS paper_ids, "
            "       COUNT(DISTINCT p) AS paper_count "
            "ORDER BY problem, method"
        )

    async def find_shared_unverified_assumptions(self, min_papers: int = 3) -> list[dict]:
        """Find assumptions shared by many papers but never independently verified."""
        return await self.query(
            "MATCH (p:Paper)-[:ASSUMES]->(a:Assumption) "
            "WITH a, COLLECT(DISTINCT p.paper_id) AS paper_ids, COUNT(DISTINCT p) AS cnt "
            "WHERE cnt >= $min_papers "
            "RETURN a.name AS assumption, a.type AS type, paper_ids, cnt "
            "ORDER BY cnt DESC",
            {"min_papers": min_papers},
        )


class InMemoryGraphStore:
    """In-memory graph store for use without Neo4j.

    Provides the same gap-detection query interface using Python data structures.
    Suitable for Phase 3 testing and small-scale use.
    """

    def __init__(self) -> None:
        self.papers: dict[str, dict] = {}
        self.methods: dict[str, dict] = {}
        self.problems: dict[str, dict] = {}
        self.assumptions: dict[str, dict] = {}
        self.datasets: dict[str, dict] = {}
        self.authors: dict[str, dict] = {}

        # Relationships as adjacency lists
        self.paper_methods: dict[str, set[str]] = {}     # paper_id → {method_names}
        self.paper_problems: dict[str, set[str]] = {}    # paper_id → {problem_names}
        self.paper_datasets: dict[str, set[str]] = {}    # paper_id → {dataset_names}
        self.paper_assumptions: dict[str, set[str]] = {} # paper_id → {assumption_names}
        self.citations: dict[str, set[str]] = {}         # citing → {cited}
        self.extensions: dict[str, set[str]] = {}        # extending → {extended}
        self.criticisms: dict[str, set[str]] = {}        # criticizing → {criticized}

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def ingest_knowledge_object(self, ko: dict[str, Any]) -> None:
        """Populate the in-memory graph from a knowledge object."""
        paper_id = ko.get("paper_id", "")
        self.papers[paper_id] = {
            "title": ko.get("title", ""),
            "year": ko.get("year"),
            "venue": ko.get("venue", ""),
        }

        # Problem
        problem = ko.get("research_problem", {}).get("statement", "")
        if problem:
            self.problems[problem] = {"name": problem}
            self.paper_problems.setdefault(paper_id, set()).add(problem)

        # Method
        method_name = ko.get("method", {}).get("core_idea", "")
        if method_name:
            self.methods[method_name] = {
                "name": method_name,
                "description": ko.get("method", {}).get("description", ""),
            }
            self.paper_methods.setdefault(paper_id, set()).add(method_name)

        # Datasets
        for ds in ko.get("experiments", {}).get("datasets", []):
            self.datasets[ds] = {"name": ds}
            self.paper_datasets.setdefault(paper_id, set()).add(ds)

        # Assumptions
        for assumption in ko.get("assumptions", []):
            desc = assumption.get("assumption", "")
            if desc:
                self.assumptions[desc] = {"name": desc, "type": assumption.get("type", "explicit")}
                self.paper_assumptions.setdefault(paper_id, set()).add(desc)

    async def add_citation(self, citing_id: str, cited_id: str) -> None:
        self.citations.setdefault(citing_id, set()).add(cited_id)

    async def find_community_silos(self) -> list[dict]:
        """Find problem pairs with low cross-citation."""
        # Build problem → papers mapping
        problem_papers: dict[str, set[str]] = {}
        for pid, problems in self.paper_problems.items():
            for prob in problems:
                problem_papers.setdefault(prob, set()).add(pid)

        silos = []
        problems_list = list(problem_papers.keys())
        for i, p1 in enumerate(problems_list):
            for p2 in problems_list[i + 1:]:
                papers1 = problem_papers[p1]
                papers2 = problem_papers[p2]
                if len(papers1) < 2 or len(papers2) < 2:
                    continue

                cross = 0
                for a in papers1:
                    for b in papers2:
                        if b in self.citations.get(a, set()):
                            cross += 1
                        if a in self.citations.get(b, set()):
                            cross += 1

                if cross < 2:
                    silos.append({
                        "field1": p1,
                        "field2": p2,
                        "papers1": len(papers1),
                        "papers2": len(papers2),
                        "cross_citations": cross,
                    })

        return sorted(silos, key=lambda x: x["cross_citations"])[:10]

    async def find_broken_chains(self) -> list[dict]:
        """Find criticized papers with no follow-up resolution."""
        chains = []
        for critic_id, criticized_set in self.criticisms.items():
            critic_year = self.papers.get(critic_id, {}).get("year", 0) or 0
            for base_id in criticized_set:
                # Check if any extension exists after the criticism
                has_followup = False
                for ext_id, ext_targets in self.extensions.items():
                    if base_id in ext_targets:
                        ext_year = self.papers.get(ext_id, {}).get("year", 0) or 0
                        if ext_year > critic_year:
                            has_followup = True
                            break

                if not has_followup:
                    chains.append({
                        "base_id": base_id,
                        "base_title": self.papers.get(base_id, {}).get("title", ""),
                        "critic_id": critic_id,
                        "critic_title": self.papers.get(critic_id, {}).get("title", ""),
                    })

        return chains[:20]

    async def find_shared_unverified_assumptions(self, min_papers: int = 3) -> list[dict]:
        """Find assumptions shared by many papers."""
        assumption_papers: dict[str, list[str]] = {}
        for pid, assumptions in self.paper_assumptions.items():
            for a in assumptions:
                assumption_papers.setdefault(a, []).append(pid)

        results = []
        for assumption, paper_ids in assumption_papers.items():
            if len(paper_ids) >= min_papers:
                results.append({
                    "assumption": assumption,
                    "type": self.assumptions.get(assumption, {}).get("type", ""),
                    "paper_ids": paper_ids,
                    "cnt": len(paper_ids),
                })

        return sorted(results, key=lambda x: x["cnt"], reverse=True)

    async def get_method_problem_coverage(self) -> list[dict]:
        """Get method-problem coverage."""
        coverage: dict[tuple[str, str], list[str]] = {}
        for pid, methods in self.paper_methods.items():
            problems = self.paper_problems.get(pid, set())
            for method in methods:
                for problem in problems:
                    key = (problem, method)
                    coverage.setdefault(key, []).append(pid)

        return [
            {
                "problem": prob,
                "method": method,
                "paper_ids": pids,
                "paper_count": len(pids),
            }
            for (prob, method), pids in sorted(coverage.items())
        ]
