# Security - BrightMind

Version: 1.1

## Secret Handling
- Store tokens only in `.env`.
- `.env` is gitignored.
- Never hardcode tokens in scripts or Python files.

## Required Slack Scopes (least privilege)
- `app_mentions:read`
- `chat:write`
- `im:history`
- `im:write`
- App token scope: `connections:write`

## Network Posture
- Gateway binds to `127.0.0.1` by default.
- Adapter binds to `127.0.0.1` by default.
- No public webhook required in Socket Mode.

## Input/Output Safety
- Slack input is sanitized and rate-limited.
- Adapter supports `dry_run` for safe contract testing.

## Operational Checks
- `doctor.ps1` fails when Slack tokens are placeholder/invalid.
- `doctor.ps1` warns/fails when heavy paths drift from D:.

## OpenClaw Security Note
OpenClaw integration is optional and isolated behind `openclaw_adapter`.
Unknown API behavior is tracked in `docs/OPENCLAW_CONTRACT.md`.

## Sources (accessed 2026-02-24)
- https://docs.slack.dev/apis/events-api/using-socket-mode
- https://docs.slack.dev/reference/scopes/chat.write
- https://docs.slack.dev/reference/scopes/app_mentions.read
- https://docs.openclaw.ai/
