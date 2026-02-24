# Architecture - BrightMind

Version: 1.1

## Components
- `services/slack_bot`: Slack Bolt Socket Mode consumer.
- `services/llm_gateway`: FastAPI gateway for local Ollama.
- `services/openclaw_adapter`: OpenAI-compatible bridge with dry-run mode.
- `services/common`: config, logging, message IDs.

## Flow A: Direct Local
1. Slack user DM or `@mention` event arrives via Socket Mode.
2. `slack_bot` sanitizes and rate-limits input.
3. `slack_bot` calls `llm_gateway /chat`.
4. `llm_gateway` calls Ollama `/api/chat`.
5. Response is returned to Slack.

## Flow B: OpenClaw Orchestrated (external)
1. External OpenClaw platform calls `openclaw_adapter`.
2. Adapter maps request to gateway-compatible payload.
3. In dry-run mode, adapter returns deterministic stub response.
4. In active mode, adapter forwards to `llm_gateway`.

## Flow C: Slack via OpenClaw Adapter
1. Slack event arrives via Socket Mode (same as Flow A).
2. `slack_bot` checks `OPENCLAW_ENABLED`. If *true*, routes to `openclaw_adapter`.
3. Adapter processes the request (dry-run stub or live forwarding to `llm_gateway`).
4. If the adapter call fails, `slack_bot` falls back to direct `llm_gateway` (Flow A).
5. Response is returned to Slack.

## Service Interfaces
- `GET /health` (gateway): returns `status`, `readiness`, `ollama`, `hint`.
- `POST /chat` (gateway): local completion.
- `POST /chat/stream` (gateway): SSE stream.
- `GET /models` (gateway): discovered/default/fallback models.
- `GET /v1/models` (adapter): OpenAI-compatible model list.
- `POST /v1/chat/completions` (adapter): OpenAI-compatible completion.

## Config Layering
Order of precedence:
1. Hardcoded defaults
2. `config/config.yaml`
3. `.env`
4. process env vars

## Path Strategy
- Repo root auto-resolved from code/script location.
- Heavy paths default to D: (`OLLAMA_MODELS`, data/log/cache policy).
- Scripts avoid hardcoded `D:\brightmind` assumptions.

## Failure Modes
- Missing model: gateway returns clear command for `download_model.ps1`.
- Missing Slack tokens: doctor fails deterministically.
- OpenClaw unavailable: direct mode still works.
- Adapter failure in Flow C: `slack_bot` automatically falls back to direct gateway.
