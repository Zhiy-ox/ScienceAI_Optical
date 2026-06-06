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
    stream: bool = Field(default=False, description="If true (graph mode), defer execution to the SSE /stream endpoint")
    hitl_gates: list[str] = Field(default_factory=list, description="Approval gates to pause at, e.g. ['plan', 'gaps']")


class ResumeRequest(BaseModel):
    """Resume an interrupted (awaiting-input) session at a HITL gate."""
    action: str = Field(default="approve", description="'approve' | 'edit' | 'reject'")
    plan: dict | None = Field(default=None, description="Edited plan (when action='edit' at the plan gate)")
    verified_gaps: list[dict] | None = Field(default=None, description="Edited gaps (when action='edit' at the gaps gate)")


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
    interrupt: dict | None = None  # populated when status == "awaiting_input"


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


# -- Streaming --

class StreamEvent(BaseModel):
    """A single SSE event payload (documents the wire format).

    event types: "progress" (human-readable stage update),
    "node" (a graph node finished), "done" (terminal), "error".
    """
    event: str
    stage: str | None = None
    msg: str | None = None
    status: str | None = None
    data: dict | None = None


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
