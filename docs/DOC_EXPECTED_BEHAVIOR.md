# Doc-Expected Behavior Checklist

| Surface | Expected behavior (from docs) | Verification test in Brightmind |
|---|---|---|
| Slack Socket Mode | Local apps can receive events over WebSocket without public request URL | Deferred for live integration; token checks reported as UNKNOWN until configured |
| Slack `app_mention` event | App receives mention events when subscribed and authorized | Deferred for live integration |
| Slack scopes | `chat.write` and `app_mentions.read` required for bot messaging/mentions | Deferred for live integration |
| Ollama Windows runtime | Local runtime available on Windows and callable via CLI/API | `OLLAMA_VERSION` and `MODEL_AVAILABLE` checks |
| Ollama model path env | `OLLAMA_MODELS` controls model storage location | validated by existing doctor script and local bootstrap behavior |
| Ollama API health/list/chat | local service responds to model list and chat operations | gateway `/health` and `/chat` smoke checks |
| OpenClaw docs + providers | OpenClaw supports provider/channel configuration, including Slack and Ollama paths | adapter `/health` and `/v1/chat/completions` dry-run check |

## Sources
- https://docs.slack.dev/apis/events-api/using-socket-mode
- https://docs.slack.dev/reference/events/app_mention
- https://docs.slack.dev/reference/scopes/chat.write
- https://docs.slack.dev/reference/scopes/app_mentions.read
- https://docs.ollama.com/windows
- https://docs.ollama.com/faq
- https://docs.openclaw.ai/
- https://docs.openclaw.ai/channels/slack
- https://docs.openclaw.ai/providers/ollama
