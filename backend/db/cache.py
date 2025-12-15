"""
Redis Caching Layer for F1 RIA

Provides intelligent caching for query results with:
- Automatic key generation from query parameters
- TTL-based expiration (configurable per query type)
- Cache invalidation on data refresh
- Compression for large results
"""

import hashlib
import json
import logging
import os
import zlib
from functools import wraps
from typing import Any, Callable, TypeVar

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Type variable for decorated functions
T = TypeVar("T")

# Cache TTL configuration (seconds)
CACHE_TTL = {
    "season_standings": 3600 * 24,  # 24 hours - rarely changes
    "race_summary": 3600 * 24,  # 24 hours - historical data
    "head_to_head": 3600 * 24,  # 24 hours - historical comparisons
    "stint_analysis": 3600 * 24,  # 24 hours - historical data
    "driver_season": 3600 * 24,  # 24 hours - historical data
    "lap_times": 3600,  # 1 hour - detailed data
    "default": 3600,  # 1 hour default
}

# Compression threshold (bytes)
COMPRESSION_THRESHOLD = 1024  # Compress if > 1KB

# Redis connection pool
_redis_pool: redis.Redis | None = None


async def init_redis(redis_url: str | None = None) -> redis.Redis:
    """Initialize Redis connection pool."""
    global _redis_pool

    if _redis_pool is not None:
        return _redis_pool

    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
    _redis_pool = redis.from_url(
        url,
        encoding="utf-8",
        decode_responses=False,  # We handle encoding ourselves for compression
    )

    # Test connection
    try:
        await _redis_pool.ping()
        logger.info(f"Redis cache initialized: {url}")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        _redis_pool = None
        raise

    return _redis_pool


async def close_redis():
    """Close Redis connection pool."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis connection closed")


def get_redis() -> redis.Redis | None:
    """Get Redis connection (may be None if not initialized)."""
    return _redis_pool


def _generate_cache_key(prefix: str, **kwargs) -> str:
    """
    Generate a deterministic cache key from function arguments.

    Args:
        prefix: Cache key prefix (e.g., function name)
        **kwargs: Function arguments to include in key

    Returns:
        Cache key string
    """
    # Sort kwargs for deterministic key generation
    sorted_args = sorted(
        (k, v) for k, v in kwargs.items()
        if v is not None  # Skip None values
    )

    # Create hash of arguments
    args_str = json.dumps(sorted_args, sort_keys=True, default=str)
    args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]

    return f"f1:{prefix}:{args_hash}"


def _compress(data: bytes) -> bytes:
    """Compress data if above threshold."""
    if len(data) > COMPRESSION_THRESHOLD:
        compressed = zlib.compress(data, level=6)
        # Only use compressed if actually smaller
        if len(compressed) < len(data):
            return b"Z" + compressed  # Prefix to indicate compression
    return b"R" + data  # R = raw


def _decompress(data: bytes) -> bytes:
    """Decompress data if compressed."""
    if data.startswith(b"Z"):
        return zlib.decompress(data[1:])
    return data[1:]  # Remove the R prefix


async def cache_get(key: str) -> Any | None:
    """
    Get value from cache.

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found
    """
    if not _redis_pool:
        return None

    try:
        data = await _redis_pool.get(key)
        if data is None:
            return None

        # Decompress and deserialize
        raw = _decompress(data)
        return json.loads(raw.decode("utf-8"))

    except Exception as e:
        logger.warning(f"Cache get error for {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> bool:
    """
    Set value in cache.

    Args:
        key: Cache key
        value: Value to cache (must be JSON serializable)
        ttl: Time-to-live in seconds (default: 1 hour)

    Returns:
        True if successful
    """
    if not _redis_pool:
        return False

    try:
        # Serialize and compress
        raw = json.dumps(value, default=str).encode("utf-8")
        data = _compress(raw)

        # Set with TTL
        await _redis_pool.set(key, data, ex=ttl or CACHE_TTL["default"])
        return True

    except Exception as e:
        logger.warning(f"Cache set error for {key}: {e}")
        return False


async def cache_delete(pattern: str) -> int:
    """
    Delete cache entries matching pattern.

    Args:
        pattern: Redis pattern (e.g., "f1:season_standings:*")

    Returns:
        Number of keys deleted
    """
    if not _redis_pool:
        return 0

    try:
        keys = []
        async for key in _redis_pool.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            return await _redis_pool.delete(*keys)
        return 0

    except Exception as e:
        logger.warning(f"Cache delete error for {pattern}: {e}")
        return 0


async def cache_stats() -> dict:
    """Get cache statistics."""
    if not _redis_pool:
        return {"status": "disconnected"}

    try:
        info = await _redis_pool.info("memory")
        keys = await _redis_pool.dbsize()

        return {
            "status": "connected",
            "keys": keys,
            "used_memory": info.get("used_memory_human", "unknown"),
            "peak_memory": info.get("used_memory_peak_human", "unknown"),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


def cached(
    prefix: str,
    ttl_key: str = "default",
    key_params: list[str] | None = None,
) -> Callable:
    """
    Decorator for caching async function results.

    Args:
        prefix: Cache key prefix
        ttl_key: Key for TTL lookup in CACHE_TTL
        key_params: Specific params to include in cache key (default: all)

    Usage:
        @cached("season_standings", ttl_key="season_standings")
        async def get_season_standings(year: int, limit: int = 20):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Skip cache if Redis not available
            if not _redis_pool:
                return await func(*args, **kwargs)

            # Build cache key from specified params or all kwargs
            if key_params:
                cache_kwargs = {k: kwargs.get(k) for k in key_params}
            else:
                cache_kwargs = kwargs.copy()

            key = _generate_cache_key(prefix, **cache_kwargs)

            # Try cache first
            cached_result = await cache_get(key)
            if cached_result is not None:
                logger.debug(f"Cache HIT: {key}")
                return cached_result

            # Cache miss - execute function
            logger.debug(f"Cache MISS: {key}")
            result = await func(*args, **kwargs)

            # Cache the result
            ttl = CACHE_TTL.get(ttl_key, CACHE_TTL["default"])
            await cache_set(key, result, ttl)

            return result

        return wrapper
    return decorator


async def invalidate_season(year: int):
    """Invalidate all cache entries for a season."""
    patterns = [
        f"f1:season_standings:*{year}*",
        f"f1:race_summary:*{year}*",
        f"f1:head_to_head:*{year}*",
        f"f1:stint_analysis:*{year}*",
        f"f1:driver_season:*{year}*",
    ]

    total = 0
    for pattern in patterns:
        count = await cache_delete(pattern)
        total += count

    logger.info(f"Invalidated {total} cache entries for {year} season")
    return total


async def invalidate_all():
    """Invalidate all F1 cache entries."""
    count = await cache_delete("f1:*")
    logger.info(f"Invalidated {count} cache entries")
    return count
