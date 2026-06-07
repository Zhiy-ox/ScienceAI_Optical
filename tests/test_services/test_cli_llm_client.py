"""Tests for the CLI LLM client routing and command construction."""

from science_ai.services.cli_llm_client import CLILLMClient


def test_cli_routes_bulk_tasks_to_antigravity() -> None:
    client = CLILLMClient(antigravity_cmd="agy")

    assert client._resolve_cli("paper_triage") == "antigravity"
    assert client._resolve_cli("verification") == "antigravity"


def test_antigravity_command_uses_one_shot_prompt_flag() -> None:
    client = CLILLMClient(antigravity_cmd="agy")

    cmd, use_stdin = client._build_command("antigravity", "Review this paper")

    assert cmd == ["agy", "-p", "Review this paper"]
    assert use_stdin is False
