"""Slack Bot - Bolt-based Slack integration for BrightMind."""

import sys
import os
from collections import defaultdict
from pathlib import Path
from time import time
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from common.config import get_settings
from common.logger import configure_logging, get_logger
from common.message_id import generate_message_id

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


def _build_messages(
    message: str,
    system_prompt: Optional[str] = None,
) -> list:
    """Build the messages list from user input and optional system prompt."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    return messages


async def call_llm_gateway(
    message: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> Optional[str]:
    """Call LLM Gateway directly for response.
    
    Args:
        message: User message
        model: Model to use (default from config)
        system_prompt: Optional system prompt
        
    Returns:
        Assistant response or None on error
    """
    gateway_url = f"http://{settings.llm_gateway.host}:{settings.llm_gateway.port}"
    
    messages = _build_messages(message, system_prompt)
    
    request_data = {
        "model": model or settings.ollama.default_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.ollama.temperature,
        "max_tokens": settings.ollama.max_tokens
    }
    
    for attempt in range(1, GATEWAY_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{gateway_url}/chat",
                    json=request_data
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("message", {}).get("content", "")

                logger.error(
                    "LLM Gateway error",
                    status_code=response.status_code,
                    attempt=attempt,
                    response=response.text
                )
                if attempt > GATEWAY_RETRIES:
                    return None
        except httpx.TimeoutException:
            logger.error("LLM Gateway timeout", attempt=attempt)
            if attempt > GATEWAY_RETRIES:
                return "Sorry, the request timed out. Please try again."
        except Exception as e:
            logger.error("LLM Gateway call failed", error=str(e), attempt=attempt)
            if attempt > GATEWAY_RETRIES:
                return None


async def call_openclaw_adapter(
    message: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> Optional[str]:
    """Call LLM through the OpenClaw adapter (OpenAI-compatible endpoint).

    Routes: slack_bot -> openclaw_adapter -> llm_gateway -> Ollama.

    Args:
        message: User message
        model: Model to use (default from config)
        system_prompt: Optional system prompt

    Returns:
        Assistant response or None on error
    """
    adapter_url = (
        f"http://{settings.openclaw_adapter.host}:{settings.openclaw_adapter.port}"
    )

    messages = _build_messages(message, system_prompt)

    request_data = {
        "model": model or settings.ollama.default_model,
        "messages": messages,
        "temperature": settings.ollama.temperature,
        "max_tokens": settings.ollama.max_tokens,
        "stream": False,
    }

    for attempt in range(1, GATEWAY_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{adapter_url}/v1/chat/completions",
                    json=request_data,
                )

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                    return None

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
                return "Sorry, the request timed out. Please try again."
        except Exception as e:
            logger.error(
                "OpenClaw adapter call failed", error=str(e), attempt=attempt
            )
            if attempt > GATEWAY_RETRIES:
                return None


async def get_llm_response(
    message: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """Unified router: picks the OpenClaw adapter or direct gateway path.

    When ``settings.openclaw_adapter.enabled`` is *True* the request is
    sent through the adapter first.  If the adapter call fails, the bot
    falls back to the direct LLM Gateway path so the user still gets a
    response.

    Args:
        message: User message
        model: Model to use (default from config)
        system_prompt: Optional system prompt

    Returns:
        Assistant response or None on error
    """
    if settings.openclaw_adapter.enabled:
        logger.info("Routing through OpenClaw adapter")
        result = await call_openclaw_adapter(message, model, system_prompt)
        if result is not None:
            return result
        logger.warning(
            "OpenClaw adapter failed, falling back to direct LLM Gateway"
        )

    return await call_llm_gateway(message, model, system_prompt)


# Initialize Bolt app
app = App(token=settings.slack.bot_token)


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
    
    # Rate limiting
    if not check_rate_limit(user):
        say(
            text="You're sending messages too quickly. Please wait a moment.",
            thread_ts=thread_ts
        )
        return
    
    # Sanitize input
    text = sanitize_input(text)
    
    # Remove @mention from text
    import re
    clean_text = re.sub(r'<@\w+>', '', text).strip()
    
    if not clean_text:
        say(
            text="Hello! How can I help you today?",
            thread_ts=thread_ts
        )
        return
    
    # Show typing indicator
    try:
        client.assistant_threads_setStatus(
            thread_ts=thread_ts,
            channel_id=channel,
            status="is thinking..."
        )
    except Exception:
        pass  # Ignore if not supported
    
    # Call LLM (via OpenClaw adapter when enabled, otherwise direct gateway)
    import asyncio
    response = asyncio.run(get_llm_response(clean_text))
    
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
    # Only handle DMs
    channel_type = event.get("channel_type", "")
    if channel_type != "im":
        return
    
    user = event.get("user", "unknown")
    channel = event.get("channel", "unknown")
    text = event.get("text", "")
    
    logger.info(
        "DM received",
        user=user,
        text_preview=text[:100]
    )
    
    # Rate limiting
    if not check_rate_limit(user):
        say(text="You're sending messages too quickly. Please wait a moment.")
        return
    
    # Sanitize input
    text = sanitize_input(text)
    
    if not text:
        say(text="Hello! How can I help you today?")
        return
    
    # Show typing indicator
    try:
        client.assistant_threads_setStatus(
            channel_id=channel,
            status="is thinking..."
        )
    except Exception:
        pass
    
    # Call LLM (via OpenClaw adapter when enabled, otherwise direct gateway)
    import asyncio
    
    system_prompt = """You are BrightMind, a helpful AI assistant running locally on the user's machine.
You have access to a local LLM and can help with coding, analysis, writing, and general questions.
Be concise but thorough in your responses."""
    
    response = asyncio.run(get_llm_response(text, system_prompt=system_prompt))
    
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
    elif text.startswith("model "):
        model_name = text[6:].strip()
        say(text=f"Model switching not yet implemented. Current: {settings.ollama.default_model}")
    else:
        # Treat as a query
        import asyncio
        response = asyncio.run(get_llm_response(text))
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
