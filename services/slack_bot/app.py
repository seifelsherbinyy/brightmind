"""Slack Bot - Bolt-based Slack integration for BrightMind.

Features:
- Conversation memory (thread-aware, per-channel / per-thread)
- Tool / function calling via Ollama (datetime, web_fetch, calc, …)
- Routing through OpenClaw adapter when enabled (with gateway fallback)
"""

import json
import sys
import os
from collections import defaultdict
from pathlib import Path
from time import time
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from common.config import get_settings
from common.conversation_store import ConversationStore
from common.logger import configure_logging, get_logger

# Configure logging
settings = get_settings()
log_dir = settings.paths.logs_dir
configure_logging(
    log_level=settings.log_level,
    log_dir=log_dir,
    service_name="slack_bot"
)
logger = get_logger(__name__)

# Rate limiting storage
rate_limits: Dict[str, List[float]] = defaultdict(list)
GATEWAY_TIMEOUT_SECONDS = float(os.getenv("BRIGHTMIND_GATEWAY_TIMEOUT_SEC", str(settings.ollama.timeout)))
GATEWAY_RETRIES = int(os.getenv("BRIGHTMIND_GATEWAY_RETRIES", "2"))
MAX_TOOL_ROUNDS = int(os.getenv("BRIGHTMIND_MAX_TOOL_ROUNDS", "5"))

# Conversation memory (in-memory, TTL = 1 hour, last 20 messages)
conversations = ConversationStore(max_messages=20, ttl_seconds=3600)

# Tool registry — imported lazily so module-level side-effects are minimal
from slack_bot.tools import execute_tool, get_tool_definitions  # noqa: E402


def check_rate_limit(user_id: str, max_requests: int = 30, window_seconds: int = 60) -> bool:
    """Check if user has exceeded rate limit.
    
    Args:
        user_id: Slack user ID
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
        
    Returns:
        True if request is allowed, False if rate limited
    """
    now = time()
    user_requests = rate_limits[user_id]
    
    # Remove old requests outside window
    user_requests[:] = [t for t in user_requests if now - t < window_seconds]
    
    if len(user_requests) >= max_requests:
        return False
    
    user_requests.append(now)
    return True


def sanitize_input(text: str, max_length: int = 4000) -> str:
    """Sanitize user input.
    
    Args:
        text: Input text
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
    """
    import re
    
    # Truncate
    text = text[:max_length]
    
    # Remove control characters
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)
    
    return text.strip()


SYSTEM_PROMPT = (
    "You are BrightMind, a helpful AI assistant running locally on the user's machine. "
    "You have access to tools you can call when needed: check the current date/time, "
    "fetch web pages, check service status, list available models, and do calculations. "
    "Use tools when they would help answer the user's question. "
    "Be concise but thorough in your responses."
)


async def _call_gateway(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Low-level call to the LLM Gateway. Returns the full response dict."""
    gateway_url = f"http://{settings.llm_gateway.host}:{settings.llm_gateway.port}"

    request_data: Dict[str, Any] = {
        "model": model or settings.ollama.default_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.ollama.temperature,
        "max_tokens": settings.ollama.max_tokens,
    }
    if tools:
        request_data["tools"] = tools

    for attempt in range(1, GATEWAY_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{gateway_url}/chat", json=request_data
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(
                    "LLM Gateway error",
                    status_code=response.status_code,
                    attempt=attempt,
                    response=response.text,
                )
                if attempt > GATEWAY_RETRIES:
                    return None
        except httpx.TimeoutException:
            logger.error("LLM Gateway timeout", attempt=attempt)
            if attempt > GATEWAY_RETRIES:
                return None
        except Exception as e:
            logger.error("LLM Gateway call failed", error=str(e), attempt=attempt)
            if attempt > GATEWAY_RETRIES:
                return None
    return None


async def _call_openclaw_adapter(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Call OpenClaw adapter and normalize response to gateway-like shape."""
    adapter_url = (
        f"http://{settings.openclaw_adapter.host}"
        f":{settings.openclaw_adapter.port}"
    )
    request_data: Dict[str, Any] = {
        "model": model or settings.ollama.default_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.ollama.temperature,
        "max_tokens": settings.ollama.max_tokens,
    }
    if tools:
        request_data["tools"] = tools

    for attempt in range(1, GATEWAY_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{adapter_url}/v1/chat/completions",
                    json=request_data,
                )
                if response.status_code == 200:
                    payload = response.json()
                    choices = payload.get("choices") or []
                    message = choices[0].get("message", {}) if choices else {}
                    return {
                        "id": payload.get("id", ""),
                        "model": payload.get("model", request_data["model"]),
                        "message": {
                            "role": message.get("role", "assistant"),
                            "content": message.get("content", ""),
                            "tool_calls": message.get("tool_calls"),
                        },
                        "usage": payload.get("usage", {}),
                    }

                logger.error(
                    "OpenClaw adapter error",
                    status_code=response.status_code,
                    attempt=attempt,
                    response=response.text,
                )
                if attempt > GATEWAY_RETRIES:
                    return None
        except httpx.TimeoutException:
            logger.error("OpenClaw adapter timeout", attempt=attempt)
            if attempt > GATEWAY_RETRIES:
                return None
        except Exception as e:
            logger.error("OpenClaw adapter call failed", error=str(e), attempt=attempt)
            if attempt > GATEWAY_RETRIES:
                return None
    return None


async def _call_llm_backend(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Call configured backend: adapter when enabled, else direct gateway."""
    if settings.openclaw_adapter.enabled:
        logger.info("Routing via OpenClaw adapter")
        adapter_response = await _call_openclaw_adapter(messages, model=model, tools=tools)
        if adapter_response is not None:
            return adapter_response
        logger.warning("OpenClaw adapter failed, falling back to direct gateway")

    return await _call_gateway(messages, model=model, tools=tools)


def _is_memory_reset_command(text: str) -> bool:
    return text.strip().lower() in {"reset", "reset memory", "/reset"}


async def get_llm_response(
    conversation_id: str,
    user_message: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """Send a message with full conversation history and tool support.

    1. Stores the user message in the conversation store.
    2. Builds the full message list (system + history).
    3. Calls the gateway with tool definitions.
    4. If the model requests tool calls, executes them and loops.
    5. Stores the final assistant reply and returns it.
    """
    prompt = system_prompt or SYSTEM_PROMPT
    conversations.append(conversation_id, "user", user_message)

    tools = get_tool_definitions()

    for _round in range(MAX_TOOL_ROUNDS):
        messages = conversations.get_history(conversation_id, system_prompt=prompt)
        data = await _call_llm_backend(messages, model=model, tools=tools)

        if data is None:
            return None

        assistant_msg = data.get("message", {})
        content = assistant_msg.get("content", "")
        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            if content:
                conversations.append(conversation_id, "assistant", content)
            return content or None

        logger.info("Tool calls requested", count=len(tool_calls))

        # Store the assistant's tool-call message in history
        conversations.append(
            conversation_id,
            "assistant",
            content or f"[calling {len(tool_calls)} tool(s)]",
        )

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}

            logger.info("Executing tool", tool=name, args=raw_args)
            result = execute_tool(name, raw_args)
            conversations.append(conversation_id, "tool", result)

    # Fell through the loop — do one final call without tools
    messages = conversations.get_history(conversation_id, system_prompt=prompt)
    data = await _call_llm_backend(messages, model=model)
    if data:
        content = data.get("message", {}).get("content", "")
        if content:
            conversations.append(conversation_id, "assistant", content)
        return content or None
    return None


# Initialize Bolt app
app = App(token=settings.slack.bot_token)


def _conversation_key(channel: str, thread_ts: Optional[str] = None) -> str:
    """Derive a conversation store key from channel and thread."""
    if thread_ts:
        return f"{channel}:{thread_ts}"
    return channel


@app.event("app_mention")
def handle_app_mention(event: dict, say, client):
    """Handle @mention in channels."""
    user = event.get("user", "unknown")
    channel = event.get("channel", "unknown")
    text = event.get("text", "")
    thread_ts = event.get("thread_ts") or event.get("ts")
    
    logger.info(
        "App mention received",
        user=user,
        channel=channel,
        text_preview=text[:100]
    )
    
    if not check_rate_limit(user):
        say(
            text="You're sending messages too quickly. Please wait a moment.",
            thread_ts=thread_ts
        )
        return
    
    text = sanitize_input(text)
    
    import re
    clean_text = re.sub(r'<@\w+>', '', text).strip()
    
    if not clean_text:
        say(text="Hello! How can I help you today?", thread_ts=thread_ts)
        return

    conv_id = _conversation_key(channel, thread_ts)
    if _is_memory_reset_command(clean_text):
        conversations.clear(conv_id)
        say(text="Conversation memory reset for this thread.", thread_ts=thread_ts)
        return
    
    try:
        client.assistant_threads_setStatus(
            thread_ts=thread_ts,
            channel_id=channel,
            status="is thinking..."
        )
    except Exception:
        pass

    import asyncio
    response = asyncio.run(get_llm_response(conv_id, clean_text))
    
    if response:
        say(text=response, thread_ts=thread_ts)
    else:
        say(
            text="Sorry, I encountered an error processing your request. Please try again later.",
            thread_ts=thread_ts
        )


@app.event("message")
def handle_message(event: dict, say, client):
    """Handle direct messages."""
    channel_type = event.get("channel_type", "")
    if channel_type != "im":
        return
    
    user = event.get("user", "unknown")
    channel = event.get("channel", "unknown")
    text = event.get("text", "")
    thread_ts = event.get("thread_ts") or event.get("ts")
    
    logger.info("DM received", user=user, text_preview=text[:100])
    
    if not check_rate_limit(user):
        say(text="You're sending messages too quickly. Please wait a moment.")
        return
    
    text = sanitize_input(text)
    
    if not text:
        say(text="Hello! How can I help you today?")
        return

    conv_id = _conversation_key(channel, thread_ts)
    if _is_memory_reset_command(text):
        conversations.clear(conv_id)
        say(text="Conversation memory reset for this DM thread.")
        return
    
    try:
        client.assistant_threads_setStatus(
            channel_id=channel,
            status="is thinking..."
        )
    except Exception:
        pass

    import asyncio
    response = asyncio.run(get_llm_response(conv_id, text))
    
    if response:
        say(text=response)
    else:
        say(text="Sorry, I encountered an error. Please ensure the LLM Gateway is running.")


@app.command("/brightmind")
def handle_command(ack, command: dict, say):
    """Handle slash command."""
    ack()
    
    user = command.get("user_id", "unknown")
    text = command.get("text", "").strip()
    
    logger.info("Slash command received", user=user, command=text)
    
    if text in ["help", "?", ""]:
        say(
            text="""*BrightMind Commands:*
• `/brightmind help` - Show this help
• `/brightmind status` - Check service status
• `/brightmind reset` - Reset slash-command conversation memory
• `/brightmind model [name]` - Show or set model

You can also DM me or @mention me in channels!"""
        )
    elif text == "status":
        import asyncio
        
        async def check_status():
            lines = []
            gateway_url = f"http://{settings.llm_gateway.host}:{settings.llm_gateway.port}"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{gateway_url}/health")
                    if response.status_code == 200:
                        data = response.json()
                        lines.append(
                            f"✅ LLM Gateway: {data.get('ollama', 'unknown')} "
                            f"| Model: {data.get('model', 'unknown')}"
                        )
                    else:
                        lines.append(f"❌ LLM Gateway: HTTP {response.status_code}")
            except Exception as e:
                lines.append(f"❌ LLM Gateway: {str(e)}")

            if settings.openclaw_adapter.enabled:
                adapter_url = (
                    f"http://{settings.openclaw_adapter.host}"
                    f":{settings.openclaw_adapter.port}"
                )
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f"{adapter_url}/health")
                        if response.status_code == 200:
                            data = response.json()
                            mode = data.get("mode", "unknown")
                            gw = data.get("llm_gateway", "unknown")
                            lines.append(
                                f"✅ OpenClaw Adapter: mode={mode} "
                                f"| gateway={gw}"
                            )
                        else:
                            lines.append(
                                f"❌ OpenClaw Adapter: HTTP {response.status_code}"
                            )
                except Exception as e:
                    lines.append(f"❌ OpenClaw Adapter: {str(e)}")
            else:
                lines.append("ℹ️ OpenClaw Adapter: disabled")

            routing = "OpenClaw → Gateway" if settings.openclaw_adapter.enabled else "Direct Gateway"
            lines.append(f"🔀 Routing: {routing}")
            return "\n".join(lines)
        
        status = asyncio.run(check_status())
        say(text=f"*BrightMind Status*\n{status}")
    elif text == "reset":
        conversations.clear(f"cmd:{user}")
        say(text="Slash-command conversation memory reset.")
    elif text.startswith("model "):
        model_name = text[6:].strip()
        say(
            text=(
                f"Model switching not yet implemented. "
                f"Requested: {model_name}. Current: {settings.ollama.default_model}"
            )
        )
    else:
        # Treat as a query
        import asyncio
        conv_id = f"cmd:{user}"
        response = asyncio.run(get_llm_response(conv_id, text))
        if response:
            say(text=response)
        else:
            say(text="Sorry, I couldn't process that request.")


@app.error
def global_error_handler(error, body, logger):
    """Global error handler."""
    logger.error("Unhandled error", error=str(error), body=body)


def main():
    """Main entry point."""
    routing = "openclaw_adapter" if settings.openclaw_adapter.enabled else "direct_gateway"
    logger.info(
        "Starting Slack Bot",
        socket_mode=settings.slack.socket_mode,
        routing=routing,
        openclaw_enabled=settings.openclaw_adapter.enabled,
        openclaw_dry_run=settings.openclaw_adapter.dry_run,
    )
    
    # Validate configuration
    if not settings.slack.bot_token:
        logger.error("SLACK_BOT_TOKEN not configured")
        print("ERROR: SLACK_BOT_TOKEN not configured. Please set it in .env file.")
        sys.exit(1)
    
    if not settings.slack.app_token:
        logger.error("SLACK_APP_TOKEN not configured")
        print("ERROR: SLACK_APP_TOKEN not configured. Please set it in .env file.")
        sys.exit(1)
    
    if settings.slack.socket_mode:
        logger.info("Starting Socket Mode handler")
        handler = SocketModeHandler(app, settings.slack.app_token)
        handler.start()
    else:
        logger.info("Starting HTTP Mode handler")
        # HTTP mode would require different setup
        print("HTTP mode not implemented in this version. Use Socket Mode.")
        sys.exit(1)


if __name__ == "__main__":
    main()
