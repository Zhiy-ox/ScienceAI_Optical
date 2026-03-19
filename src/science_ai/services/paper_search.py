"""Paper search clients for Semantic Scholar, arXiv, and OpenAlex."""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
ARXIV_BASE = "https://export.arxiv.org/api/query"
OPENALEX_BASE = "https://api.openalex.org"


@dataclass
class PaperMeta:
    """Standardized paper metadata from any source."""

    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str
    abstract: str
    citation_count: int
    source: str  # "semantic_scholar" | "arxiv" | "openalex"
    url: str
    references: list[str] | None = None


class SemanticScholarClient:
    """Client for the Semantic Scholar Academic Graph API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.headers = {}
        if api_key:
            self.headers["x-api-key"] = api_key

    async def search(
        self,
        query: str,
        *,
        limit: int = 50,
        year_range: tuple[int, int] | None = None,
        fields_of_study: list[str] | None = None,
    ) -> list[PaperMeta]:
        """Search papers by query string."""
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": "paperId,title,authors,year,venue,abstract,citationCount,externalIds,url",
        }
        if year_range:
            params["year"] = f"{year_range[0]}-{year_range[1]}"
        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(4):
                resp = await client.get(
                    f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
                    params=params,
                    headers=self.headers,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt  # 1, 2, 4, 8
                    logger.warning("S2 rate-limited, retrying in %ds...", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            else:
                resp.raise_for_status()  # raise the last 429

        data = resp.json().get("data", [])
        return [self._to_paper_meta(p) for p in data if p.get("abstract")]

    async def get_paper(self, paper_id: str) -> PaperMeta | None:
        """Get a single paper by Semantic Scholar ID or DOI."""
        fields = "paperId,title,authors,year,venue,abstract,citationCount,externalIds,url,references"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/{paper_id}",
                params={"fields": fields},
                headers=self.headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()

        return self._to_paper_meta(resp.json())

    async def get_citations(self, paper_id: str, limit: int = 50) -> list[PaperMeta]:
        """Get papers that cite the given paper."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/{paper_id}/citations",
                params={
                    "limit": limit,
                    "fields": "paperId,title,authors,year,venue,abstract,citationCount,url",
                },
                headers=self.headers,
            )
            resp.raise_for_status()

        data = resp.json().get("data", [])
        return [
            self._to_paper_meta(item["citingPaper"])
            for item in data
            if item.get("citingPaper", {}).get("abstract")
        ]

    def _to_paper_meta(self, raw: dict) -> PaperMeta:
        authors = [a.get("name", "") for a in raw.get("authors", [])]
        refs = None
        if "references" in raw and raw["references"]:
            refs = [r.get("paperId", "") for r in raw["references"] if r.get("paperId")]

        external = raw.get("externalIds", {}) or {}
        pid = external.get("DOI") or external.get("ArXiv") or raw.get("paperId", "")

        return PaperMeta(
            paper_id=pid,
            title=raw.get("title", ""),
            authors=authors,
            year=raw.get("year"),
            venue=raw.get("venue", ""),
            abstract=raw.get("abstract", ""),
            citation_count=raw.get("citationCount", 0),
            source="semantic_scholar",
            url=raw.get("url", ""),
            references=refs,
        )


class ArxivClient:
    """Client for the arXiv API."""

    async def search(
        self,
        query: str,
        *,
        limit: int = 50,
        sort_by: str = "relevance",
    ) -> list[PaperMeta]:
        """Search arXiv papers."""
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(ARXIV_BASE, params=params)
            resp.raise_for_status()

        return self._parse_atom_feed(resp.text)

    def _parse_atom_feed(self, xml_text: str) -> list[PaperMeta]:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_text)
        papers = []

        for entry in root.findall("atom:entry", ns):
            arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]
            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
            authors = [
                a.findtext("atom:name", "", ns)
                for a in entry.findall("atom:author", ns)
            ]
            published = entry.findtext("atom:published", "", ns) or ""
            year = int(published[:4]) if len(published) >= 4 else None

            papers.append(PaperMeta(
                paper_id=f"arxiv:{arxiv_id}",
                title=title,
                authors=authors,
                year=year,
                venue="arXiv",
                abstract=abstract,
                citation_count=0,
                source="arxiv",
                url=f"https://arxiv.org/abs/{arxiv_id}",
            ))

        return papers


class PaperSearchService:
    """Unified search across multiple academic APIs."""

    def __init__(self, semantic_scholar_key: str | None = None) -> None:
        self.s2 = SemanticScholarClient(api_key=semantic_scholar_key)
        self.arxiv = ArxivClient()

    async def search(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        limit: int = 50,
        year_range: tuple[int, int] | None = None,
    ) -> list[PaperMeta]:
        """Search across configured sources and deduplicate results."""
        sources = sources or ["semantic_scholar", "arxiv"]
        all_papers: list[PaperMeta] = []

        if "semantic_scholar" in sources:
            try:
                papers = await self.s2.search(query, limit=limit, year_range=year_range)
                all_papers.extend(papers)
            except Exception:
                logger.exception("Semantic Scholar search failed for query: %s", query)

        if "arxiv" in sources:
            try:
                papers = await self.arxiv.search(query, limit=limit)
                all_papers.extend(papers)
            except Exception:
                logger.exception("arXiv search failed for query: %s", query)

        # Deduplicate by title similarity (simple lowercase match)
        seen_titles: set[str] = set()
        unique: list[PaperMeta] = []
        for p in all_papers:
            key = p.title.lower().strip()
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(p)

        return unique
