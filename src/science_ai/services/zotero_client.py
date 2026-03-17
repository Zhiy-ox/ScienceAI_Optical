"""Zotero integration for reading and writing papers via pyzotero."""

from __future__ import annotations

import logging
from typing import Any

from pyzotero import zotero

from science_ai.services.paper_search import PaperMeta

logger = logging.getLogger(__name__)


class ZoteroClient:
    """Read/write client for a Zotero library using the Zotero Web API."""

    def __init__(
        self,
        library_id: str,
        api_key: str,
        library_type: str = "user",
    ) -> None:
        self.library_id = library_id
        self.library_type = library_type
        self.zot = zotero.Zotero(library_id, library_type, api_key)

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def search(self, query: str, *, limit: int = 50) -> list[PaperMeta]:
        """Search the Zotero library by query string."""
        items = self.zot.items(q=query, limit=limit, itemType="-attachment || note")
        return [self._to_paper_meta(item) for item in items if item.get("data", {}).get("title")]

    def get_collection_items(self, collection_key: str, *, limit: int = 100) -> list[PaperMeta]:
        """Fetch all items in a Zotero collection."""
        items = self.zot.collection_items(collection_key, limit=limit, itemType="-attachment || note")
        return [self._to_paper_meta(item) for item in items if item.get("data", {}).get("title")]

    def get_top_items(self, *, limit: int = 50) -> list[PaperMeta]:
        """Fetch top-level library items."""
        items = self.zot.top(limit=limit, itemType="-attachment || note")
        return [self._to_paper_meta(item) for item in items if item.get("data", {}).get("title")]

    def list_collections(self) -> list[dict[str, Any]]:
        """List all collections in the library."""
        collections = self.zot.collections()
        return [
            {
                "key": c["key"],
                "name": c["data"].get("name", ""),
                "num_items": c["meta"].get("numItems", 0),
            }
            for c in collections
        ]

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------

    def create_collection(self, name: str, parent_key: str | None = None) -> str:
        """Create a new Zotero collection. Returns the collection key."""
        payload = {"name": name}
        if parent_key:
            payload["parentCollection"] = parent_key

        resp = self.zot.create_collections([payload])
        # pyzotero returns {"successful": {"0": {...}}, ...}
        successful = resp.get("successful", {})
        if successful:
            first = next(iter(successful.values()))
            return first.get("key", first.get("data", {}).get("key", ""))
        raise RuntimeError(f"Failed to create Zotero collection: {resp}")

    def add_item(self, paper: PaperMeta, collection_key: str | None = None) -> str:
        """Create a Zotero item from a PaperMeta. Returns the item key."""
        template = self.zot.item_template("journalArticle")
        template["title"] = paper.title
        template["abstractNote"] = paper.abstract
        template["date"] = str(paper.year) if paper.year else ""
        template["url"] = paper.url

        # Set creators
        template["creators"] = [
            {"creatorType": "author", "name": name}
            for name in paper.authors[:20]
        ]

        # Extract DOI if present in paper_id
        if paper.paper_id and not paper.paper_id.startswith("arxiv:"):
            template["DOI"] = paper.paper_id

        if paper.venue:
            template["publicationTitle"] = paper.venue

        if collection_key:
            template["collections"] = [collection_key]

        resp = self.zot.create_items([template])
        successful = resp.get("successful", {})
        if successful:
            first = next(iter(successful.values()))
            return first.get("key", first.get("data", {}).get("key", ""))
        raise RuntimeError(f"Failed to create Zotero item: {resp}")

    def add_note(self, parent_item_key: str, content: str, tags: list[str] | None = None) -> str:
        """Attach a note to a Zotero item. Returns the note key."""
        template = self.zot.item_template("note")
        template["parentItem"] = parent_item_key
        template["note"] = content
        if tags:
            template["tags"] = [{"tag": t} for t in tags]

        resp = self.zot.create_items([template])
        successful = resp.get("successful", {})
        if successful:
            first = next(iter(successful.values()))
            return first.get("key", first.get("data", {}).get("key", ""))
        raise RuntimeError(f"Failed to create Zotero note: {resp}")

    def add_tags(self, item_key: str, tags: list[str]) -> None:
        """Add tags to a Zotero item."""
        item = self.zot.item(item_key)
        existing_tags = item["data"].get("tags", [])
        existing_tag_names = {t["tag"] for t in existing_tags}
        new_tags = [{"tag": t} for t in tags if t not in existing_tag_names]
        if new_tags:
            item["data"]["tags"] = existing_tags + new_tags
            self.zot.update_item(item)

    # ------------------------------------------------------------------
    # PIPELINE EXPORT
    # ------------------------------------------------------------------

    def export_session(
        self,
        *,
        session_id: str,
        question: str,
        triage_results: list[dict],
        knowledge_objects: list[dict],
        critiques: list[dict],
        verified_gaps: list[dict],
        ideas: list[dict],
        report: dict | None,
        all_papers: list[PaperMeta],
    ) -> str:
        """Export a full research session to Zotero.

        Creates a collection for the session, adds papers with tags,
        attaches critiques/gaps/ideas as notes.
        Returns the collection key.
        """
        # Create session collection
        short_q = question[:60] + ("..." if len(question) > 60 else "")
        collection_key = self.create_collection(f"ScienceAI: {short_q}")

        # Build paper lookup
        paper_map = {p.paper_id: p for p in all_papers}
        item_key_map: dict[str, str] = {}  # paper_id → zotero item key

        # Add triaged papers
        for tr in triage_results:
            pid = tr.get("paper_id", "")
            paper = paper_map.get(pid)
            if not paper:
                continue
            try:
                item_key = self.add_item(paper, collection_key=collection_key)
                item_key_map[pid] = item_key
                # Tag by priority
                priority = tr.get("priority", "skip")
                self.add_tags(item_key, ["ScienceAI", f"priority:{priority}", f"session:{session_id[:8]}"])
            except Exception:
                logger.exception("Failed to export paper %s to Zotero", pid)

        # Attach knowledge objects as notes
        for ko in knowledge_objects:
            pid = ko.get("paper_id", "")
            item_key = item_key_map.get(pid)
            if not item_key:
                continue
            try:
                method = ko.get("method", {})
                note_html = (
                    f"<h2>Knowledge Object</h2>"
                    f"<p><b>Core idea:</b> {method.get('core_idea', 'N/A')}</p>"
                    f"<p><b>Key components:</b> {', '.join(method.get('key_components', []))}</p>"
                )
                self.add_note(item_key, note_html, tags=["ScienceAI", "knowledge_object"])
            except Exception:
                logger.exception("Failed to attach knowledge object for %s", pid)

        # Attach critiques as notes
        for crit in critiques:
            pid = crit.get("paper_id", "")
            item_key = item_key_map.get(pid)
            if not item_key:
                continue
            try:
                assumptions = crit.get("assumption_issues", [])
                weaknesses = crit.get("experimental_weaknesses", [])
                note_html = (
                    f"<h2>Critique</h2>"
                    f"<p><b>Assumption issues:</b></p><ul>{''.join(f'<li>{a}</li>' for a in assumptions)}</ul>"
                    f"<p><b>Experimental weaknesses:</b></p><ul>{''.join(f'<li>{w}</li>' for w in weaknesses)}</ul>"
                )
                self.add_note(item_key, note_html, tags=["ScienceAI", "critique"])
            except Exception:
                logger.exception("Failed to attach critique for %s", pid)

        # Add verified gaps as standalone notes in collection
        for gap in verified_gaps:
            try:
                note_html = (
                    f"<h2>Research Gap: {gap.get('title', '')}</h2>"
                    f"<p><b>Type:</b> {gap.get('gap_type', '')}</p>"
                    f"<p><b>Confidence:</b> {gap.get('confidence', 'N/A')}</p>"
                    f"<p><b>Status:</b> {gap.get('status', '')}</p>"
                )
                # Create as a standalone note item in the collection
                template = self.zot.item_template("note")
                template["note"] = note_html
                template["tags"] = [{"tag": "ScienceAI"}, {"tag": "verified_gap"}]
                template["collections"] = [collection_key]
                self.zot.create_items([template])
            except Exception:
                logger.exception("Failed to export gap to Zotero")

        # Add ideas as standalone notes
        for idea in ideas:
            try:
                note_html = (
                    f"<h2>Research Idea: {idea.get('title', '')}</h2>"
                    f"<p><b>Strategy:</b> {idea.get('strategy', '')}</p>"
                    f"<p><b>Feasibility:</b> {idea.get('feasibility_score', 'N/A')}</p>"
                )
                template = self.zot.item_template("note")
                template["note"] = note_html
                template["tags"] = [{"tag": "ScienceAI"}, {"tag": "research_idea"}]
                template["collections"] = [collection_key]
                self.zot.create_items([template])
            except Exception:
                logger.exception("Failed to export idea to Zotero")

        # Add report as standalone note
        if report:
            try:
                sections_html = ""
                for section in report.get("sections", []):
                    sections_html += f"<h2>{section.get('heading', '')}</h2><p>{section.get('content', '')}</p>"
                note_html = f"<h1>{report.get('title', 'Research Report')}</h1>{sections_html}"
                template = self.zot.item_template("note")
                template["note"] = note_html
                template["tags"] = [{"tag": "ScienceAI"}, {"tag": "report"}]
                template["collections"] = [collection_key]
                self.zot.create_items([template])
            except Exception:
                logger.exception("Failed to export report to Zotero")

        logger.info("Exported session %s to Zotero collection %s", session_id, collection_key)
        return collection_key

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    def _to_paper_meta(self, item: dict) -> PaperMeta:
        """Convert a Zotero item to PaperMeta."""
        data = item.get("data", {})
        creators = data.get("creators", [])
        authors = []
        for c in creators:
            name = c.get("name") or f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
            if name:
                authors.append(name)

        year = None
        date_str = data.get("date", "")
        if date_str and len(date_str) >= 4:
            try:
                year = int(date_str[:4])
            except ValueError:
                pass

        doi = data.get("DOI", "")
        paper_id = doi or data.get("key", item.get("key", ""))
        url = data.get("url", "")

        return PaperMeta(
            paper_id=f"zotero:{paper_id}",
            title=data.get("title", ""),
            authors=authors,
            year=year,
            venue=data.get("publicationTitle", ""),
            abstract=data.get("abstractNote", ""),
            citation_count=0,
            source="zotero",
            url=url,
        )
