"""
F1 Race Intelligence Agent - FastAPI Application

Main entry point for the backend API.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import chat, data, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("Starting F1 Race Intelligence API...")

    # TODO: Initialize database pools
    # app.state.timescale_pool = await create_timescale_pool()
    # app.state.neo4j_driver = create_neo4j_driver()
    # app.state.qdrant_client = create_qdrant_client()
    # app.state.redis = await create_redis_pool()

    # TODO: Initialize agent
    # app.state.agent = await create_agent(app.state)

    # TODO: Initialize observability
    # init_sentry()

    print("API startup complete")

    yield

    # Shutdown
    print("Shutting down API...")
    # TODO: Close connections
    # await app.state.timescale_pool.close()
    # await app.state.neo4j_driver.close()
    # await app.state.redis.close()


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
    # TODO: Add actual health checks for databases
    checks = {
        "api": "healthy",
        "timescaledb": "not_configured",
        "neo4j": "not_configured",
        "qdrant": "not_configured",
        "redis": "not_configured",
    }

    return {
        "status": "healthy",
        "checks": checks,
    }
