# AGENTS.md

## Cursor Cloud specific instructions

### Overview

BrightMind is a local-LLM Slack assistant with three Python services under `services/`:

| Service | Port | Role |
|---|---|---|
| `llm_gateway` | 8080 | FastAPI proxy to Ollama (core) |
| `slack_bot` | N/A | Slack Bolt Socket Mode bot |
| `openclaw_adapter` | 8081 | Optional OpenAI-compatible bridge (dry-run by default) |

### Running services (Linux)

All services require a `.env` file at the repo root (copy from `.env.example` and adjust paths for Linux). The config module auto-discovers it via `services/common/config.py`.

```bash
# Activate the venv
source .venv/bin/activate

# Start Ollama (required backend for llm_gateway)
OLLAMA_MODELS=/workspace/.ollama/models ollama serve &

# Start llm_gateway
python services/llm_gateway/app.py &

# Start openclaw_adapter (optional, runs in dry_run mode by default)
# Set OPENCLAW_ENABLED=true in .env to start it
python services/openclaw_adapter/app.py &

# slack_bot requires real SLACK_BOT_TOKEN and SLACK_APP_TOKEN in .env
python services/slack_bot/app.py
```

### Key gotchas

- **Windows-first repo**: All automation scripts (`scripts/*.ps1`) are PowerShell/Windows. On Linux, run the Python services directly as shown above.
- **No Makefile, no Docker**: Services run as bare Python processes.
- **`common` package**: Must be installed as editable (`pip install -e services/common`) before any service can import from `common.*`.
- **Config resolution**: `services/common/config.py` reads `.env` then `config/config.yaml` (defaults to `config/config.example.yaml`). Set `BRIGHTMIND_CONFIG_PATH` in `.env` to use a custom YAML config.
- **No automated tests**: The repo has no test files. Linting via `ruff check services/` is the only static check available.
- **Ollama model**: At least one Ollama model must be pulled before `llm_gateway` can serve chat requests. Use `ollama pull <model>` (e.g. `qwen2.5-coder:0.5b` for a lightweight option).
- **Slack tokens**: The `slack_bot` service exits immediately if `SLACK_BOT_TOKEN` or `SLACK_APP_TOKEN` are not set to valid values.

### Linting

```bash
source .venv/bin/activate
ruff check services/
```

### Health checks

```bash
curl http://localhost:8080/health   # llm_gateway
curl http://localhost:8081/health   # openclaw_adapter (if enabled)
```
