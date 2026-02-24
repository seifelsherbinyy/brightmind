# OpenClaw Contract - BrightMind Adapter

Version: 1.1

## Verified (from docs)
- OpenClaw has documentation at `https://docs.openclaw.ai/`.
- Slack channel integration docs exist at `https://docs.openclaw.ai/channels/slack`.
- Ollama provider docs exist at `https://docs.openclaw.ai/providers/ollama`.
- Install script endpoint is published at `https://openclaw.ai/install.ps1`.

## Adapter Contract Implemented Here
- Health: `GET /health`
- Model listing: `GET /v1/models`
- Chat completions: `POST /v1/chat/completions`
- Mode control:
  - `OPENCLAW_ENABLED` gates service startup.
  - `OPENCLAW_DRY_RUN=true` returns deterministic stub responses.

## Explicitly Unverified / Deferred
- Any undocumented OpenClaw auth handshake beyond provided docs pages.
- Any undocumented provider registration API outside config-driven local setup.
- Any undocumented webhook/callback contract not stated in docs above.

## Fallback Rules
- If OpenClaw contract details are unavailable, keep Direct Local mode as source of truth.
- Do not invent required OpenClaw fields; document missing fields and keep adapter stub-safe.

## Test Scenarios
1. `OPENCLAW_ENABLED=true`, `OPENCLAW_DRY_RUN=true`: `/v1/chat/completions` returns stub marker.
2. `OPENCLAW_ENABLED=true`, `OPENCLAW_DRY_RUN=false`: forwards to `llm_gateway`.
3. `OPENCLAW_ENABLED=false`: service should not run; direct mode remains unaffected.
