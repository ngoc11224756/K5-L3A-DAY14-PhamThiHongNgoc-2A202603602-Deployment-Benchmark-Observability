"""
Rate limiting (tiêu chí 7) — Sliding window 60 giây lưu trong Redis.
"""
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """
    Kiểm tra số request trong 60 giây gần nhất bằng Redis Sorted Set.
    Vượt RATE_LIMIT_PER_MINUTE → HTTP 429 kèm header Retry-After.
    """
    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = f"ratelimit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            else:
                retry_after = WINDOW_SECONDS
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": settings.rate_limit_per_minute,
                    "window_seconds": WINDOW_SECONDS,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Rate limiter unavailable: cannot connect to Redis",
        )
