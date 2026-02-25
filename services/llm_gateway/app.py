"""LLM Gateway - FastAPI service for local LLM inference via Ollama."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
    service_name="llm_gateway"
)
logger = get_logger(__name__)


# Pydantic models
class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role (system, user, assistant, tool)")
    content: str = Field(default="", description="Message content")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tool calls requested by the model")
    tool_call_id: Optional[str] = Field(default=None, description="ID of the tool call this message responds to")


class ChatRequest(BaseModel):
    """Chat completion request."""
    model: str = Field(default="qwen2.5-coder:7b", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="Conversation messages")
    stream: bool = Field(default=False, description="Stream response")
    temperature: float = Field(default=0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: int = Field(default=2048, ge=1, le=8192, description="Maximum tokens")
    tools: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tool definitions for function calling")


class ChatUsage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)


class ChatResponse(BaseModel):
    """Chat completion response."""
    id: str = Field(..., description="Response ID")
    model: str = Field(..., description="Model used")
    message: ChatMessage = Field(..., description="Assistant response")
    usage: ChatUsage = Field(default_factory=ChatUsage)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok")
    readiness: str = Field(default="ready")
    ollama: str = Field(default="unknown")
    model: Optional[str] = Field(default=None)
    hint: Optional[str] = Field(default=None)
    version: str = Field(default="1.0.0")


class OllamaClient:
    """Client for Ollama API."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._available = False
        self._default_model = "qwen2.5-coder:7b"
    
    async def check_health(self) -> dict:
        """Check Ollama server health."""
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    self._available = True
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {
                        "status": "ok",
                        "models": models,
                        "default": self._default_model
                    }
                else:
                    self._available = False
                    return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            self._available = False
            return {"status": "error", "message": str(e)}
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send chat request to Ollama."""
        import httpx
        
        if not self._available:
            health = await self.check_health()
            if health["status"] != "ok":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Ollama not available: {health.get('message', 'unknown error')}"
                )
        
        # Convert messages to Ollama format
        messages = []
        for m in request.messages:
            msg: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            messages.append(msg)
        
        ollama_request: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens
            }
        }

        if request.tools:
            ollama_request["tools"] = request.tools
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=ollama_request
                )
                
                if response.status_code != 200:
                    if response.status_code == 404 or "model" in response.text.lower():
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=(
                                f"Model '{request.model}' is unavailable. "
                                "Run .\\scripts\\download_model.ps1 -Model "
                                f"\"{request.model}\" -Force"
                            )
                        )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Ollama error: {response.text}"
                    )
                
                data = response.json()
                resp_message = data.get("message", {})
                tool_calls = resp_message.get("tool_calls")

                return ChatResponse(
                    id=generate_message_id("msg"),
                    model=request.model,
                    message=ChatMessage(
                        role="assistant",
                        content=resp_message.get("content", ""),
                        tool_calls=tool_calls,
                    ),
                    usage=ChatUsage(
                        prompt_tokens=data.get("prompt_eval_count", 0),
                        completion_tokens=data.get("eval_count", 0),
                        total_tokens=(data.get("prompt_eval_count", 0) + data.get("eval_count", 0))
                    )
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Ollama request timed out"
            )
        except Exception as e:
            logger.error("Ollama request failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Ollama request failed: {str(e)}"
            )
    
    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """Stream chat response from Ollama."""
        import httpx
        
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        ollama_request = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=ollama_request
                ) as response:
                    async for line in response.aiter_lines():
                        if line.strip():
                            yield f"data: {line}\n\n"
        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield f"data: {{'error': '{str(e)}'}}\n\n"


# Global Ollama client
ollama_client: Optional[OllamaClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global ollama_client
    
    logger.info("Starting LLM Gateway", version="1.0.0")
    
    # Initialize Ollama client
    ollama_client = OllamaClient(base_url=settings.ollama.host)
    health = await ollama_client.check_health()
    
    if health["status"] == "ok":
        logger.info(
            "Ollama connected",
            models=health.get("models", []),
            default=health.get("default")
        )
    else:
        logger.warning(
            "Ollama not available",
            error=health.get("message"),
            hint="Run 'ollama serve' or install Ollama"
        )
    
    yield
    
    logger.info("Shutting down LLM Gateway")


# Create FastAPI app
app = FastAPI(
    title="BrightMind LLM Gateway",
    description="Local LLM inference gateway via Ollama",
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
    global ollama_client
    
    if ollama_client is None:
        return HealthResponse(
            status="error",
            readiness="not_ready",
            ollama="not_initialized",
            hint="Restart the service to initialize the Ollama client."
        )
    
    health = await ollama_client.check_health()
    
    ollama_ok = health["status"] == "ok"
    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        readiness="ready" if ollama_ok else "not_ready",
        ollama=health["status"],
        model=health.get("default") if ollama_ok else None,
        hint=None if ollama_ok else "Ensure Ollama is running (`ollama serve`) and model is downloaded.",
        version="1.0.0"
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat completion endpoint."""
    global ollama_client
    
    if ollama_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama client not initialized"
        )
    
    logger.info(
        "Chat request",
        model=request.model,
        message_count=len(request.messages),
        stream=request.stream
    )
    
    try:
        response = await ollama_client.chat(request)
        logger.info(
            "Chat response",
            model=response.model,
            tokens=response.usage.total_tokens
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Streaming chat completion endpoint."""
    global ollama_client
    
    if ollama_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama client not initialized"
        )
    
    logger.info("Stream request", model=request.model)
    
    return StreamingResponse(
        ollama_client.chat_stream(request),
        media_type="text/event-stream"
    )


@app.get("/models")
async def list_models() -> dict:
    """List available models."""
    global ollama_client
    
    if ollama_client is None:
        return {"models": [], "default": settings.ollama.default_model}
    
    health = await ollama_client.check_health()
    
    return {
        "models": health.get("models", []),
        "default": settings.ollama.default_model,
        "fallback": settings.ollama.fallback_model
    }


if __name__ == "__main__":
    import uvicorn
    
    host = settings.llm_gateway.host
    port = settings.llm_gateway.port
    
    logger.info(f"Starting LLM Gateway on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=settings.log_level.lower()
    )
