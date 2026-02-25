"""Terminal smoke check for BrightMind chat plumbing.

This script is intentionally Slack-free: it does not require Slack tokens and does
not start the Slack bot. It helps answer "why can't I chat?" by validating that
the configured routing backend is reachable and can produce a response.

Usage (from repo root, with venv active):
  python -m services.slack_bot.smoke_check
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from common.config import get_settings


async def _get_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
    resp.raise_for_status()
    return resp.json()


async def _post_json(url: str, payload: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


async def main() -> int:
    settings = get_settings()
    gw_base = f"http://{settings.llm_gateway.host}:{settings.llm_gateway.port}"
    ad_base = f"http://{settings.openclaw_adapter.host}:{settings.openclaw_adapter.port}"

    print("BrightMind smoke check")
    print(f"- OPENCLAW_ENABLED={settings.openclaw_adapter.enabled}")
    print(f"- OPENCLAW_DRY_RUN={settings.openclaw_adapter.dry_run}")
    print(f"- LLM Gateway: {gw_base}")
    print(f"- OpenClaw Adapter: {ad_base}")

    gateway_health: Optional[Dict[str, Any]] = None
    adapter_health: Optional[Dict[str, Any]] = None

    try:
        gateway_health = await _get_json(f"{gw_base}/health")
        print(f"- gateway /health: ok (readiness={gateway_health.get('readiness')})")
    except Exception as exc:
        print(f"- gateway /health: ERROR ({exc})")

    try:
        adapter_health = await _get_json(f"{ad_base}/health")
        print(f"- adapter /health: ok (mode={adapter_health.get('mode')})")
    except Exception as exc:
        print(f"- adapter /health: ERROR ({exc})")

    user_text = "Hello BrightMind! Reply with a short confirmation."

    if settings.openclaw_adapter.enabled:
        try:
            data = await _post_json(
                f"{ad_base}/v1/chat/completions",
                {
                    "model": settings.ollama.default_model,
                    "messages": [
                        {"role": "system", "content": "You are BrightMind."},
                        {"role": "user", "content": user_text},
                    ],
                    "stream": False,
                    "temperature": settings.ollama.temperature,
                    "max_tokens": min(settings.ollama.max_tokens, 256),
                },
                timeout=10.0 if settings.openclaw_adapter.dry_run else 30.0,
            )
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
            print(f"- adapter chat: ok\n  response={content!r}")
            return 0
        except Exception as exc:
            print(f"- adapter chat: ERROR ({exc})")
            print("  Falling back to gateway chat check.")

    try:
        data = await _post_json(
            f"{gw_base}/chat",
            {
                "model": settings.ollama.default_model,
                "messages": [
                    {"role": "system", "content": "You are BrightMind."},
                    {"role": "user", "content": user_text},
                ],
                "stream": False,
                "temperature": settings.ollama.temperature,
                "max_tokens": min(settings.ollama.max_tokens, 256),
            },
            timeout=30.0,
        )
        content = (data.get("message") or {}).get("content")
        print(f"- gateway chat: ok\n  response={content!r}")
        return 0
    except Exception as exc:
        print(f"- gateway chat: ERROR ({exc})")

    print("Smoke check failed: neither adapter nor gateway produced a response.")
    print("Next steps:")
    print("- Start gateway: `python services/llm_gateway/app.py`")
    print("- Start adapter (if enabled): `python services/openclaw_adapter/app.py`")
    print("- Start Ollama: `ollama serve` (and pull a model)")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

