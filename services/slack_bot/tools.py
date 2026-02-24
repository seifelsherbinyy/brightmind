"""Built-in tool definitions and executor for BrightMind Slack bot.

Tools are described using the Ollama / OpenAI function-calling schema so
they can be sent alongside chat requests.  The executor maps tool names
to Python callables and returns string results.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Tool definitions (Ollama / OpenAI compatible schema)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": (
                "Get the current date, time, and timezone. "
                "Use when the user asks what time or date it is."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch the text content of a public web page or API endpoint. "
                "Use when the user asks you to look something up online, "
                "read a URL, or retrieve live data from an API."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch (must start with http:// or https://).",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "service_status",
            "description": (
                "Check the health of BrightMind backend services "
                "(LLM Gateway, Ollama, OpenClaw Adapter). "
                "Use when the user asks about system status or service health."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_models",
            "description": (
                "List the LLM models currently available in the local Ollama instance. "
                "Use when the user asks what models are available or installed."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a mathematical expression and return the result. "
                "Supports basic arithmetic (+, -, *, /, **, %, //). "
                "Use when the user asks for a calculation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g. '2 ** 10' or '355 / 113'.",
                    },
                },
                "required": ["expression"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _get_current_datetime(**_kwargs: Any) -> str:
    now = datetime.now(timezone.utc)
    return json.dumps({
        "utc": now.isoformat(),
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%H:%M:%S UTC"),
    })


def _web_fetch(url: str = "", **_kwargs: Any) -> str:
    if not url or not url.startswith(("http://", "https://")):
        return json.dumps({"error": "Invalid URL. Must start with http:// or https://."})
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "BrightMind/1.1"})
            body = resp.text[:4000]
            return json.dumps({
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "body": body,
            })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _service_status(**_kwargs: Any) -> str:
    results: Dict[str, Any] = {}
    for name, url in [
        ("llm_gateway", "http://127.0.0.1:8080/health"),
        ("openclaw_adapter", "http://127.0.0.1:8081/health"),
        ("ollama", "http://127.0.0.1:11434/api/tags"),
    ]:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                results[name] = resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            results[name] = {"error": str(exc)}
    return json.dumps(results)


def _list_models(**_kwargs: Any) -> str:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get("http://127.0.0.1:8080/models")
            if resp.status_code == 200:
                return json.dumps(resp.json())
            return json.dumps({"error": f"HTTP {resp.status_code}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


_SAFE_MATH_NAMES = {"abs": abs, "round": round, "min": min, "max": max, "pow": pow}


def _calculate(expression: str = "", **_kwargs: Any) -> str:
    if not expression:
        return json.dumps({"error": "No expression provided."})
    try:
        result = eval(expression, {"__builtins__": {}}, _SAFE_MATH_NAMES)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except Exception as exc:
        return json.dumps({"expression": expression, "error": str(exc)})


# ---------------------------------------------------------------------------
# Registry and executor
# ---------------------------------------------------------------------------

_TOOL_FUNCTIONS: Dict[str, Callable[..., str]] = {
    "get_current_datetime": _get_current_datetime,
    "web_fetch": _web_fetch,
    "service_status": _service_status,
    "list_models": _list_models,
    "calculate": _calculate,
}


def execute_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
    """Run a tool by name and return its string result."""
    fn = _TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return fn(**(arguments or {}))


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Return the list of tool schemas to pass to the LLM."""
    return TOOL_DEFINITIONS
