"""Application configuration and model pricing tables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # API Keys
    openai_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://scienceai:scienceai@localhost:5432/scienceai"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # Embedding
    openai_embedding_model: str = "text-embedding-3-large"
    embedding_dimension: int = 1536

    # Zotero
    zotero_library_id: str = ""
    zotero_api_key: str = ""
    zotero_library_type: str = "user"  # "user" or "group"

    # LLM Backend: "api" (paid, via litellm) or "cli" (free, via local CLI tools)
    llm_backend: str = "cli"
    cli_codex_command: str = "codex"
    cli_gemini_command: str = "gemini"
    cli_claude_command: str = "claude"
    cli_timeout_seconds: int = 240

    # Cost budget (USD) — pipeline stops if exceeded
    cost_budget_usd: float = Field(default=10.0)


# ---------------------------------------------------------------------------
# Model registry: maps model IDs to their pricing and capabilities
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, dict] = {
    "gpt-5.4": {
        "provider": "openai",
        "input_per_m": 2.50,
        "output_per_m": 15.00,
        "cached_input_per_m": 0.25,
        "context_window": 1_050_000,
        "max_output": 128_000,
        "supports_reasoning_effort": True,
        "supports_tool_search": True,
    },
    "gemini/gemini-3.1-pro": {
        "provider": "google",
        "input_per_m": 2.00,
        "output_per_m": 12.00,
        "cached_input_per_m": 0.50,
        "context_window": 1_000_000,
        "max_output": 65_000,
        "supports_reasoning_effort": True,
        "supports_tool_search": False,
    },
    "claude-opus-4-6": {
        "provider": "anthropic",
        "input_per_m": 5.00,
        "output_per_m": 25.00,
        "cached_input_per_m": 0.50,  # read price (0.1x)
        "context_window": 1_000_000,
        "max_output": 128_000,
        "supports_reasoning_effort": True,
        "supports_tool_search": False,
    },
    "claude-sonnet-4-6": {
        "provider": "anthropic",
        "input_per_m": 3.00,
        "output_per_m": 15.00,
        "cached_input_per_m": 0.30,
        "context_window": 1_000_000,
        "max_output": 64_000,
        "supports_reasoning_effort": True,
        "supports_tool_search": False,
    },
    # CLI backends (free — $0.00 per call)
    "cli:codex": {
        "provider": "cli",
        "input_per_m": 0.0,
        "output_per_m": 0.0,
        "cached_input_per_m": 0.0,
        "context_window": 200_000,
        "max_output": 32_000,
        "supports_reasoning_effort": False,
        "supports_tool_search": False,
    },
    "cli:gemini": {
        "provider": "cli",
        "input_per_m": 0.0,
        "output_per_m": 0.0,
        "cached_input_per_m": 0.0,
        "context_window": 1_000_000,
        "max_output": 65_000,
        "supports_reasoning_effort": False,
        "supports_tool_search": False,
    },
    "cli:claude": {
        "provider": "cli",
        "input_per_m": 0.0,
        "output_per_m": 0.0,
        "cached_input_per_m": 0.0,
        "context_window": 200_000,
        "max_output": 128_000,
        "supports_reasoning_effort": False,
        "supports_tool_search": False,
    },
}

# ---------------------------------------------------------------------------
# Task → model routing defaults
# ---------------------------------------------------------------------------

TASK_MODEL_MAP: dict[str, dict] = {
    "query_planning": {"model": "gpt-5.4", "reasoning_effort": "medium"},
    "task_routing": {"model": "gpt-5.4", "reasoning_effort": "low"},
    "paper_triage": {"model": "gemini/gemini-3.1-pro", "reasoning_effort": "low"},
    "deep_read_high": {"model": "claude-opus-4-6", "reasoning_effort": "high"},
    "deep_read_medium": {"model": "claude-sonnet-4-6", "reasoning_effort": "medium"},
    "critique": {"model": "claude-opus-4-6", "reasoning_effort": "high"},
    "gap_detection": {"model": "gpt-5.4", "reasoning_effort": "high"},
    "verification": {"model": "claude-sonnet-4-6", "reasoning_effort": "medium"},
    "idea_generation": {"model": "gpt-5.4", "reasoning_effort": "medium"},
    "experiment_planning": {"model": "gpt-5.4", "reasoning_effort": "medium"},
    "report_writing": {"model": "claude-opus-4-6", "reasoning_effort": "high"},
}


settings = Settings()
