# Backend Dockerfile for F1 Race Intelligence Agent

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN pip install uv

# Copy dependency file first for caching
COPY pyproject.toml ./

# Extract and install dependencies only (skip package build)
RUN uv pip install --system \
    fastapi uvicorn pydantic pydantic-settings websockets \
    langgraph langchain langchain-core langchain-openai langchain-groq langchain-google-genai langchain-community \
    asyncpg neo4j qdrant-client redis \
    fastf1 mem0ai ollama \
    sentence-transformers cohere \
    langfuse "sentry-sdk[fastapi]" structlog \
    httpx pandas numpy python-dotenv tenacity orjson python-multipart \
    pytest pytest-asyncio pytest-cov ruff

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default command
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
