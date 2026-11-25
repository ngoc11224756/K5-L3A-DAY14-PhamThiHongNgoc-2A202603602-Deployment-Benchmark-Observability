"""
Cost guard (tiêu chí 8) — Theo dõi và giới hạn chi phí LLM bằng Redis.
"""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
DAILY_KEY_TTL_SECONDS = 2 * 24 * 3600


def _today_cost_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{day}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    key = _today_cost_key()
    try:
        current = float(r.get(key) or 0.0)
    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Cost guard unavailable: cannot connect to Redis",
        )

    if current >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "used_usd": round(current, 6),
                "budget_usd": settings.daily_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng trong Redis, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K

    key = _today_cost_key()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, DAILY_KEY_TTL_SECONDS)
        pipe.execute()
    except redis.RedisError:
        pass

    return cost
