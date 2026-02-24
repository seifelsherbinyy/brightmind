"""OpenClaw Adapter - Bridge between OpenClaw Gateway and BrightMind LLM Gateway.

This service provides an OpenAI-compatible API that OpenClaw can use to access
local LLMs through BrightMind's LLM Gateway.

Usage:
    1. Start this adapter: python app.py
    2. Configure OpenClaw to use http://localhost:8081 as a model provider
    3. OpenClaw will route LLM requests through this adapter

Configuration in ~/.openclaw/openclaw.json:
    {
        "models": {
            "providers": {
                "brightmind": {
                    "baseUrl": "http://localhost:8081",
                    "apiKey": "unused-local"
                }
            }
        }
    }
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from common.config import get_settings
from common.logger import configure_logging, get_logger
from common.message_id import generate_message_id

# Configure logging
settings = get_settings()
log_dir = settings.paths.logs_dir
configure_logging(
    log_level=settings.log_level,
    log_dir=log_dir,
    service_name="openclaw_adapter"
)
logger = get_logger(__name__)


# Pydantic models (OpenAI-compatible)
class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role (system, user, assistant, tool)")
    content: str = Field(..., description="Message content")
    name: Optional[str] = Field(default=None, description="Name for tool messages")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(default="qwen2.5-coder:7b", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="Conversation messages")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=2048, ge=1)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    n: Optional[int] = Field(default=1, ge=1, le=10)
    stream: Optional[bool] = Field(default=False)
    stop: Optional[List[str]] = Field(default=None)
    presence_penalty: Optional[float] = Field(default=0, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(default=0, ge=-2, le=2)
    user: Optional[str] = Field(default=None)


class ChatCompletionChoice(BaseModel):
    """Chat completion choice."""
    index: int = Field(default=0)
    message: ChatMessage
    finish_reason: str = Field(default="stop")


class ChatCompletionUsage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = Field(default_factory=lambda: generate_message_id("chatcmpl"))
    object: str = Field(default="chat.completion")
    created: int = Field(default_factory=lambda: int(__import__("time").time()))
    model: str = Field(default="qwen2.5-coder:7b")
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ModelInfo(BaseModel):
    """Model information."""
    id: str
    object: str = Field(default="model")
    created: int = Field(default=0)
    owned_by: str = Field(default="brightmind")


class ModelListResponse(BaseModel):
    """List of available models."""
    object: str = Field(default="list")
    data: List[ModelInfo]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok")
    llm_gateway: str = Field(default="unknown")
    openclaw_gateway: str = Field(default="unknown")
    mode: str = Field(default="active")
    version: str = Field(default="1.0.0")


class OpenClawAdapter:
    """Adapter for OpenClaw integration."""
    
    def __init__(self):
        self.llm_gateway_url = f"http://{settings.llm_gateway.host}:{settings.llm_gateway.port}"
        self.openclaw_gateway_url = settings.openclaw_adapter.openclaw_gateway_url
        self._llm_available = False
        self._openclaw_available = False
    
    async def check_llm_gateway(self) -> dict:
        """Check LLM Gateway health."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.llm_gateway_url}/health")
                if response.status_code == 200:
                    self._llm_available = True
                    return {"status": "ok", "data": response.json()}
                else:
                    self._llm_available = False
                    return {"status": "error", "code": response.status_code}
        except Exception as e:
            self._llm_available = False
            return {"status": "error", "message": str(e)}
    
    async def check_openclaw_gateway(self) -> dict:
        """Check OpenClaw Gateway health."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.openclaw_gateway_url}/health")
                if response.status_code == 200:
                    self._openclaw_available = True
                    return {"status": "ok"}
                else:
                    self._openclaw_available = False
                    return {"status": "error", "code": response.status_code}
        except Exception as e:
            self._openclaw_available = False
            return {"status": "error", "message": str(e)}
    
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Process chat completion request.
        
        Forwards to LLM Gateway and formats response in OpenAI-compatible format.
        """
        if settings.openclaw_adapter.dry_run:
            stub_text = (
                "[OPENCLAW_DRY_RUN] Adapter stub response. "
                f"Received {len(request.messages)} message(s) for model '{request.model}'."
            )
            return ChatCompletionResponse(
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        message=ChatMessage(role="assistant", content=stub_text),
                        finish_reason="stop",
                    )
                ],
                usage=ChatCompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

        if not self._llm_available:
            health = await self.check_llm_gateway()
            if health["status"] != "ok":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"LLM Gateway not available: {health.get('message', 'unknown')}"
                )
        
        # Convert to LLM Gateway format
        gateway_request = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": request.stream,
            "temperature": request.temperature or 0.7,
            "max_tokens": request.max_tokens or 2048
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.llm_gateway_url}/chat",
                    json=gateway_request
                )
                
                if response.status_code != 200:
                    logger.error(
                        "LLM Gateway error",
                        status_code=response.status_code,
                        response=response.text
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"LLM Gateway error: {response.text}"
                    )
                
                data = response.json()
                
                return ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            message=ChatMessage(
                                role="assistant",
                                content=data.get("message", {}).get("content", "")
                            ),
                            finish_reason="stop"
                        )
                    ],
                    usage=ChatCompletionUsage(
                        prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                        completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                        total_tokens=data.get("usage", {}).get("total_tokens", 0)
                    )
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM Gateway timeout"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Chat completion failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Chat completion failed: {str(e)}"
            )
    
    async def list_models(self) -> ModelListResponse:
        """List available models from LLM Gateway."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.llm_gateway_url}/models")
                if response.status_code == 200:
                    data = response.json()
                    models = [
                        ModelInfo(id=m, created=0)
                        for m in data.get("models", [])
                    ]
                    # Add defaults if not present
                    defaults = [data.get("default"), data.get("fallback")]
                    for default in defaults:
                        if default and default not in [m.id for m in models]:
                            models.append(ModelInfo(id=default, created=0))
                    return ModelListResponse(data=models)
                else:
                    # Return defaults on error
                    return ModelListResponse(data=[
                        ModelInfo(id=settings.ollama.default_model, created=0),
                        ModelInfo(id=settings.ollama.fallback_model, created=0)
                    ])
        except Exception as e:
            logger.error("Failed to list models", error=str(e))
            return ModelListResponse(data=[
                ModelInfo(id=settings.ollama.default_model, created=0)
            ])


# Global adapter instance
adapter: Optional[OpenClawAdapter] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global adapter
    
    logger.info("Starting OpenClaw Adapter", version="1.0.0")
    
    # Initialize adapter
    adapter = OpenClawAdapter()
    
    # Check dependencies
    llm_health = await adapter.check_llm_gateway()
    openclaw_health = await adapter.check_openclaw_gateway()
    
    logger.info(
        "Dependency check",
        llm_gateway=llm_health["status"],
        openclaw_gateway=openclaw_health["status"]
    )
    
    yield
    
    logger.info("Shutting down OpenClaw Adapter")


# Create FastAPI app
app = FastAPI(
    title="BrightMind OpenClaw Adapter",
    description="OpenAI-compatible adapter for OpenClaw integration",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    global adapter
    
    if adapter is None:
        return HealthResponse(
            status="error",
            llm_gateway="not_initialized",
            openclaw_gateway="not_initialized"
        )
    
    llm_health = await adapter.check_llm_gateway()
    openclaw_health = await adapter.check_openclaw_gateway()
    
    return HealthResponse(
        status="ok" if llm_health["status"] == "ok" else "degraded",
        llm_gateway=llm_health["status"],
        openclaw_gateway=openclaw_health["status"],
        mode="dry_run" if settings.openclaw_adapter.dry_run else "active",
    )


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """List available models (OpenAI-compatible)."""
    global adapter
    
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adapter not initialized"
        )
    
    return await adapter.list_models()


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Chat completions endpoint (OpenAI-compatible).
    
    This is the main endpoint that OpenClaw uses to request LLM completions.
    """
    global adapter
    
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adapter not initialized"
        )
    
    logger.info(
        "Chat completion request",
        model=request.model,
        message_count=len(request.messages),
        stream=request.stream
    )
    
    # Note: Streaming not implemented in this version
    if request.stream:
        logger.warning("Streaming requested but not implemented")
    
    try:
        response = await adapter.chat_completion(request)
        logger.info(
            "Chat completion response",
            model=response.model,
            tokens=response.usage.total_tokens
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat completion failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat completion failed: {str(e)}"
        )


@app.get("/")
async def root() -> dict:
    """Root endpoint with basic info."""
    return {
        "name": "BrightMind OpenClaw Adapter",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/v1/models",
            "/v1/chat/completions"
        ],
        "mode": "dry_run" if settings.openclaw_adapter.dry_run else "active",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    if not settings.openclaw_adapter.enabled:
        print("OpenClaw Adapter is disabled in configuration.")
        print("To enable, set OPENCLAW_ENABLED=true in .env")
        print("Or set openclaw_adapter.enabled: true in config.yaml")
        sys.exit(0)
    
    host = settings.openclaw_adapter.host
    port = settings.openclaw_adapter.port
    
    logger.info(f"Starting OpenClaw Adapter on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=settings.log_level.lower()
    )
