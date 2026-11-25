"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Không ping Redis lúc import để app vẫn khởi động được khi Redis chưa sẵn sàng.
"""
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url or "redis://localhost:6379/0",
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Kiểm tra Redis có phản hồi PING hay không (dùng cho GET /ready)."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng connection pool khi ứng dụng tắt."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
