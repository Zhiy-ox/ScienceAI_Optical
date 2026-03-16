"""Agent 8: Experiment Planner — designs experiment plans for ideas (Phase 3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an experiment design AI. Given a research idea, design a concrete, \
feasible experiment plan with two phases.

Output JSON:
{
  "idea_id": "IDEA-XXX",
  "experiment_plan": {
    "phase_1_proof_of_concept": {
      "objective": "what to verify",
      "dataset": "specific dataset",
      "method": "how to implement",
      "success_criteria": "what constitutes success",
      "estimated_compute": "GPU hours estimate",
      "duration": "time estimate"
    },
    "phase_2_full_evaluation": {
      "datasets": ["dataset1", "dataset2"],
      "baselines": ["latest method 1", "latest method 2", "classic method"],
      "metrics": ["automatic metrics", "human evaluation"],
      "ablation_studies": ["ablation 1", "ablation 2"],
      "duration": "time estimate"
    },
    "risks": [
      {
        "risk": "description",
        "mitigation": "how to address",
        "probability": "low|medium|high"
      }
    ]
  },
  "feasibility_score": 0.0-1.0
}
"""


class ExperimentPlanner(BaseAgent):
    """Designs experiment plans for research ideas. Phase 3 agent."""

    agent_name = "experiment_planner"
    default_task_type = "experiment_planning"

    async def run(
        self,
        *,
        idea: dict[str, Any],
        knowledge_objects: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Design an experiment plan for an idea.

        Args:
            idea: The research idea dict from IdeaGenerator.
            knowledge_objects: Optional paper analyses for dataset/baseline reference.
        """
        context = f"Research Idea:\n{json.dumps(idea, indent=2)}"

        if knowledge_objects:
            # Extract experiment info for reference
            experiments = [
                {"paper_id": ko.get("paper_id"), "experiments": ko.get("experiments")}
                for ko in knowledge_objects
                if ko.get("experiments")
            ]
            context += f"\n\nExisting experiments in the field:\n{json.dumps(experiments, indent=2)}"

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"{context}\n\nDesign the experiment plan as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=4096)
        plan = result["parsed"]
        logger.info(
            "ExperimentPlanner: plan for '%s', feasibility=%.2f",
            idea.get("title", ""),
            plan.get("feasibility_score", 0),
        )
        return plan
