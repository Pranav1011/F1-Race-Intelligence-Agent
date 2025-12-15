"""
F1 Race Intelligence Agent - FastAPI Application

Main entry point for the backend API.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import chat, data, sessions

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("Starting F1 Race Intelligence API...")

    # Initialize database pools for agent tools
    try:
        # TimescaleDB pool
        from agent.tools.timescale_tools import init_pool as init_timescale
        timescale_url = os.getenv(
            "TIMESCALE_URI",
            "postgresql://f1:f1_password@timescaledb:5432/f1_telemetry"
        )
        await init_timescale(timescale_url)
        logger.info("TimescaleDB pool initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize TimescaleDB pool: {e}")

    try:
        # Neo4j driver
        from agent.tools.neo4j_tools import init_driver as init_neo4j
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "f1_password")
        await init_neo4j(neo4j_uri, neo4j_user, neo4j_password)
        logger.info("Neo4j driver initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Neo4j driver: {e}")

    try:
        # RAG service (Qdrant + embeddings)
        from agent.tools.vector_tools import init_rag
        qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        await init_rag(qdrant_host, qdrant_port)
        logger.info("RAG service initialized (Qdrant + embeddings)")
    except Exception as e:
        logger.warning(f"Failed to initialize RAG service: {e}")

    try:
        # Redis cache
        from db.cache import init_redis
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
        await init_redis(redis_url)
        logger.info("Redis cache initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Redis cache: {e}")

    print("API startup complete")

    yield

    # Shutdown
    print("Shutting down API...")
    try:
        from agent.tools.timescale_tools import close_pool as close_timescale
        await close_timescale()
    except Exception:
        pass

    try:
        from agent.tools.neo4j_tools import close_driver as close_neo4j
        await close_neo4j()
    except Exception:
        pass

    try:
        from db.cache import close_redis
        await close_redis()
    except Exception:
        pass


app = FastAPI(
    title="F1 Race Intelligence Agent",
    description="AI-powered F1 race analysis and insights",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(data.router, prefix="/api/v1/data", tags=["data"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "F1 Race Intelligence Agent",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    from agent.tools.neo4j_tools import _driver as neo4j_driver
    from agent.tools.timescale_tools import _pool as timescale_pool
    from agent.tools.vector_tools import get_rag_service
    from db.cache import cache_stats, get_redis

    redis_client = get_redis()
    rag_service = get_rag_service()

    checks = {
        "api": "healthy",
        "timescaledb": "healthy" if timescale_pool else "not_connected",
        "neo4j": "healthy" if neo4j_driver else "not_connected",
        "qdrant": "healthy" if rag_service and rag_service.health_check() else "not_connected",
        "redis": "healthy" if redis_client else "not_connected",
    }

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"

    # Get cache stats if Redis is connected
    cache_info = await cache_stats() if redis_client else None

    # Get RAG stats if available
    rag_stats = None
    if rag_service:
        rag_stats = rag_service.get_collection_stats()

    return {
        "status": overall,
        "checks": checks,
        "cache": cache_info,
        "rag_collections": rag_stats,
    }
