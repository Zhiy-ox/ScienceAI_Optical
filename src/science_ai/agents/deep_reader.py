"""Agent 3: Deep Reader — extracts structured Paper Knowledge Objects."""

from __future__ import annotations

import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a meticulous academic paper reader acting as a critical reviewer — NOT a summarizer.

Your task is to extract a structured Paper Knowledge Object from the provided paper.

You MUST distinguish between:
- What the authors CLAIM vs what the EVIDENCE actually supports
- EXPLICIT assumptions vs IMPLICIT assumptions
- Author-stated limitations vs limitations YOU identify

Output valid JSON with this exact schema:
{
  "paper_id": "string",
  "title": "string",
  "authors": ["string"],
  "year": number,
  "venue": "string",

  "research_problem": {
    "statement": "precise problem description",
    "motivation": "why this problem matters"
  },

  "method": {
    "core_idea": "one sentence capturing the essential approach",
    "description": "detailed description",
    "key_components": ["component1", "component2"],
    "novelty_claim": "what the authors claim is new"
  },

  "assumptions": [
    {
      "assumption": "description",
      "type": "explicit" or "implicit",
      "evidence": "source passage or reasoning",
      "page": number or null
    }
  ],

  "experiments": {
    "datasets": ["dataset1", "dataset2"],
    "metrics": ["metric1", "metric2"],
    "baselines": ["baseline1", "baseline2"],
    "key_results": [
      {
        "claim": "description of result",
        "value": "specific numbers",
        "table_or_figure": "Table/Figure reference"
      }
    ]
  },

  "limitations": [
    {
      "description": "limitation description",
      "source": "author_stated" or "reader_identified",
      "severity": "minor" or "moderate" or "major"
    }
  ],

  "future_work": ["direction1", "direction2"],

  "key_evidence": [
    {
      "claim": "what is claimed",
      "quote": "direct quote from paper",
      "page": number or null,
      "section": "section reference"
    }
  ]
}

Be thorough. Extract ALL assumptions (especially implicit ones). Identify limitations \
the authors did NOT mention. Quote exact text for key evidence.
"""

COMPARISON_PROMPT = """\
You are comparing multiple papers on the same topic as a critical reviewer.

For each paper, extract the Paper Knowledge Object (same schema as single-paper analysis).

Additionally, provide a cross-paper comparison:
{
  "papers": [<Paper Knowledge Object>, ...],
  "comparison": {
    "shared_assumptions": ["assumptions shared across papers"],
    "conflicting_claims": [
      {"claim": "description", "paper_a": "position", "paper_b": "position"}
    ],
    "method_evolution": "how methods progressed across papers",
    "evaluation_gaps": ["gaps shared across evaluations"],
    "consensus_findings": ["findings all papers agree on"]
  }
}
"""


class DeepReader(BaseAgent):
    """Extracts structured knowledge objects from papers."""

    agent_name = "deep_reader"
    default_task_type = "deep_read_high"

    async def run(
        self,
        *,
        paper_text: str,
        paper_id: str = "",
        title: str = "",
        priority: str = "high",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Extract a Paper Knowledge Object from a single paper.

        Args:
            paper_text: Full text of the paper.
            paper_id: Paper identifier.
            title: Paper title.
            priority: "high" uses Opus, otherwise Sonnet.

        Returns:
            Paper Knowledge Object dict.
        """
        task_type = "deep_read_high" if priority == "high" else "deep_read_medium"

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"Paper ID: {paper_id}\nTitle: {title}\n\n"
                f"Full text:\n{paper_text}\n\n"
                "Extract the Paper Knowledge Object as JSON."
            ),
        ]

        result = await self.call_llm_json(
            messages=messages, task_type=task_type, max_tokens=8192
        )

        knowledge_obj = result["parsed"]
        logger.info(
            "DeepReader: extracted knowledge for '%s' (%s), %d assumptions, %d limitations",
            title[:60],
            task_type,
            len(knowledge_obj.get("assumptions", [])),
            len(knowledge_obj.get("limitations", [])),
        )

        return knowledge_obj

    async def run_comparison(
        self,
        *,
        papers: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Compare multiple papers in a single context window.

        Uses Claude Opus 1M context (no surcharge) for cross-paper analysis.

        Args:
            papers: List of dicts with keys: paper_id, title, text.

        Returns:
            Comparison result with individual knowledge objects + cross-paper analysis.
        """
        papers_text = "\n\n{'='*80}\n\n".join(
            f"### Paper: {p['title']}\nID: {p['paper_id']}\n\n{p['text']}"
            for p in papers
        )

        messages = [
            self.build_system_message(COMPARISON_PROMPT),
            self.build_user_message(
                f"Compare these {len(papers)} papers:\n\n{papers_text}\n\n"
                "Output the comparison JSON."
            ),
        ]

        result = await self.call_llm_json(
            messages=messages,
            task_type="deep_read_high",
            max_tokens=16384,
        )

        logger.info("DeepReader: compared %d papers", len(papers))
        return result["parsed"]
