"""ENRICH node - Fetch RAG context to enhance response generation."""

import logging
from typing import Any

from agent.schemas.query import QueryUnderstanding, AnalysisType
from agent.schemas.analysis import ProcessedAnalysis

logger = logging.getLogger(__name__)

# Observability imports (optional - graceful degradation)
try:
    from observability.sentry_integration import add_breadcrumb
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# RAG service import
_rag_service = None


def _get_rag_service():
    """Get the RAG service instance."""
    global _rag_service
    if _rag_service is None:
        try:
            from agent.tools.vector_tools import get_rag_service
            _rag_service = get_rag_service()
        except Exception as e:
            logger.warning(f"Could not get RAG service: {e}")
    return _rag_service


async def enrich_context(state: dict) -> dict[str, Any]:
    """
    ENRICH node: Fetch RAG context to enhance response generation.

    Searches for:
    - Race reports/articles for historical context
    - Reddit discussions for community insights
    - Regulations if query involves rules/penalties
    - Past analyses for consistency

    Args:
        state: Current agent state with query_understanding and processed_analysis

    Returns:
        Updated state with enriched_context
    """
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))
    processed = ProcessedAnalysis(**state.get("processed_analysis", {}))

    # Build search query from understanding
    search_query = _build_search_query(understanding, state)

    enriched_context = {
        "race_context": [],
        "community_insights": [],
        "regulations": [],
        "similar_analyses": [],
    }

    rag_service = _get_rag_service()
    if not rag_service:
        logger.warning("RAG service not available, skipping enrichment")
        return {"enriched_context": enriched_context}

    # Add breadcrumb for observability
    if SENTRY_AVAILABLE:
        add_breadcrumb(
            message=f"ENRICH node fetching context for {understanding.query_type}",
            category="agent",
            level="info",
            data={"search_query": search_query[:100]},
        )

    try:
        # 1. Always search race reports for context
        race_context = await _search_race_context(
            rag_service, search_query, understanding
        )
        enriched_context["race_context"] = race_context

        # 2. Search Reddit for community insights
        community_insights = await _search_community(
            rag_service, search_query, understanding
        )
        enriched_context["community_insights"] = community_insights

        # 3. Search regulations if query involves rules/incidents/penalties
        if _needs_regulations(understanding):
            regulations = await _search_regulations(
                rag_service, search_query, understanding
            )
            enriched_context["regulations"] = regulations

        # 4. Search past analyses for consistency
        similar_analyses = await _search_past_analyses(
            rag_service, search_query, understanding
        )
        enriched_context["similar_analyses"] = similar_analyses

        # Log enrichment results
        total_docs = sum(len(v) for v in enriched_context.values())
        logger.info(f"ENRICH: Retrieved {total_docs} context documents")

    except Exception as e:
        logger.error(f"Error in ENRICH node: {e}")
        if SENTRY_AVAILABLE:
            from observability.sentry_integration import capture_exception
            capture_exception(e, extra={"node": "enrich"})

    return {"enriched_context": enriched_context}


def _build_search_query(understanding: QueryUnderstanding, state: dict) -> str:
    """Build a search query from the understanding."""
    parts = []

    # Add drivers
    if understanding.drivers:
        parts.append(" ".join(understanding.drivers))

    # Add teams
    if understanding.teams:
        parts.append(" ".join(understanding.teams))

    # Add races
    if understanding.races:
        parts.append(" ".join(understanding.races))

    # Add query type context
    query_type_context = {
        AnalysisType.COMPARISON: "comparison battle performance",
        AnalysisType.STRATEGY: "strategy pit stop undercut overcut",
        AnalysisType.PACE: "pace lap times speed",
        AnalysisType.TELEMETRY: "telemetry speed throttle brake",
        AnalysisType.INCIDENT: "incident crash penalty investigation",
        AnalysisType.PREDICTION: "prediction forecast expectation",
        AnalysisType.HISTORICAL: "historical record statistics",
        AnalysisType.WHAT_IF: "scenario alternative strategy",
    }
    if understanding.query_type in query_type_context:
        parts.append(query_type_context[understanding.query_type])

    # Add the original query for context
    from agent.nodes.understand import get_last_human_message
    original_query = get_last_human_message(state)
    if original_query:
        parts.append(original_query)

    return " ".join(parts)


async def _search_race_context(
    rag_service,
    query: str,
    understanding: QueryUnderstanding,
) -> list[dict]:
    """Search race reports for context."""
    try:
        # Build filters
        filters = {}
        if understanding.seasons:
            filters["season"] = understanding.seasons[0]

        result = await rag_service.hybrid_search(
            query=query,
            collection="race_reports",
            limit=3,
            filters=filters if filters else None,
        )

        return [
            {
                "content": r.content[:500],
                "source": r.metadata.get("source", "race_report"),
                "relevance": r.score,
            }
            for r in result.results
        ]
    except Exception as e:
        logger.warning(f"Error searching race context: {e}")
        return []


async def _search_community(
    rag_service,
    query: str,
    understanding: QueryUnderstanding,
) -> list[dict]:
    """Search Reddit discussions for community insights."""
    try:
        result = await rag_service.hybrid_search(
            query=query,
            collection="reddit_discussions",
            limit=3,
        )

        return [
            {
                "content": r.content[:400],
                "score": r.metadata.get("score", 0),
                "relevance": r.score,
            }
            for r in result.results
        ]
    except Exception as e:
        logger.warning(f"Error searching community: {e}")
        return []


async def _search_regulations(
    rag_service,
    query: str,
    understanding: QueryUnderstanding,
) -> list[dict]:
    """Search FIA regulations."""
    try:
        # Build regulation-specific query
        reg_query = query
        if understanding.query_type == AnalysisType.INCIDENT:
            reg_query = f"penalty rules {query}"

        result = await rag_service.hybrid_search(
            query=reg_query,
            collection="regulations",
            limit=2,
        )

        return [
            {
                "content": r.content[:400],
                "article": r.metadata.get("article", ""),
                "relevance": r.score,
            }
            for r in result.results
        ]
    except Exception as e:
        logger.warning(f"Error searching regulations: {e}")
        return []


async def _search_past_analyses(
    rag_service,
    query: str,
    understanding: QueryUnderstanding,
) -> list[dict]:
    """Search past agent analyses for consistency."""
    try:
        result = await rag_service.hybrid_search(
            query=query,
            collection="past_analyses",
            limit=2,
        )

        return [
            {
                "query": r.metadata.get("query", ""),
                "analysis_preview": r.content[:300],
                "relevance": r.score,
            }
            for r in result.results
        ]
    except Exception as e:
        logger.warning(f"Error searching past analyses: {e}")
        return []


def _needs_regulations(understanding: QueryUnderstanding) -> bool:
    """Check if query needs regulation context."""
    # Queries that benefit from regulation context
    regulation_types = {
        AnalysisType.INCIDENT,
        AnalysisType.STRATEGY,  # For pit lane rules, etc.
    }

    if understanding.query_type in regulation_types:
        return True

    # Check for regulation-related keywords in sub_queries
    reg_keywords = ["penalty", "rule", "regulation", "legal", "illegal", "steward"]
    for sub_query in understanding.sub_queries:
        if any(kw in sub_query.lower() for kw in reg_keywords):
            return True

    return False
