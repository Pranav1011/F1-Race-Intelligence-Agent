"""
Tests for Redis caching layer.
"""

import pytest
import json
import zlib
from unittest.mock import AsyncMock, MagicMock, patch

# Test the cache module functions
from db.cache import (
    _generate_cache_key,
    _compress,
    _decompress,
    CACHE_TTL,
)


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_generate_cache_key_basic(self):
        """Test basic cache key generation."""
        key = _generate_cache_key("test_prefix", arg1="value1", arg2="value2")
        assert key.startswith("f1:test_prefix:")
        assert len(key) > len("f1:test_prefix:")

    def test_generate_cache_key_deterministic(self):
        """Test that same args produce same key."""
        key1 = _generate_cache_key("prefix", a=1, b=2)
        key2 = _generate_cache_key("prefix", a=1, b=2)
        assert key1 == key2

    def test_generate_cache_key_order_independent(self):
        """Test that argument order doesn't affect key."""
        key1 = _generate_cache_key("prefix", a=1, b=2)
        key2 = _generate_cache_key("prefix", b=2, a=1)
        assert key1 == key2

    def test_generate_cache_key_ignores_none(self):
        """Test that None values are ignored."""
        key1 = _generate_cache_key("prefix", a=1, b=None)
        key2 = _generate_cache_key("prefix", a=1)
        assert key1 == key2

    def test_generate_cache_key_different_values(self):
        """Test that different values produce different keys."""
        key1 = _generate_cache_key("prefix", a=1)
        key2 = _generate_cache_key("prefix", a=2)
        assert key1 != key2


class TestCompression:
    """Tests for compression/decompression."""

    def test_compress_small_data_not_compressed(self):
        """Test that small data is not compressed."""
        small_data = b"small"
        result = _compress(small_data)
        assert result.startswith(b"R")  # R = raw
        assert result[1:] == small_data

    def test_compress_large_data_compressed(self):
        """Test that large data is compressed."""
        # Create compressible data > 1KB
        large_data = b"x" * 2000
        result = _compress(large_data)
        assert result.startswith(b"Z")  # Z = zlib compressed
        assert len(result) < len(large_data)

    def test_decompress_raw_data(self):
        """Test decompression of raw data."""
        original = b"test data"
        compressed = b"R" + original
        result = _decompress(compressed)
        assert result == original

    def test_decompress_compressed_data(self):
        """Test decompression of compressed data."""
        original = b"x" * 2000
        compressed = b"Z" + zlib.compress(original)
        result = _decompress(compressed)
        assert result == original

    def test_compress_decompress_roundtrip(self):
        """Test compression and decompression roundtrip."""
        original = b"test data for roundtrip"
        compressed = _compress(original)
        decompressed = _decompress(compressed)
        assert decompressed == original

    def test_compress_decompress_large_roundtrip(self):
        """Test roundtrip with large compressible data."""
        original = json.dumps({"data": "x" * 5000}).encode()
        compressed = _compress(original)
        decompressed = _decompress(compressed)
        assert decompressed == original


class TestCacheTTL:
    """Tests for cache TTL configuration."""

    def test_ttl_values_exist(self):
        """Test that expected TTL keys exist."""
        assert "season_standings" in CACHE_TTL
        assert "race_summary" in CACHE_TTL
        assert "head_to_head" in CACHE_TTL
        assert "stint_analysis" in CACHE_TTL
        assert "default" in CACHE_TTL

    def test_ttl_values_are_positive(self):
        """Test that all TTL values are positive."""
        for key, value in CACHE_TTL.items():
            assert value > 0, f"TTL for {key} should be positive"

    def test_historical_data_has_long_ttl(self):
        """Test that historical data has longer TTL."""
        assert CACHE_TTL["season_standings"] >= 3600  # At least 1 hour
        assert CACHE_TTL["race_summary"] >= 3600


class TestCacheOperations:
    """Tests for cache get/set operations (mocked)."""

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_when_not_initialized(self):
        """Test cache_get returns None when Redis not initialized."""
        from db.cache import cache_get

        # With _redis_pool = None, should return None
        with patch('db.cache._redis_pool', None):
            result = await cache_get("test_key")
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_returns_false_when_not_initialized(self):
        """Test cache_set returns False when Redis not initialized."""
        from db.cache import cache_set

        with patch('db.cache._redis_pool', None):
            result = await cache_set("test_key", {"data": "test"})
            assert result is False


class TestCacheStats:
    """Tests for cache statistics."""

    @pytest.mark.asyncio
    async def test_cache_stats_disconnected(self):
        """Test cache_stats when not connected."""
        from db.cache import cache_stats

        with patch('db.cache._redis_pool', None):
            result = await cache_stats()
            assert result["status"] == "disconnected"
