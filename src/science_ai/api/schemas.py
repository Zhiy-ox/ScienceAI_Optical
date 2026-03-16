"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# -- Requests --

class StartResearchRequest(BaseModel):
    question: str = Field(..., description="Research question in natural language")
    max_papers: int = Field(default=15, ge=1, le=50, description="Max papers to deep-read")
    phase: int = Field(default=3, ge=1, le=3, description="Pipeline phase to run (1, 2, or 3)")
    user_background: str = Field(default="", description="Optional researcher background for personalization")


# -- Responses --

class SessionCreated(BaseModel):
    session_id: str
    status: str = "started"
    message: str = "Research pipeline started"


class CostSummary(BaseModel):
    session_id: str
    total_usd: float
    by_model: dict[str, float]
    call_count: int


class ResearchResult(BaseModel):
    session_id: str
    status: str
    plan: dict | None = None
    papers_found: int = 0
    triage_results: list[dict] = []
    knowledge_objects: list[dict] = []
    critiques: list[dict] = []
    gaps: list[dict] = []
    verified_gaps: list[dict] = []
    ideas: list[dict] = []
    experiment_plans: list[dict] = []
    report: dict | None = None
    cost_summary: CostSummary | None = None


class SessionStatus(BaseModel):
    session_id: str
    status: str
    cost_so_far: float = 0.0


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.3.0"
