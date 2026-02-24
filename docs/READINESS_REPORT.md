# Brightmind Readiness Report (v1.0)

Generated from: `artifacts/readiness/readiness_report.json`

## Summary
- Local mode go/no-go: **GO**
- Live integration go/no-go: **NO-GO** (Slack credentials intentionally deferred)

## Pass/Fail Table
| check_id | category | status | severity | evidence | remediation |
|---|---|---|---|---|---|
| REPO_RUNALL | repo | PASS | critical | run_all.ps1 present | none |
| API_GATEWAY_HEALTH | service | PASS | critical | status=ok readiness=ready | none |
| OPENCLAW_ADAPTER_HEALTH | service | PASS | high | status=ok mode=dry_run | none |
| PYTHON_VERSION | deps | PASS | critical | Python 3.12.4 | none |
| OLLAMA_VERSION | deps | PASS | critical | ollama version is 0.17.0 | none |
| MODEL_AVAILABLE | model | PASS | critical | model qwen2.5-coder:7b present | none |
| SLACK_CREDS_READY | integration | UNKNOWN | high | tokens not configured (offline mode) | configure for live integration later |
| GATEWAY_BIND_LOCALHOST | security | PASS | critical | bind 127.0.0.1:8080 | none |
| ADAPTER_BIND_LOCALHOST | security | PASS | critical | bind 127.0.0.1:8081 | none |
| SMOKE_GATEWAY_CHAT | smoke | PASS | critical | deterministic ok | none |
| PERF_CHAT_LATENCY | performance | PASS | medium | latency within target | none |
| SMOKE_ADAPTER_DRY_RUN | smoke | PASS | high | dry-run marker found | none |

## Machine-readable JSON
`readiness_report.json` schema:
- `title`
- `version`
- `generated_at`
- `repo_path`
- `artifacts_path`
- `verdict.local_mode_go`
- `verdict.live_integration_go`
- `verdict.pass_count`
- `verdict.fail_count`
- `verdict.unknown_count`
- `environment` (versions, models, endpoints)
- `checks[]` with `check_id/category/status/severity/evidence/remediation/commands_run/failure_code`

Use latest file:
```powershell
Get-Content -Raw .\artifacts\readiness\readiness_report.json
```
