# AGENTS.md

## Roles

### Claude
Claude is the implementation agent.
Claude should:
- work on feature branches only
- make small commits
- update `/ai/claude_implementation_log.md`
- run tests before opening PRs
- avoid unrelated refactors

### Codex
Codex is the review/supervision agent.
Codex should:
- review PR diffs
- check correctness, tests, security, maintainability
- identify missed edge cases
- avoid rewriting large parts unless necessary
- provide actionable review comments

## Rules
- No direct commits to `main`.
- Every change must go through PR.
- All generated changes must pass CI.
- If tests are missing, reviewer should request tests.
- Large changes should be split into smaller PRs.

## Project commands
```bash
npm install
npm test
npm run lint
npm run build
```
