# Cursor Codex Runbook - BrightMind

Version: 1.1

## Terminal Sequence (copy/paste)
```powershell
cd D:\brightmind
./scripts/bootstrap.ps1
./scripts/doctor.ps1
./scripts/download_model.ps1 -Model "qwen2.5-coder:7b" -Force
./scripts/run_all.ps1
```

## Required Manual Step
Edit `.env` before starting services:
- `SLACK_BOT_TOKEN=xoxb-...`
- `SLACK_APP_TOKEN=xapp-...`

## Expected Checks
1. `doctor.ps1` returns exit code `0` for `READY` or `READY_WITH_WARNINGS`.
2. `curl http://localhost:8080/health` returns JSON with readiness.
3. Slack DM / mention gets a response.

## Failure Hints
- Placeholder tokens -> `doctor` fails.
- Missing model -> gateway returns download command.
- C: path drift -> set `OLLAMA_MODELS` to `D:\ollama\models`.

## Optional OpenClaw
- Enable in `.env`:
  - `OPENCLAW_ENABLED=true`
  - `OPENCLAW_DRY_RUN=true` for contract testing
- Adapter endpoint: `http://localhost:8081/v1/chat/completions`

## Source Links (accessed 2026-02-24)
- https://docs.openclaw.ai/
- https://docs.openclaw.ai/providers/ollama
- https://docs.slack.dev/apis/events-api/using-socket-mode
