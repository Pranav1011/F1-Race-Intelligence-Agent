"""
Data-service preflight.

Before the agent spends LLM calls on understanding and planning, check that at
least one data backend can be reached. With every backend down (a fresh clone
without Docker, say) no plan can return data, so the honest no-data reply is
sent at once instead of after several slow model calls.
"""

import asyncio
import contextlib
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Per-service TCP connect timeout; all services are probed concurrently
PROBE_TIMEOUT_S = 1.0

# How long a result is reused before the services are probed again
CACHE_TTL_S = 30.0


@dataclass(frozen=True)
class DataService:
    """A data backend the agent's tools query, named as the no-data reply names it."""

    label: str
    host: str
    port: int


def configured_services() -> list[DataService]:
    """The data backends, from the same settings and defaults as api/main.py."""
    timescale = urlparse(
        os.getenv("TIMESCALE_URI", "postgresql://timescaledb:5432/f1_telemetry")
    )
    neo4j = urlparse(os.getenv("NEO4J_URI", "bolt://neo4j:7687"))
    return [
        DataService(
            "the race database (TimescaleDB)",
            timescale.hostname or "timescaledb",
            timescale.port or 5432,
        ),
        DataService("the knowledge graph (Neo4j)", neo4j.hostname or "neo4j", neo4j.port or 7687),
        DataService(
            "race report search (Qdrant)",
            os.getenv("QDRANT_HOST", "qdrant"),
            int(os.getenv("QDRANT_PORT", "6333")),
        ),
    ]


async def probe_service(service: DataService, timeout: float = PROBE_TIMEOUT_S) -> bool:
    """True when a TCP connection to the service opens within the timeout."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(service.host, service.port), timeout
        )
    except (OSError, TimeoutError):
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


class DataServicePreflight:
    """Cached reachability check of the configured data backends."""

    def __init__(self, ttl_s: float = CACHE_TTL_S):
        self.ttl_s = ttl_s
        self._checked_at: float | None = None
        self._unreachable: list[str] = []
        self._lock = asyncio.Lock()

    async def unreachable_services(self) -> list[str]:
        """Labels of the backends that could not be reached (cached for ttl_s)."""
        async with self._lock:
            now = time.monotonic()
            if self._checked_at is None or now - self._checked_at >= self.ttl_s:
                services = configured_services()
                reachable = await asyncio.gather(*(probe_service(s) for s in services))
                self._unreachable = [s.label for s, ok in zip(services, reachable, strict=True) if not ok]
                self._checked_at = now
                if self._unreachable:
                    logger.info(f"Preflight: unreachable data services: {self._unreachable}")
            return list(self._unreachable)

    async def all_unreachable(self) -> list[str]:
        """The unreachable labels when every backend is down, else an empty list."""
        unreachable = await self.unreachable_services()
        return unreachable if len(unreachable) == len(configured_services()) else []
