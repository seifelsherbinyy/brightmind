# BrightMind

BrightMind is a Windows-first local LLM foundation repo for Slack messaging with an optional OpenClaw bridge.

## Modes
- Direct Local: Slack -> `slack_bot` -> `llm_gateway` -> Ollama
- OpenClaw Orchestrated: Slack/OpenClaw -> `openclaw_adapter` -> `llm_gateway` -> Ollama

## Quick Start
1. `cd D:\brightmind`
2. `./scripts/bootstrap.ps1`
3. Edit `.env` with real Slack tokens.
4. `./scripts/doctor.ps1`
5. `./scripts/download_model.ps1 -Model "qwen2.5-coder:7b" -Force`
6. `./scripts/run_all.ps1`

## Defaults
- Runtime: Ollama
- Default model: `qwen2.5-coder:7b` (quality-first)
- Fallback model: `llama3.2:3b`
- Heavy storage target: `D:`

## Core Endpoints
- LLM health: `http://localhost:8080/health`
- LLM chat: `http://localhost:8080/chat`
- OpenClaw adapter health: `http://localhost:8081/health`
- OpenClaw adapter chat: `http://localhost:8081/v1/chat/completions`

## Repo Tree (deterministic snapshot)
```text
brightmind/
  config/
    config.example.yaml
  docs/
    ARCHITECTURE.md
    CURSOR_CODEX_RUNBOOK.md
    OPENCLAW_CONTRACT.md
    PRD.md
    RUNBOOK.md
    SECURITY.md
  scripts/
    bootstrap.ps1
    doctor.ps1
    download_model.ps1
    run_all.ps1
  services/
    common/
    llm_gateway/
    openclaw_adapter/
    slack_bot/
  .env.example
  .gitignore
  LICENSE
  README.md
```

## Sources
- OpenClaw docs: https://docs.openclaw.ai/
- OpenClaw Slack channel docs: https://docs.openclaw.ai/channels/slack
- OpenClaw Ollama provider docs: https://docs.openclaw.ai/providers/ollama
- OpenClaw install script endpoint: https://openclaw.ai/install.ps1
- Slack Socket Mode: https://docs.slack.dev/apis/events-api/using-socket-mode
- Slack app mention event: https://docs.slack.dev/reference/events/app_mention
- Slack `chat:write` scope: https://docs.slack.dev/reference/scopes/chat.write
- Slack `app_mentions:read` scope: https://docs.slack.dev/reference/scopes/app_mentions.read
- Ollama Windows docs: https://docs.ollama.com/windows
- Ollama FAQ (`OLLAMA_MODELS`): https://docs.ollama.com/faq
