# PRD - BrightMind Foundation

Version: 1.1  
Date: 2026-02-24

## Environment Contract
- OS: Windows 11
- RAM: 16GB
- GPU: RTX 3050 4GB
- Constraint: C: is low space, heavy assets must target D:

## Problem
Need a local LLM Slack assistant with optional OpenClaw orchestration, deployable with PowerShell automation and no hardcoded secrets.

## Goals
- Bootstrap idempotently on Windows.
- Keep Direct Local mode operational without OpenClaw credentials.
- Support OpenClaw adapter mode with verified stub contract.
- Validate D:-drive usage and token readiness using `doctor.ps1`.

## Non-Goals
- Production-grade distributed orchestration.
- Full OpenClaw feature parity beyond documented bridge surfaces.
- RAG/vector DB in v1.1.

## Personas and User Stories
- Developer: run local assistant from Slack with minimal setup.
- Operator: diagnose quickly with PASS/FAIL checks.
- Integrator: enable OpenClaw later without breaking direct mode.

## Functional Requirements
- `bootstrap.ps1`: path-safe setup + deps + env bootstrap.
- `doctor.ps1`: deterministic checks and exit codes.
- `run_all.ps1`: starts services, tracks PID map, clean stop.
- `download_model.ps1`: size-aware safe model pull.
- `llm_gateway`: `/health`, `/chat`, `/chat/stream`, `/models`.
- `openclaw_adapter`: `/health`, `/v1/models`, `/v1/chat/completions` with dry-run mode.

## Non-Functional Requirements
- No secret hardcoding.
- Structured logs under repo `logs/`.
- Default model quality-first 7B with documented 3B fallback.

## Acceptance Criteria
- Direct Local mode works end-to-end with real Slack tokens and local model.
- `doctor.ps1` fails on placeholder/missing Slack tokens.
- Model/gateway errors provide actionable next steps.
- OpenClaw behavior is documented as verified vs unverified contract items.

## Milestones
- Phase 0: hardening + docs alignment (this release)
- Phase 1: OpenClaw live integration once contract unknowns are resolved
- Phase 2: optional persistence, metrics, richer routing

## Risks
- Ollama/model mismatch -> mitigate with clear model download guidance.
- Slack token misconfiguration -> mitigate with strict doctor validation.
- OpenClaw API evolution -> mitigate via isolated adapter + contract doc.

## Telemetry and Logging
- Service logs per process in `logs/*.log`.
- Health endpoint returns readiness + hints.

## Security
See `docs/SECURITY.md` for secret handling and least privilege scopes.

## Sources (accessed 2026-02-24)
- https://docs.openclaw.ai/
- https://docs.openclaw.ai/channels/slack
- https://docs.openclaw.ai/providers/ollama
- https://openclaw.ai/install.ps1
- https://docs.slack.dev/apis/events-api/using-socket-mode
- https://docs.slack.dev/reference/events/app_mention
- https://docs.slack.dev/reference/scopes/chat.write
- https://docs.slack.dev/reference/scopes/app_mentions.read
- https://docs.ollama.com/windows
- https://docs.ollama.com/faq
