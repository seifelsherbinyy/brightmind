# Changelog / TODO for Live API Integration

## Completed now
- Local gateway start/health verified.
- Deterministic `/chat` smoke test verified.
- Adapter dry-run health and chat-completion stub verified.
- Machine-readable readiness report generated.

## Remaining for live integration
1. Configure Slack tokens in `.env`:
   - `SLACK_BOT_TOKEN=xoxb-...`
   - `SLACK_APP_TOKEN=xapp-...`
2. Validate Slack app scopes and Socket Mode settings.
3. Switch adapter from dry-run to live only after token validation and repeated smoke pass.
4. Add integration smoke tests for real Slack roundtrip in controlled workspace.

## Safe enablement sequence
```powershell
# 1) set tokens in .env (manually)
# 2) verify baseline
.\scripts\brightmind_stack_verify.ps1 -Command All
# 3) enable live bot startup path when ready
.\scripts\run_all.ps1
```

## Rollback
If live integration fails:
1. Stop stack: `.\scripts\brightmind_stack_verify.ps1 -Command Stop`
2. Re-run local-only readiness: `.\scripts\brightmind_stack_verify.ps1 -Command All`
3. Keep `OPENCLAW_DRY_RUN=true` and `-NoSlackBot` until stable.
