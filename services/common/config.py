"""Configuration management for BrightMind."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _repo_root_from_file() -> Path:
    # services/common/config.py -> repo root
    return Path(__file__).resolve().parents[2]


def _get_nested(data: Dict[str, Any], path: str, default: Any) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


class PathConfig(BaseModel):
    project_root: Path
    logs_dir: Path
    cache_dir: Path
    data_dir: Path
    model_storage_dir: Path


class SlackConfig(BaseModel):
    bot_token: str = ""
    app_token: str = ""
    socket_mode: bool = True
    mention_only_in_channels: bool = True
    max_message_length: int = 4000
    rate_limit_per_minute: int = 30
    allowed_channels: List[str] = Field(default_factory=list)


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    default_model: str = "qwen2.5-coder:7b"
    fallback_model: str = "llama3.2:3b"
    timeout: int = 30
    max_tokens: int = 2048
    temperature: float = 0.7


class LLMGatewayConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080


class OpenClawAdapterConfig(BaseModel):
    enabled: bool = False
    dry_run: bool = True
    host: str = "127.0.0.1"
    port: int = 8081
    openclaw_gateway_url: str = "http://localhost:18789"
    api_key: str = ""


class Settings(BaseModel):
    app_name: str = "BrightMind"
    app_version: str = "1.1.0"
    log_level: str = "INFO"
    paths: PathConfig
    slack: SlackConfig
    ollama: OllamaConfig
    llm_gateway: LLMGatewayConfig
    openclaw_adapter: OpenClawAdapterConfig


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _build_settings() -> Settings:
    repo_root = Path(os.getenv("BRIGHTMIND_PROJECT_ROOT", _repo_root_from_file())).resolve()
    env_file = repo_root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    config_path = Path(os.getenv("BRIGHTMIND_CONFIG_PATH", str(repo_root / "config" / "config.yaml"))).resolve()
    cfg = _load_yaml_file(config_path)

    project_root = Path(os.getenv("BRIGHTMIND_PROJECT_ROOT", str(repo_root))).resolve()
    logs_dir = Path(os.getenv("BRIGHTMIND_LOGS_DIR", str(repo_root / "logs"))).resolve()
    cache_dir = Path(os.getenv("BRIGHTMIND_CACHE_DIR", str(repo_root / "cache"))).resolve()
    data_dir = Path(os.getenv("BRIGHTMIND_DATA_DIR", _get_nested(cfg, "app.data_dir", str(repo_root / "data")))).resolve()
    model_storage_dir = Path(os.getenv("OLLAMA_MODELS", "D:/ollama/models")).resolve()

    for directory in (logs_dir, cache_dir, data_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return Settings(
        app_name=os.getenv("BRIGHTMIND_APP_NAME", _get_nested(cfg, "app.name", "BrightMind")),
        app_version=os.getenv("BRIGHTMIND_APP_VERSION", _get_nested(cfg, "app.version", "1.1.0")),
        log_level=os.getenv("BRIGHTMIND_LOG_LEVEL", _get_nested(cfg, "app.log_level", "INFO")),
        paths=PathConfig(
            project_root=project_root,
            logs_dir=logs_dir,
            cache_dir=cache_dir,
            data_dir=data_dir,
            model_storage_dir=model_storage_dir,
        ),
        slack=SlackConfig(
            bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
            app_token=os.getenv("SLACK_APP_TOKEN", ""),
            socket_mode=os.getenv("SLACK_SOCKET_MODE", str(_get_nested(cfg, "services.slack_bot.socket_mode", True))).lower() == "true",
            mention_only_in_channels=os.getenv("SLACK_MENTION_ONLY_IN_CHANNELS", str(_get_nested(cfg, "services.slack_bot.mention_only_in_channels", True))).lower() == "true",
            max_message_length=int(os.getenv("SLACK_MAX_MESSAGE_LENGTH", str(_get_nested(cfg, "services.slack_bot.max_message_length", 4000)))),
            rate_limit_per_minute=int(os.getenv("SLACK_RATE_LIMIT_PER_MINUTE", str(_get_nested(cfg, "services.slack_bot.rate_limit_per_minute", 30)))),
            allowed_channels=_get_nested(cfg, "services.slack_bot.allowed_channels", []),
        ),
        ollama=OllamaConfig(
            host=os.getenv("OLLAMA_HOST", _get_nested(cfg, "services.llm_gateway.ollama_url", "http://localhost:11434")),
            default_model=os.getenv("OLLAMA_DEFAULT_MODEL", _get_nested(cfg, "models.default", "qwen2.5-coder:7b")),
            fallback_model=os.getenv("OLLAMA_FALLBACK_MODEL", _get_nested(cfg, "models.fallback", "llama3.2:3b")),
            timeout=int(os.getenv("OLLAMA_TIMEOUT", str(_get_nested(cfg, "services.llm_gateway.timeout", 30)))),
            max_tokens=int(os.getenv("OLLAMA_MAX_TOKENS", str(_get_nested(cfg, "services.llm_gateway.max_tokens", 2048)))),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", str(_get_nested(cfg, "models.temperature", 0.7)))),
        ),
        llm_gateway=LLMGatewayConfig(
            host=os.getenv("LLM_GATEWAY_HOST", _get_nested(cfg, "services.llm_gateway.host", "127.0.0.1")),
            port=int(os.getenv("LLM_GATEWAY_PORT", str(_get_nested(cfg, "services.llm_gateway.port", 8080)))),
        ),
        openclaw_adapter=OpenClawAdapterConfig(
            enabled=os.getenv("OPENCLAW_ENABLED", str(_get_nested(cfg, "services.openclaw_adapter.enabled", False))).lower() == "true",
            dry_run=os.getenv("OPENCLAW_DRY_RUN", "true").lower() == "true",
            host=os.getenv("OPENCLAW_HOST", _get_nested(cfg, "services.openclaw_adapter.host", "127.0.0.1")),
            port=int(os.getenv("OPENCLAW_PORT", str(_get_nested(cfg, "services.openclaw_adapter.port", 8081)))),
            openclaw_gateway_url=os.getenv("OPENCLAW_GATEWAY_URL", _get_nested(cfg, "services.openclaw_adapter.openclaw_gateway_url", "http://localhost:18789")),
            api_key=os.getenv("OPENCLAW_API_KEY", ""),
        ),
    )


@lru_cache()
def get_settings() -> Settings:
    return _build_settings()


def get_data_path(*parts: str) -> Path:
    settings = get_settings()
    path = settings.paths.data_dir.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
