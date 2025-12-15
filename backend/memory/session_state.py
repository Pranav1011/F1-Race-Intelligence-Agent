"""Session State via Redis.

Provides short-term working memory for agent sessions:
- Conversation history within a session
- Current analysis context
- Temporary data cache
- Session metadata
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class SessionState:
    """
    Session state manager using Redis.

    Provides fast key-value storage for:
    - Session conversation history
    - Current working context
    - Temporary cached data
    - Session metadata and preferences
    """

    # Key prefixes
    PREFIX_SESSION = "f1:session:"
    PREFIX_HISTORY = "f1:history:"
    PREFIX_CONTEXT = "f1:context:"
    PREFIX_CACHE = "f1:cache:"

    # TTLs (in seconds)
    TTL_SESSION = 86400  # 24 hours
    TTL_HISTORY = 3600   # 1 hour
    TTL_CONTEXT = 1800   # 30 minutes
    TTL_CACHE = 600      # 10 minutes

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: str | None = None,
    ):
        """
        Initialize session state manager.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Optional password
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password

        self._client: redis.Redis | None = None
        self._initialized = False

    async def initialize(self):
        """Initialize Redis connection."""
        if self._initialized:
            return

        logger.info(f"Connecting to Redis at {self.redis_host}:{self.redis_port}...")
        self._client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
            decode_responses=True,
        )

        # Test connection
        try:
            await self._client.ping()
            self._initialized = True
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._initialized = False

    # =========================================
    # Session Management
    # =========================================

    async def create_session(
        self,
        session_id: str,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        Create a new session.

        Args:
            session_id: Unique session identifier
            user_id: Optional user identifier
            metadata: Optional session metadata

        Returns:
            Session data dict
        """
        if not self._initialized:
            await self.initialize()

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
            "message_count": 0,
            "metadata": metadata or {},
        }

        key = f"{self.PREFIX_SESSION}{session_id}"
        await self._client.set(key, json.dumps(session_data), ex=self.TTL_SESSION)

        logger.debug(f"Created session: {session_id}")
        return session_data

    async def get_session(self, session_id: str) -> dict | None:
        """
        Get session data.

        Args:
            session_id: Session identifier

        Returns:
            Session data or None
        """
        if not self._initialized:
            await self.initialize()

        key = f"{self.PREFIX_SESSION}{session_id}"
        data = await self._client.get(key)

        if data:
            return json.loads(data)
        return None

    async def update_session(
        self,
        session_id: str,
        updates: dict,
    ) -> dict | None:
        """
        Update session data.

        Args:
            session_id: Session identifier
            updates: Fields to update

        Returns:
            Updated session data or None
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        session.update(updates)
        session["last_activity"] = datetime.now(timezone.utc).isoformat()

        key = f"{self.PREFIX_SESSION}{session_id}"
        await self._client.set(key, json.dumps(session), ex=self.TTL_SESSION)

        return session

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all associated data.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted
        """
        if not self._initialized:
            await self.initialize()

        keys = [
            f"{self.PREFIX_SESSION}{session_id}",
            f"{self.PREFIX_HISTORY}{session_id}",
            f"{self.PREFIX_CONTEXT}{session_id}",
        ]

        # Also delete any cache keys for this session
        cache_pattern = f"{self.PREFIX_CACHE}{session_id}:*"
        cache_keys = []
        async for key in self._client.scan_iter(match=cache_pattern):
            cache_keys.append(key)

        all_keys = keys + cache_keys
        if all_keys:
            await self._client.delete(*all_keys)

        logger.debug(f"Deleted session: {session_id}")
        return True

    # =========================================
    # Conversation History
    # =========================================

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ):
        """
        Add a message to session history.

        Args:
            session_id: Session identifier
            role: Message role (user/assistant/system)
            content: Message content
            metadata: Optional message metadata
        """
        if not self._initialized:
            await self.initialize()

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        key = f"{self.PREFIX_HISTORY}{session_id}"
        await self._client.rpush(key, json.dumps(message))
        await self._client.expire(key, self.TTL_HISTORY)

        # Update session message count
        await self.update_session(session_id, {
            "message_count": await self._client.llen(key)
        })

    async def get_history(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get conversation history.

        Args:
            session_id: Session identifier
            limit: Maximum messages to return (most recent)

        Returns:
            List of messages
        """
        if not self._initialized:
            await self.initialize()

        key = f"{self.PREFIX_HISTORY}{session_id}"
        messages = await self._client.lrange(key, -limit, -1)

        return [json.loads(m) for m in messages]

    async def clear_history(self, session_id: str):
        """
        Clear conversation history.

        Args:
            session_id: Session identifier
        """
        if not self._initialized:
            await self.initialize()

        key = f"{self.PREFIX_HISTORY}{session_id}"
        await self._client.delete(key)

    # =========================================
    # Working Context
    # =========================================

    async def set_context(
        self,
        session_id: str,
        context: dict,
    ):
        """
        Set current working context.

        This stores the current analysis state, entities being discussed,
        and other temporary context.

        Args:
            session_id: Session identifier
            context: Context data
        """
        if not self._initialized:
            await self.initialize()

        key = f"{self.PREFIX_CONTEXT}{session_id}"
        await self._client.set(key, json.dumps(context), ex=self.TTL_CONTEXT)

    async def get_context(self, session_id: str) -> dict | None:
        """
        Get current working context.

        Args:
            session_id: Session identifier

        Returns:
            Context data or None
        """
        if not self._initialized:
            await self.initialize()

        key = f"{self.PREFIX_CONTEXT}{session_id}"
        data = await self._client.get(key)

        if data:
            return json.loads(data)
        return None

    async def update_context(
        self,
        session_id: str,
        updates: dict,
    ) -> dict:
        """
        Update working context with new data.

        Args:
            session_id: Session identifier
            updates: Fields to update/add

        Returns:
            Updated context
        """
        context = await self.get_context(session_id) or {}
        context.update(updates)
        await self.set_context(session_id, context)
        return context

    # =========================================
    # Temporary Cache
    # =========================================

    async def cache_set(
        self,
        session_id: str,
        key: str,
        value: Any,
        ttl: int | None = None,
    ):
        """
        Set a cached value.

        Args:
            session_id: Session identifier
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Optional TTL override
        """
        if not self._initialized:
            await self.initialize()

        cache_key = f"{self.PREFIX_CACHE}{session_id}:{key}"
        await self._client.set(
            cache_key,
            json.dumps(value),
            ex=ttl or self.TTL_CACHE,
        )

    async def cache_get(
        self,
        session_id: str,
        key: str,
    ) -> Any | None:
        """
        Get a cached value.

        Args:
            session_id: Session identifier
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self._initialized:
            await self.initialize()

        cache_key = f"{self.PREFIX_CACHE}{session_id}:{key}"
        data = await self._client.get(cache_key)

        if data:
            return json.loads(data)
        return None

    async def cache_delete(
        self,
        session_id: str,
        key: str,
    ):
        """
        Delete a cached value.

        Args:
            session_id: Session identifier
            key: Cache key
        """
        if not self._initialized:
            await self.initialize()

        cache_key = f"{self.PREFIX_CACHE}{session_id}:{key}"
        await self._client.delete(cache_key)

    # =========================================
    # Utility Methods
    # =========================================

    async def extend_session_ttl(self, session_id: str):
        """Extend session TTL on activity."""
        if not self._initialized:
            await self.initialize()

        keys = [
            f"{self.PREFIX_SESSION}{session_id}",
            f"{self.PREFIX_HISTORY}{session_id}",
        ]

        for key in keys:
            await self._client.expire(key, self.TTL_SESSION)

    async def get_active_sessions(self) -> list[str]:
        """Get list of active session IDs."""
        if not self._initialized:
            await self.initialize()

        session_ids = []
        pattern = f"{self.PREFIX_SESSION}*"

        async for key in self._client.scan_iter(match=pattern):
            session_id = key.replace(self.PREFIX_SESSION, "")
            session_ids.append(session_id)

        return session_ids

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            if not self._initialized:
                return False
            await self._client.ping()
            return True
        except Exception:
            return False


# Global instance
_session_state: SessionState | None = None


async def get_session_state(
    redis_host: str = "redis",
    redis_port: int = 6379,
) -> SessionState:
    """Get or create the global SessionState instance."""
    global _session_state
    if _session_state is None:
        _session_state = SessionState(
            redis_host=redis_host,
            redis_port=redis_port,
        )
        await _session_state.initialize()
    return _session_state
