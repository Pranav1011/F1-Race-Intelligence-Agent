"""
Vector Search Tools

Tools for semantic search over race reports, regulations, and past analyses.
"""

import logging
from typing import Any

from langchain_core.tools import tool
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

# Client instance (initialized at startup)
_client: QdrantClient | None = None
_embedder = None  # Embedding model


def init_client(host: str, port: int):
    """Initialize the Qdrant client."""
    global _client
    _client = QdrantClient(host=host, port=port, check_compatibility=False)
    logger.info(f"Qdrant tool client initialized for {host}:{port}")


def init_embedder(model_name: str = "BAAI/bge-base-en-v1.5"):
    """Initialize the embedding model."""
    global _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(model_name)
        logger.info(f"Embedder initialized with {model_name}")
    except Exception as e:
        logger.warning(f"Failed to initialize embedder: {e}")


def _embed_text(text: str) -> list[float]:
    """Embed text using the configured embedder."""
    if _embedder is None:
        raise RuntimeError("Embedder not initialized")
    return _embedder.encode(text).tolist()


@tool
async def search_race_reports(
    query: str,
    race_id: str | None = None,
    season: int | None = None,
    drivers: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Search race reports and journalist articles.

    Args:
        query: Natural language search query
        race_id: Filter by specific race
        season: Filter by season year
        drivers: Filter by mentioned drivers
        limit: Maximum results

    Returns:
        Relevant article excerpts with source information
    """
    if not _client or not _embedder:
        return [{"error": "Vector search not initialized"}]

    try:
        # Build filter conditions
        filter_conditions = []

        if race_id:
            filter_conditions.append(
                models.FieldCondition(
                    key="race_id",
                    match=models.MatchValue(value=race_id),
                )
            )

        if season:
            filter_conditions.append(
                models.FieldCondition(
                    key="season",
                    match=models.MatchValue(value=season),
                )
            )

        if drivers:
            filter_conditions.append(
                models.FieldCondition(
                    key="drivers",
                    match=models.MatchAny(any=drivers),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        # Embed query and search
        query_vector = _embed_text(query)

        results = _client.search(
            collection_name="race_reports",
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {
                "content": hit.payload.get("content", ""),
                "source": hit.payload.get("source", ""),
                "url": hit.payload.get("url", ""),
                "race_id": hit.payload.get("race_id", ""),
                "score": hit.score,
            }
            for hit in results
        ]

    except Exception as e:
        logger.error(f"Error searching race reports: {e}")
        return [{"error": str(e)}]


@tool
async def search_reddit_discussions(
    query: str,
    race_id: str | None = None,
    min_score: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Search Reddit discussions from r/formula1.

    Args:
        query: Natural language search query
        race_id: Filter by specific race
        min_score: Minimum upvote score
        limit: Maximum results

    Returns:
        Relevant discussion excerpts with community engagement metrics
    """
    if not _client or not _embedder:
        return [{"error": "Vector search not initialized"}]

    try:
        filter_conditions = []

        if race_id:
            filter_conditions.append(
                models.FieldCondition(
                    key="race_id",
                    match=models.MatchValue(value=race_id),
                )
            )

        if min_score:
            filter_conditions.append(
                models.FieldCondition(
                    key="score",
                    range=models.Range(gte=min_score),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        query_vector = _embed_text(query)

        results = _client.search(
            collection_name="reddit_discussions",
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {
                "content": hit.payload.get("content", ""),
                "post_id": hit.payload.get("post_id", ""),
                "score": hit.payload.get("score", 0),
                "quality_score": hit.payload.get("quality_score", 0),
                "relevance_score": hit.score,
            }
            for hit in results
        ]

    except Exception as e:
        logger.error(f"Error searching Reddit: {e}")
        return [{"error": str(e)}]


@tool
async def search_regulations(
    query: str,
    document_type: str | None = None,
    year: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Search FIA sporting and technical regulations.

    Args:
        query: Natural language search query
        document_type: "sporting" or "technical"
        year: Regulation year
        limit: Maximum results

    Returns:
        Relevant regulation excerpts with article references
    """
    if not _client or not _embedder:
        return [{"error": "Vector search not initialized"}]

    try:
        filter_conditions = []

        if document_type:
            filter_conditions.append(
                models.FieldCondition(
                    key="document_type",
                    match=models.MatchValue(value=document_type),
                )
            )

        if year:
            filter_conditions.append(
                models.FieldCondition(
                    key="year",
                    match=models.MatchValue(value=year),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        query_vector = _embed_text(query)

        results = _client.search(
            collection_name="regulations",
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {
                "content": hit.payload.get("content", ""),
                "document_type": hit.payload.get("document_type", ""),
                "section": hit.payload.get("section", ""),
                "article_number": hit.payload.get("article_number", ""),
                "year": hit.payload.get("year", ""),
                "score": hit.score,
            }
            for hit in results
        ]

    except Exception as e:
        logger.error(f"Error searching regulations: {e}")
        return [{"error": str(e)}]


@tool
async def search_past_analyses(
    query: str,
    query_type: str | None = None,
    limit: int = 3,
) -> list[dict]:
    """
    Search previous agent analyses for similar questions.

    Args:
        query: Current user query
        query_type: Type of analysis (historical, what_if, comparison)
        limit: Maximum results

    Returns:
        Similar past analyses that might inform the current response
    """
    if not _client or not _embedder:
        return [{"error": "Vector search not initialized"}]

    try:
        filter_conditions = []

        if query_type:
            filter_conditions.append(
                models.FieldCondition(
                    key="query_type",
                    match=models.MatchValue(value=query_type),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        query_vector = _embed_text(query)

        results = _client.search(
            collection_name="past_analyses",
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {
                "original_query": hit.payload.get("query", ""),
                "analysis": hit.payload.get("content", ""),
                "query_type": hit.payload.get("query_type", ""),
                "drivers": hit.payload.get("drivers", []),
                "score": hit.score,
            }
            for hit in results
        ]

    except Exception as e:
        logger.error(f"Error searching past analyses: {e}")
        return [{"error": str(e)}]


@tool
async def store_analysis(
    query: str,
    analysis: str,
    query_type: str,
    drivers: list[str] | None = None,
    race_id: str | None = None,
) -> dict:
    """
    Store an analysis for future reference.

    Args:
        query: Original user query
        analysis: Generated analysis response
        query_type: Type of analysis
        drivers: Drivers mentioned in the analysis
        race_id: Related race ID

    Returns:
        Storage confirmation
    """
    if not _client or not _embedder:
        return {"error": "Vector search not initialized"}

    try:
        import uuid
        from datetime import datetime

        # Embed the query for future similarity search
        query_vector = _embed_text(query)

        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=query_vector,
            payload={
                "query": query,
                "content": analysis,
                "query_type": query_type,
                "drivers": drivers or [],
                "race_id": race_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        _client.upsert(
            collection_name="past_analyses",
            points=[point],
        )

        return {"status": "stored", "id": point.id}

    except Exception as e:
        logger.error(f"Error storing analysis: {e}")
        return {"error": str(e)}


# Export all tools
VECTOR_TOOLS = [
    search_race_reports,
    search_reddit_discussions,
    search_regulations,
    search_past_analyses,
    store_analysis,
]
