# Brightmind Local Stack Runbook (v1.0)

## 1. Purpose
This runbook executes one-command startup + verification for local mode, then produces a go/no-go report.

## 2. Preconditions
1. Windows PowerShell available.
2. Repo exists at `D:\brightmind` (or pass `-RepoPath`).
3. Python and Ollama installed.
4. Model `qwen2.5-coder:7b` available (or set `OLLAMA_DEFAULT_MODEL`).

## 3. One-command flow
```powershell
cd D:\brightmind
.\scripts\brightmind_stack_verify.ps1 -Command All
```

Expected:
1. Starts gateway via `run_all.ps1 -NoSlackBot -NoOpenClawAdapter`.
2. Starts adapter in dry-run mode for validation.
3. Runs health checks and smoke tests.
4. Writes artifacts and `readiness_report.json`.
5. Stops started processes unless `-KeepRunning` is set.

## 4. Subcommands
```powershell
.\scripts\brightmind_stack_verify.ps1 -Command Start
.\scripts\brightmind_stack_verify.ps1 -Command Verify
.\scripts\brightmind_stack_verify.ps1 -Command SmokeTest
.\scripts\brightmind_stack_verify.ps1 -Command Report
.\scripts\brightmind_stack_verify.ps1 -Command Stop
.\scripts\brightmind_stack_verify.ps1 -Command Clean
```

## 5. Exit codes
- `0`: pass (or pass with UNKNOWN non-blockers)
- `10`: prerequisite failure
- `20`: startup failure
- `30`: health/model failure
- `40`: smoke test failure
- `50`: security posture failure
- `60`: other failure
- `99`: unhandled script exception

## 6. Artifact locations
- Latest machine-readable report: `artifacts\readiness\readiness_report.json`
- Per-run artifacts: `artifacts\readiness\<timestamp>\`

## 7. Minimal diagnostics branch
If `All` fails, run:
```powershell
.\scripts\brightmind_stack_verify.ps1 -Command Start -KeepRunning
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8081/health
Get-Content .\logs\llm_gateway.err.log -Tail 120
Get-Content .\logs\openclaw_adapter.err.log -Tail 120
.\scripts\brightmind_stack_verify.ps1 -Command Stop
```

## 8. Safety defaults
- No secrets printed.
- Localhost-only check enforced (`127.0.0.1` / `localhost` / `::1`).
- Slack credentials are optional for offline mode and reported as `UNKNOWN` until configured.
