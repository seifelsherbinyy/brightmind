# Runbook - BrightMind

Version: 1.1

## Day-0 Setup
1. `cd D:\brightmind`
2. `./scripts/bootstrap.ps1`
3. Edit `.env` and set real `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`.
4. `./scripts/doctor.ps1`
5. `./scripts/download_model.ps1 -Model "qwen2.5-coder:7b" -Force`
6. `./scripts/run_all.ps1`

## Day-2 Operations
- Stop services: `./scripts/run_all.ps1 -Stop`
- Restart services: `./scripts/run_all.ps1 -Restart`
- Health checks:
  - `curl http://localhost:8080/health`
  - `curl http://localhost:8081/health` (if adapter enabled)
- Logs: `Get-Content .\logs\llm_gateway.log -Wait`

## Troubleshooting Matrix
| Symptom | Check | Fix |
|---|---|---|
| `doctor` FAIL on Slack tokens | `.env` values | Replace placeholders with real `xoxb-` and `xapp-` tokens |
| Gateway says model unavailable | `ollama list` | Run `download_model.ps1` for that model |
| D: storage warning | `OLLAMA_MODELS` user env var | Set to `D:\ollama\models` |
| Slack bot no response | `logs/slack_bot.log` | Verify Socket Mode and scopes |
| Adapter unavailable | `OPENCLAW_ENABLED` and `OPENCLAW_DRY_RUN` | Enable or keep disabled; direct mode still valid |

## Expected Outputs
- `doctor.ps1`: `READY`, `READY_WITH_WARNINGS`, or `NOT_READY`.
- Gateway `/health`: includes `status`, `readiness`, and `hint` when degraded.

## Source Links (accessed 2026-02-24)
- https://docs.ollama.com/windows
- https://docs.ollama.com/faq
- https://docs.slack.dev/apis/events-api/using-socket-mode
- https://docs.openclaw.ai/channels/slack
