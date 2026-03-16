"""Report Writer — generates the final comprehensive research report."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert scientific report writer. Generate a comprehensive research \
report synthesizing all analysis results.

The report MUST include these sections:

1. **Executive Summary**: 2-3 paragraph overview of findings
2. **Research Question Analysis**: How the question was decomposed
3. **Literature Landscape**: Overview of the field based on paper analysis
   - Key themes and sub-areas
   - Major methods and their evolution
   - Influential papers and authors
4. **Critical Analysis**: Synthesis of paper critiques
   - Common strengths across the literature
   - Systematic weaknesses and blind spots
   - Evaluation practices assessment
5. **Research Gaps**: Detailed description of each verified gap
   - Detection mechanism used
   - Supporting evidence (with paper citations)
   - Confidence and impact assessment
6. **Research Ideas**: For each proposed idea
   - Description and hypothesis
   - Connection to identified gaps
   - Novelty and feasibility assessment
7. **Experiment Plans**: Concrete next steps for top ideas
8. **Cost Summary**: API usage and cost breakdown

IMPORTANT:
- Every claim must cite specific papers
- Use the paper_id for citations
- Be specific about evidence, not vague
- Structure with clear markdown headers

Output the report as a JSON object:
{
  "title": "Research Report: [topic]",
  "generated_at": "ISO timestamp",
  "sections": [
    {"heading": "Section Title", "content": "markdown content"},
    ...
  ],
  "citations": [
    {"paper_id": "...", "title": "...", "year": ..., "relevance": "how it's cited"}
  ]
}
"""


class ReportWriter(BaseAgent):
    """Generates the final comprehensive research report using Claude Opus."""

    agent_name = "report_writer"
    default_task_type = "report_writing"

    async def run(
        self,
        *,
        question: str,
        plan: dict[str, Any],
        knowledge_objects: list[dict[str, Any]],
        critiques: list[dict[str, Any]],
        verified_gaps: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        experiment_plans: list[dict[str, Any]],
        cost_summary: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a complete research report.

        Args:
            question: Original research question.
            plan: Research plan from QueryPlanner.
            knowledge_objects: Paper Knowledge Objects from DeepReader.
            critiques: Critique reports from CritiqueAgent.
            verified_gaps: Verified research gaps.
            ideas: Generated research ideas.
            experiment_plans: Experiment plans for ideas.
            cost_summary: Session cost breakdown.
        """
        # Build compact context to fit within token limits
        compact_kos = [
            {
                "paper_id": ko.get("paper_id"),
                "title": ko.get("title"),
                "year": ko.get("year"),
                "method": ko.get("method", {}).get("core_idea"),
                "problem": ko.get("research_problem", {}).get("statement"),
                "limitations": [l.get("description") for l in ko.get("limitations", [])],
                "key_results": [r.get("claim") for r in ko.get("experiments", {}).get("key_results", [])],
            }
            for ko in knowledge_objects
        ]

        context = json.dumps({
            "research_question": question,
            "plan_summary": {
                "sub_questions": plan.get("decomposed_questions", []),
                "scope": plan.get("scope", {}),
            },
            "papers_analyzed": compact_kos,
            "critiques_summary": [
                {
                    "paper_id": c.get("paper_id"),
                    "overall_confidence": c.get("overall_confidence"),
                    "key_issues": (
                        [i.get("problem") for i in c.get("critique", {}).get("assumption_issues", [])]
                        + [i.get("issue") for i in c.get("critique", {}).get("experimental_weaknesses", [])]
                    )[:5],
                }
                for c in critiques
            ],
            "verified_gaps": verified_gaps,
            "research_ideas": ideas,
            "experiment_plans": experiment_plans,
            "cost_summary": cost_summary,
        }, indent=2)

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"Generate a comprehensive research report from this analysis:\n\n"
                f"{context}\n\n"
                "Output the report as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=16384)
        report = result["parsed"]

        logger.info(
            "ReportWriter: generated report with %d sections",
            len(report.get("sections", [])),
        )
        return report
