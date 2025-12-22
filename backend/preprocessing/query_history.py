"""
Query history and smart suggestions for F1 RIA.

Features:
- Store and retrieve query history per user/session
- Generate smart suggestions based on patterns
- Track popular queries and trends
"""

import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Try to import Redis - graceful fallback to in-memory
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using in-memory query history")


@dataclass
class QueryHistoryEntry:
    """A single query history entry."""
    query: str
    normalized: str
    intent: str
    drivers: list[str] = field(default_factory=list)
    teams: list[str] = field(default_factory=list)
    circuits: list[str] = field(default_factory=list)
    year: int | None = None
    timestamp: str = ""
    session_id: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "normalized": self.normalized,
            "intent": self.intent,
            "drivers": self.drivers,
            "teams": self.teams,
            "circuits": self.circuits,
            "year": self.year,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueryHistoryEntry":
        return cls(
            query=data.get("query", ""),
            normalized=data.get("normalized", ""),
            intent=data.get("intent", "general"),
            drivers=data.get("drivers", []),
            teams=data.get("teams", []),
            circuits=data.get("circuits", []),
            year=data.get("year"),
            timestamp=data.get("timestamp", ""),
            session_id=data.get("session_id", ""),
        )


@dataclass
class QuerySuggestion:
    """A query suggestion."""
    text: str
    type: str  # "recent", "popular", "related", "follow_up"
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


class QueryHistoryManager:
    """
    Manages query history and generates smart suggestions.

    Features:
    - Per-user and per-session history
    - Popular query tracking
    - Pattern-based follow-up suggestions
    - Entity-based related suggestions
    """

    # Redis key prefixes
    PREFIX_USER_HISTORY = "f1ria:history:user:"
    PREFIX_SESSION_HISTORY = "f1ria:history:session:"
    PREFIX_POPULAR = "f1ria:popular"
    PREFIX_ENTITY_QUERIES = "f1ria:entity:"

    # Follow-up patterns based on intent
    FOLLOW_UP_PATTERNS = {
        "race_results": [
            "Who had the fastest lap at {circuit}?",
            "What was {driver}'s pit strategy?",
            "Show me {driver}'s lap times",
        ],
        "standings": [
            "How many points behind is {driver}?",
            "Show championship evolution",
            "Who has the most wins this season?",
        ],
        "comparison": [
            "Show their head to head this season",
            "Compare their qualifying pace",
            "Who has more podiums?",
        ],
        "lap_times": [
            "Show tire degradation comparison",
            "What were the sector times?",
            "Compare to teammate",
        ],
        "qualifying": [
            "What was the gap to pole?",
            "Show Q1/Q2/Q3 evolution",
            "Compare qualifying vs race pace",
        ],
        "pit_stops": [
            "Compare pit stop times",
            "What tire compounds were used?",
            "Show strategy comparison",
        ],
    }

    def __init__(
        self,
        redis_url: str | None = None,
        history_limit: int = 50,
        popular_limit: int = 20,
    ):
        """
        Initialize the query history manager.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379")
            history_limit: Max entries per user/session history
            popular_limit: Max popular queries to track
        """
        self.redis_url = redis_url
        self.history_limit = history_limit
        self.popular_limit = popular_limit

        self._redis: Any = None
        self._in_memory_history: dict[str, list[dict]] = {}
        self._in_memory_popular: dict[str, int] = {}

    async def initialize(self):
        """Initialize Redis connection."""
        if REDIS_AVAILABLE and self.redis_url:
            try:
                self._redis = redis.from_url(self.redis_url)
                await self._redis.ping()
                logger.info("QueryHistoryManager connected to Redis")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._redis = None
        else:
            logger.info("QueryHistoryManager using in-memory storage")

    async def add_query(
        self,
        user_id: str | None,
        session_id: str,
        query: str,
        preprocessed: dict,
    ):
        """
        Add a query to history.

        Args:
            user_id: User identifier (None for anonymous)
            session_id: Session identifier
            query: Original query text
            preprocessed: Preprocessed query data
        """
        entry = QueryHistoryEntry(
            query=query,
            normalized=preprocessed.get("normalized", query),
            intent=preprocessed.get("intent", "general"),
            drivers=preprocessed.get("drivers", []),
            teams=preprocessed.get("teams", []),
            circuits=preprocessed.get("circuits", []),
            year=preprocessed.get("year"),
            timestamp=datetime.utcnow().isoformat(),
            session_id=session_id,
        )

        if self._redis:
            await self._add_to_redis(user_id, session_id, entry)
        else:
            await self._add_to_memory(user_id, session_id, entry)

        # Track popular queries
        await self._track_popular(query, preprocessed)

        # Index by entities for related suggestions
        await self._index_by_entities(entry)

    async def _add_to_redis(
        self,
        user_id: str | None,
        session_id: str,
        entry: QueryHistoryEntry,
    ):
        """Add entry to Redis history."""
        entry_json = json.dumps(entry.to_dict())

        # Add to session history
        session_key = f"{self.PREFIX_SESSION_HISTORY}{session_id}"
        await self._redis.lpush(session_key, entry_json)
        await self._redis.ltrim(session_key, 0, self.history_limit - 1)
        await self._redis.expire(session_key, 86400)  # 24 hours

        # Add to user history if user_id provided
        if user_id:
            user_key = f"{self.PREFIX_USER_HISTORY}{user_id}"
            await self._redis.lpush(user_key, entry_json)
            await self._redis.ltrim(user_key, 0, self.history_limit - 1)
            await self._redis.expire(user_key, 604800)  # 7 days

    async def _add_to_memory(
        self,
        user_id: str | None,
        session_id: str,
        entry: QueryHistoryEntry,
    ):
        """Add entry to in-memory history."""
        session_key = f"session:{session_id}"
        if session_key not in self._in_memory_history:
            self._in_memory_history[session_key] = []
        self._in_memory_history[session_key].insert(0, entry.to_dict())
        self._in_memory_history[session_key] = \
            self._in_memory_history[session_key][:self.history_limit]

        if user_id:
            user_key = f"user:{user_id}"
            if user_key not in self._in_memory_history:
                self._in_memory_history[user_key] = []
            self._in_memory_history[user_key].insert(0, entry.to_dict())
            self._in_memory_history[user_key] = \
                self._in_memory_history[user_key][:self.history_limit]

    async def _track_popular(self, query: str, preprocessed: dict):
        """Track popular queries."""
        # Create a normalized key for the query
        normalized = preprocessed.get("normalized", query).lower().strip()
        query_hash = hashlib.md5(normalized.encode()).hexdigest()[:12]

        if self._redis:
            await self._redis.zincrby(self.PREFIX_POPULAR, 1, f"{query_hash}:{normalized}")
            # Keep only top N
            await self._redis.zremrangebyrank(self.PREFIX_POPULAR, 0, -self.popular_limit - 1)
            await self._redis.expire(self.PREFIX_POPULAR, 604800)  # 7 days
        else:
            self._in_memory_popular[normalized] = \
                self._in_memory_popular.get(normalized, 0) + 1

    async def _index_by_entities(self, entry: QueryHistoryEntry):
        """Index query by entities for related suggestions."""
        if not self._redis:
            return  # Skip for in-memory (simple implementation)

        entry_json = json.dumps(entry.to_dict())

        # Index by driver
        for driver in entry.drivers:
            key = f"{self.PREFIX_ENTITY_QUERIES}driver:{driver.lower()}"
            await self._redis.lpush(key, entry_json)
            await self._redis.ltrim(key, 0, 9)  # Keep last 10
            await self._redis.expire(key, 604800)

        # Index by team
        for team in entry.teams:
            key = f"{self.PREFIX_ENTITY_QUERIES}team:{team.lower()}"
            await self._redis.lpush(key, entry_json)
            await self._redis.ltrim(key, 0, 9)
            await self._redis.expire(key, 604800)

    async def get_history(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[QueryHistoryEntry]:
        """
        Get query history for user or session.

        Args:
            user_id: User identifier
            session_id: Session identifier
            limit: Max entries to return

        Returns:
            List of history entries (most recent first)
        """
        if self._redis:
            return await self._get_history_redis(user_id, session_id, limit)
        else:
            return await self._get_history_memory(user_id, session_id, limit)

    async def _get_history_redis(
        self,
        user_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[QueryHistoryEntry]:
        """Get history from Redis."""
        entries = []

        # Prefer user history, fall back to session
        if user_id:
            key = f"{self.PREFIX_USER_HISTORY}{user_id}"
            data = await self._redis.lrange(key, 0, limit - 1)
            entries = [
                QueryHistoryEntry.from_dict(json.loads(d))
                for d in data
            ]

        if not entries and session_id:
            key = f"{self.PREFIX_SESSION_HISTORY}{session_id}"
            data = await self._redis.lrange(key, 0, limit - 1)
            entries = [
                QueryHistoryEntry.from_dict(json.loads(d))
                for d in data
            ]

        return entries

    async def _get_history_memory(
        self,
        user_id: str | None,
        session_id: str | None,
        limit: int,
    ) -> list[QueryHistoryEntry]:
        """Get history from memory."""
        entries = []

        if user_id:
            key = f"user:{user_id}"
            data = self._in_memory_history.get(key, [])[:limit]
            entries = [QueryHistoryEntry.from_dict(d) for d in data]

        if not entries and session_id:
            key = f"session:{session_id}"
            data = self._in_memory_history.get(key, [])[:limit]
            entries = [QueryHistoryEntry.from_dict(d) for d in data]

        return entries

    async def get_suggestions(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        current_query: str | None = None,
        preprocessed: dict | None = None,
        limit: int = 5,
    ) -> list[QuerySuggestion]:
        """
        Get smart query suggestions.

        Combines:
        - Recent queries (personalized)
        - Popular queries (global trends)
        - Related queries (by entity)
        - Follow-up suggestions (by intent pattern)

        Args:
            user_id: User identifier
            session_id: Session identifier
            current_query: Current query (for follow-up suggestions)
            preprocessed: Preprocessed current query
            limit: Max suggestions to return

        Returns:
            List of suggestions
        """
        suggestions: list[QuerySuggestion] = []
        seen_queries: set[str] = set()

        # 1. Follow-up suggestions based on current query intent
        if preprocessed:
            follow_ups = await self._get_follow_up_suggestions(preprocessed)
            for s in follow_ups[:2]:
                if s.text.lower() not in seen_queries:
                    suggestions.append(s)
                    seen_queries.add(s.text.lower())

        # 2. Recent queries (personalized)
        history = await self.get_history(user_id, session_id, limit=5)
        for entry in history:
            if entry.query.lower() not in seen_queries:
                suggestions.append(QuerySuggestion(
                    text=entry.query,
                    type="recent",
                    confidence=0.9,
                    metadata={"intent": entry.intent},
                ))
                seen_queries.add(entry.query.lower())
                if len(suggestions) >= limit:
                    break

        # 3. Popular queries
        popular = await self._get_popular_queries(3)
        for query in popular:
            if query.lower() not in seen_queries:
                suggestions.append(QuerySuggestion(
                    text=query,
                    type="popular",
                    confidence=0.7,
                ))
                seen_queries.add(query.lower())

        # 4. Related by entity
        if preprocessed:
            related = await self._get_related_by_entity(preprocessed, 2)
            for query in related:
                if query.lower() not in seen_queries:
                    suggestions.append(QuerySuggestion(
                        text=query,
                        type="related",
                        confidence=0.6,
                    ))
                    seen_queries.add(query.lower())

        return suggestions[:limit]

    async def _get_follow_up_suggestions(
        self,
        preprocessed: dict,
    ) -> list[QuerySuggestion]:
        """Generate follow-up suggestions based on intent and entities."""
        suggestions = []
        intent = preprocessed.get("intent", "general")
        patterns = self.FOLLOW_UP_PATTERNS.get(intent, [])

        drivers = preprocessed.get("drivers", [])
        circuits = preprocessed.get("circuits", [])

        for pattern in patterns[:3]:
            text = pattern

            # Fill in placeholders
            if "{driver}" in text and drivers:
                text = text.replace("{driver}", drivers[0])
            elif "{driver}" in text:
                continue  # Skip if no driver available

            if "{circuit}" in text and circuits:
                text = text.replace("{circuit}", circuits[0])
            elif "{circuit}" in text:
                continue  # Skip if no circuit available

            suggestions.append(QuerySuggestion(
                text=text,
                type="follow_up",
                confidence=0.95,
                metadata={"base_intent": intent},
            ))

        return suggestions

    async def _get_popular_queries(self, limit: int) -> list[str]:
        """Get top popular queries."""
        if self._redis:
            results = await self._redis.zrevrange(
                self.PREFIX_POPULAR, 0, limit - 1, withscores=False
            )
            # Extract query text from "hash:query" format
            return [r.split(":", 1)[1] if ":" in r else r for r in results]
        else:
            sorted_queries = sorted(
                self._in_memory_popular.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            return [q for q, _ in sorted_queries[:limit]]

    async def _get_related_by_entity(
        self,
        preprocessed: dict,
        limit: int,
    ) -> list[str]:
        """Get related queries by shared entities."""
        if not self._redis:
            return []

        related = []

        # Check queries with same driver
        for driver in preprocessed.get("drivers", []):
            key = f"{self.PREFIX_ENTITY_QUERIES}driver:{driver.lower()}"
            data = await self._redis.lrange(key, 0, limit - 1)
            for d in data:
                entry = json.loads(d)
                if entry.get("query") and entry["query"] not in related:
                    related.append(entry["query"])

        return related[:limit]

    async def get_trending(self, hours: int = 24, limit: int = 5) -> list[str]:
        """Get trending queries in recent hours."""
        # For simplicity, just return popular queries
        # A full implementation would track timestamps
        return await self._get_popular_queries(limit)


# Singleton instance
_history_manager: QueryHistoryManager | None = None


async def get_history_manager(
    redis_url: str | None = None,
) -> QueryHistoryManager:
    """Get or create the singleton history manager."""
    global _history_manager
    if _history_manager is None:
        _history_manager = QueryHistoryManager(redis_url)
        await _history_manager.initialize()
    return _history_manager
