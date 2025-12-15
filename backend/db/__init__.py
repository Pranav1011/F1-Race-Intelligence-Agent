"""Database utilities."""

from db.cache import (
    init_redis,
    close_redis,
    get_redis,
    cache_get,
    cache_set,
    cache_delete,
    cache_stats,
    cached,
    invalidate_season,
    invalidate_all,
    CACHE_TTL,
)

__all__ = [
    "init_redis",
    "close_redis",
    "get_redis",
    "cache_get",
    "cache_set",
    "cache_delete",
    "cache_stats",
    "cached",
    "invalidate_season",
    "invalidate_all",
    "CACHE_TTL",
]
