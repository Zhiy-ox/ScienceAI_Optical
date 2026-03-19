"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# -- Requests --

class StartResearchRequest(BaseModel):
    question: str = Field(..., description="Research question in natural language")
    max_papers: int = Field(default=15, ge=1, le=50, description="Max papers to deep-read")
    phase: int = Field(default=3, ge=1, le=3, description="Pipeline phase to run (1, 2, or 3)")
    user_background: str = Field(default="", description="Optional researcher background for personalization")
    source: str = Field(default="web", description="Paper source: 'web', 'zotero', or 'both'")


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


class CostDetail(BaseModel):
    """Per-call cost record."""
    call_id: str
    agent: str
    model: str
    reasoning_effort: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    timestamp: float


class DetailedCostReport(BaseModel):
    """Detailed cost report for a research session."""
    session_id: str
    total_usd: float
    by_model: dict[str, float]
    by_agent: dict[str, float]
    call_count: int
    cache_savings_estimate_usd: float
    calls: list[CostDetail]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.4.0"


# -- Settings --

class SettingsUpdate(BaseModel):
    """Settings update request — only set fields are updated."""
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    zotero_library_id: str | None = None
    zotero_api_key: str | None = None
    zotero_library_type: str | None = None
    cost_budget_usd: float | None = None
    llm_backend: str | None = None  # "api" or "cli"


class SettingsResponse(BaseModel):
    """Returns masked keys and config — never exposes full keys."""
    openai_api_key: str  # masked, e.g. "sk-...abc"
    anthropic_api_key: str
    google_api_key: str
    zotero_library_id: str
    zotero_api_key: str
    zotero_library_type: str
    cost_budget_usd: float
    llm_backend: str  # "api" or "cli"


class ProviderTestResult(BaseModel):
    provider: str
    ok: bool
    message: str


class SettingsTestResponse(BaseModel):
    results: list[ProviderTestResult]


# -- Sessions --

class SessionListItem(BaseModel):
    session_id: str
    status: str
    question: str
    cost_so_far: float


# -- Zotero --

class ZoteroCollection(BaseModel):
    key: str
    name: str
    num_items: int
