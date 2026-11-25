"""
Production AI Agent — Part 6 Final Project

Đáp ứng đủ 12 tiêu chí Production Readiness:
  - /health (liveness) và /ready (readiness kiểm tra Redis)
  - API Key authentication (X-API-Key -> 401)
  - Rate limiting (sliding window trong Redis -> 429)
  - Cost guard (theo dõi chi phí trong Redis -> 402)
  - Config từ biến môi trường, structured JSON logging, graceful shutdown
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi dòng log của ứng dụng thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    app_logger = logging.getLogger("production_agent")
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _setup_logger()
START_TIME = time.time()
_is_shutting_down = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management: startup và graceful shutdown (SIGTERM)."""
    global _is_shutting_down
    _is_shutting_down = False
    logger.info(
        "agent_startup",
        extra={
            "extra_fields": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
                "rate_limit_per_minute": settings.rate_limit_per_minute,
            }
        },
    )
    yield
    _is_shutting_down = True
    logger.info(
        "agent_shutdown",
        extra={"extra_fields": {"event": "graceful_shutdown", "signal": "SIGTERM"}},
    )
    close_redis()


app = FastAPI(
    title="Production AI Agent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.error(
            "unhandled_exception",
            extra={
                "extra_fields": {
                    "event": "error",
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "ms": elapsed_ms,
                }
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "http_request",
        extra={
            "extra_fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = None


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy, kể cả khi Redis mất kết nối."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi sẵn sàng, 503 khi đang tắt hoặc Redis không kết nối được."""
    if _is_shutting_down or not redis_healthy():
        raise HTTPException(
            status_code=503,
            detail="Agent not ready: Redis unavailable or shutting down",
        )
    return {"status": "ready", "redis": "ok"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)

    logger.info(
        "ask_completed",
        extra={
            "extra_fields": {
                "event": "ask",
                "user_id": body.user_id or "anonymous",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 6),
            }
        },
    )

    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": round(cost, 6),
    }
