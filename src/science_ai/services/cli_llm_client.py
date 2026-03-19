"""CLI-based LLM client — calls Gemini CLI, Codex CLI, and Claude Code via subprocess.

Drop-in replacement for LLMClient that routes tasks to locally-installed CLI tools
instead of paid API endpoints. Cost is $0.00 per call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from science_ai.cost.tracker import CostTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task → CLI tool routing
# ---------------------------------------------------------------------------

CLI_TASK_MAP: dict[str, str] = {
    "query_planning":     "codex",    # fast structured planning
    "task_routing":       "codex",    # simple routing decisions
    "paper_triage":       "gemini",   # bulk processing, large context
    "deep_read_high":     "claude",   # deep analysis, long-form extraction
    "deep_read_medium":   "claude",   # deep analysis
    "critique":           "claude",   # critical thinking
    "gap_detection":      "codex",    # multi-mechanism synthesis
    "verification":       "gemini",   # search + verification
    "idea_generation":    "codex",    # creative generation
    "experiment_planning": "codex",   # structured planning
    "report_writing":     "claude",   # long-form writing
}

# Fallback if task_type is unknown
DEFAULT_CLI = "claude"


class CLILLMClient:
    """LLM client that delegates to CLI tools via subprocess.

    Implements the same interface as LLMClient (complete / complete_json)
    so it can be used as a drop-in replacement. All agents work unchanged.
    """

    def __init__(
        self,
        cost_tracker: CostTracker | None = None,
        codex_cmd: str = "codex",
        gemini_cmd: str = "gemini",
        claude_cmd: str = "claude",
        timeout: int = 120,
    ) -> None:
        self.cost_tracker = cost_tracker or CostTracker()
        self.codex_cmd = codex_cmd
        self.gemini_cmd = gemini_cmd
        self.claude_cmd = claude_cmd
        self.timeout = timeout

        # Batch queue (mirrors LLMClient interface)
        self._batch_queue: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Main interface — matches LLMClient exactly
    # ------------------------------------------------------------------

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        agent_name: str = "unknown",
        session_id: str | None = None,
        enable_cache: bool = True,
    ) -> dict[str, Any]:
        """Run a prompt through the appropriate CLI tool."""
        cli_tool = self._resolve_cli(task_type)
        prompt = self._build_prompt(messages)

        logger.info(
            "CLI call: tool=%s task=%s agent=%s prompt_len=%d",
            cli_tool, task_type, agent_name, len(prompt),
        )

        content = await self._run_cli(cli_tool, prompt)

        # Estimate token counts (rough: 1 token ≈ 4 chars)
        input_tokens = len(prompt) // 4
        output_tokens = len(content) // 4

        # Record in cost tracker (free — $0.00)
        if self.cost_tracker and session_id:
            self.cost_tracker.record_call(
                session_id=session_id,
                agent=agent_name,
                model=f"cli:{cli_tool}",
                reasoning_effort=reasoning_effort or "n/a",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=0,
            )

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": 0,
            "cost_usd": 0.0,
            "model": f"cli:{cli_tool}",
        }

    async def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 4096,
        agent_name: str = "unknown",
        session_id: str | None = None,
        enable_cache: bool = True,
    ) -> dict[str, Any]:
        """Run a prompt and parse the response as JSON."""
        # Append JSON instruction to the last user message
        augmented = self._append_json_instruction(messages)

        result = await self.complete(
            messages=augmented,
            task_type=task_type,
            model=model,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            agent_name=agent_name,
            session_id=session_id,
            enable_cache=enable_cache,
        )

        parsed = self._extract_json(result["content"])
        result["parsed"] = parsed
        return result

    # ------------------------------------------------------------------
    # Batch API (mirrors LLMClient interface)
    # ------------------------------------------------------------------

    def queue_batch_request(
        self,
        *,
        messages: list[dict[str, str]],
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 4096,
        agent_name: str = "unknown",
        session_id: str | None = None,
        custom_id: str | None = None,
    ) -> str:
        """Queue a request for batch execution."""
        req_id = custom_id or f"batch-{len(self._batch_queue)}"
        self._batch_queue.append({
            "custom_id": req_id,
            "messages": messages,
            "task_type": task_type,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "max_tokens": max_tokens,
            "agent_name": agent_name,
            "session_id": session_id,
        })
        return req_id

    async def execute_batch(self) -> list[dict[str, Any]]:
        """Execute all queued requests concurrently."""
        queue = self._batch_queue[:]
        self._batch_queue.clear()

        # Run up to 5 CLI calls concurrently
        sem = asyncio.Semaphore(5)

        async def _run(req: dict) -> dict[str, Any]:
            async with sem:
                result = await self.complete_json(
                    messages=req["messages"],
                    task_type=req["task_type"],
                    model=req["model"],
                    reasoning_effort=req["reasoning_effort"],
                    max_tokens=req["max_tokens"],
                    agent_name=req["agent_name"],
                    session_id=req["session_id"],
                )
                result["custom_id"] = req["custom_id"]
                return result

        results = await asyncio.gather(*[_run(r) for r in queue], return_exceptions=True)

        final = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error("Batch request %s failed: %s", queue[i]["custom_id"], r)
                final.append({
                    "custom_id": queue[i]["custom_id"],
                    "content": "",
                    "parsed": {},
                    "error": str(r),
                })
            else:
                final.append(r)
        return final

    @property
    def batch_queue_size(self) -> int:
        return len(self._batch_queue)

    # ------------------------------------------------------------------
    # CLI execution
    # ------------------------------------------------------------------

    async def _run_cli(self, cli_tool: str, prompt: str) -> str:
        """Execute a CLI tool with the given prompt and return stdout."""
        cmd = self._build_command(cli_tool, prompt)

        logger.debug("Running CLI command: %s (prompt_len=%d)", cmd[0], len(prompt))
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # For gemini, send prompt via stdin
            stdin_data = prompt.encode() if cli_tool == "gemini" else None

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=self.timeout,
            )

            elapsed = time.monotonic() - start
            content = stdout.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(
                    "CLI %s failed (rc=%d, %.1fs): %s",
                    cli_tool, proc.returncode, elapsed, err_msg[:500],
                )
                raise RuntimeError(
                    f"CLI {cli_tool} exited with code {proc.returncode}: {err_msg[:200]}"
                )

            logger.info(
                "CLI %s completed in %.1fs, output_len=%d",
                cli_tool, elapsed, len(content),
            )
            return content

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            logger.error("CLI %s timed out after %.1fs", cli_tool, elapsed)
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"CLI {cli_tool} timed out after {self.timeout}s")

    def _build_command(self, cli_tool: str, prompt: str) -> list[str]:
        """Build the subprocess command for each CLI tool."""
        if cli_tool == "codex":
            # codex --quiet --prompt "..."
            return [self.codex_cmd, "--quiet", "--prompt", prompt]
        elif cli_tool == "gemini":
            # gemini reads from stdin
            return [self.gemini_cmd]
        elif cli_tool == "claude":
            # claude --print -p "..."
            return [self.claude_cmd, "--print", "-p", prompt]
        else:
            raise ValueError(f"Unknown CLI tool: {cli_tool}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_cli(self, task_type: str | None) -> str:
        """Map task_type to the CLI tool to use."""
        if task_type:
            return CLI_TASK_MAP.get(task_type, DEFAULT_CLI)
        return DEFAULT_CLI

    def _build_prompt(self, messages: list[dict[str, str]]) -> str:
        """Flatten OpenAI-style messages into a single prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System Instructions]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)

    def _append_json_instruction(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Copy messages and append a JSON-only instruction to the last user message."""
        messages = [dict(m) for m in messages]  # shallow copy each

        json_hint = (
            "\n\nIMPORTANT: Respond with valid JSON only. "
            "Do not include any text, markdown formatting, or explanation outside the JSON object."
        )

        # Append to last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                msg["content"] = msg["content"] + json_hint
                break
        else:
            # No user message found — append as new user message
            messages.append({"role": "user", "content": json_hint.strip()})

        return messages

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from CLI output, handling markdown code blocks."""
        text = text.strip()

        # 1. Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Try extracting from markdown code blocks
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. Try finding first { to last }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        # 4. Try first [ to last ] for arrays
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            try:
                parsed = json.loads(text[first_bracket:last_bracket + 1])
                if isinstance(parsed, list):
                    return {"results": parsed}
            except json.JSONDecodeError:
                pass

        logger.error("Failed to extract JSON from CLI output (len=%d): %s...", len(text), text[:200])
        raise ValueError(f"CLI output is not valid JSON. Output starts with: {text[:200]}")
