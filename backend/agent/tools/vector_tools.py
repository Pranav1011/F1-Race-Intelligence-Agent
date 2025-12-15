"""
Vector Search Tools

Tools for semantic search over race reports, regulations, and past analyses.
Uses the RAG service with hybrid search (semantic + keyword).
"""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# RAG service instance (initialized at startup)
_rag_service = None


async def init_rag(host: str = "qdrant", port: int = 6333):
    """Initialize the RAG service."""
    global _rag_service
    from agent.rag.service import RAGService
    _rag_service = RAGService(qdrant_host=host, qdrant_port=port)
    _rag_service.initialize()
    logger.info(f"RAG service initialized for {host}:{port}")


def get_rag_service():
    """Get the RAG service instance."""
    return _rag_service


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
    if not _rag_service:
        return [{"error": "RAG service not initialized"}]

    try:
        results = await _rag_service.search_race_context(
            query=query,
            race_id=race_id,
            season=season,
            drivers=drivers,
            limit=limit,
        )
        return results

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
    if not _rag_service:
        return [{"error": "RAG service not initialized"}]

    try:
        # Build filters for Reddit-specific search
        filters = {}
        if race_id:
            filters["race_id"] = race_id
        if min_score:
            filters["min_score"] = min_score

        # Use hybrid search on reddit_discussions collection
        result = await _rag_service.hybrid_search(
            query=query,
            collection="reddit_discussions",
            limit=limit,
            filters=filters if filters else None,
        )

        return [
            {
                "content": r.content,
                "post_id": r.metadata.get("post_id", ""),
                "score": r.metadata.get("score", 0),
                "quality_score": r.metadata.get("quality_score", 0),
                "relevance_score": r.score,
            }
            for r in result.results
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
    if not _rag_service:
        return [{"error": "RAG service not initialized"}]

    try:
        results = await _rag_service.search_regulations(
            query=query,
            document_type=document_type,
            year=year,
            limit=limit,
        )
        return results

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
    if not _rag_service:
        return [{"error": "RAG service not initialized"}]

    try:
        results = await _rag_service.search_similar_analyses(
            query=query,
            query_type=query_type,
            limit=limit,
        )
        return results

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
    if not _rag_service:
        return {"error": "RAG service not initialized"}

    try:
        doc_id = await _rag_service.store_analysis(
            query=query,
            analysis=analysis,
            query_type=query_type,
            drivers=drivers,
            race_id=race_id,
        )
        return {"status": "stored", "id": doc_id}

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
