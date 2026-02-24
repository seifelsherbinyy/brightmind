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

### Routing modes

When `OPENCLAW_ENABLED=true` in `.env`, the `slack_bot` routes messages through the `openclaw_adapter` first (Flow C in `docs/ARCHITECTURE.md`). If the adapter is unavailable, it automatically falls back to calling `llm_gateway` directly. When `OPENCLAW_ENABLED=false`, messages go directly to the gateway (Flow A).

### Key gotchas

- **Windows-first repo**: All automation scripts (`scripts/*.ps1`) are PowerShell/Windows. On Linux, run the Python services directly as shown above.
- **No Makefile, no Docker**: Services run as bare Python processes.
- **`common` package**: Must be installed as editable (`pip install -e services/common`) before any service can import from `common.*`.
- **Config resolution**: `services/common/config.py` reads `.env` then `config/config.yaml` (defaults to `config/config.example.yaml`). Set `BRIGHTMIND_CONFIG_PATH` in `.env` to use a custom YAML config.
- **Config caching**: `get_settings()` uses `@lru_cache`, so env var changes after first import require a process restart.
- **No automated tests**: The repo has no test files. Linting via `ruff check services/` is the only static check available.
- **Ollama model**: At least one Ollama model must be pulled before `llm_gateway` can serve chat requests. Use `ollama pull <model>` (e.g. `qwen2.5-coder:0.5b` for a lightweight option).
- **Slack tokens**: The `slack_bot` service exits immediately if `SLACK_BOT_TOKEN` or `SLACK_APP_TOKEN` are not set to valid values. These are provided via environment secrets `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`. Write them into `.env` before starting the bot.
- **Slack bot import**: Importing `slack_bot.app` at module level triggers `App(token=...)` which calls `auth.test` against the Slack API. If the token is invalid/placeholder, the import itself raises `BoltError`. This means you cannot unit-test routing functions by importing the module without valid tokens; test via HTTP calls to the running services instead.
- **Slack scopes**: The bot token has `chat:write`, `app_mentions:read`, `im:read`, `channels:read` but **not** `channels:join` or `im:history`. It cannot join channels programmatically or read message history. Users must invite the bot to channels manually via Slack.
- **structlog warnings**: When running services inline (e.g. in test scripts), structlog may emit `AttributeError: 'NoneType' object has no attribute 'disabled'` warnings. These are harmless logging context clashes and do not affect functionality.

### Conversation memory

The `slack_bot` maintains per-thread message history via `ConversationStore` (in `services/common/conversation_store.py`). Conversations are keyed by `channel:thread_ts` (or just `channel` for top-level DMs). History is in-memory with 1-hour TTL and 20-message cap. No persistence across restarts (Phase 2 roadmap item).

### Tool / function calling

The bot sends tool definitions to Ollama alongside each request. When the model responds with `tool_calls`, the bot executes them and feeds results back in a loop (up to `BRIGHTMIND_MAX_TOOL_ROUNDS`, default 5). Built-in tools are defined in `services/slack_bot/tools.py`:

| Tool | Description |
|---|---|
| `get_current_datetime` | Returns current UTC date/time |
| `web_fetch` | Fetches a URL and returns the body text (max 4KB) |
| `service_status` | Checks health of gateway, adapter, and Ollama |
| `list_models` | Lists available Ollama models |
| `calculate` | Evaluates a math expression safely |

Tool calling quality depends on the model — `qwen2.5-coder:7b` handles it well; the 0.5b variant may not invoke tools reliably.

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
