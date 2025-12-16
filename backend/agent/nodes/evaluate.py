"""EVALUATE node - Assess data sufficiency and decide whether to loop."""

import logging
from typing import Any, Literal

from agent.schemas.analysis import ProcessedAnalysis, EvaluationResult
from agent.schemas.query import QueryUnderstanding, AnalysisType

logger = logging.getLogger(__name__)

# Observability imports (optional - graceful degradation)
try:
    from observability.sentry_integration import add_breadcrumb
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 2

# Query-type specific completeness thresholds
# Some query types need more complete data than others
THRESHOLD_BY_QUERY_TYPE = {
    # High precision required - need accurate data
    AnalysisType.TELEMETRY: 0.8,      # Telemetry analysis needs precise data
    AnalysisType.COMPARISON: 0.75,    # Comparisons need data for all drivers
    AnalysisType.STRATEGY: 0.7,       # Strategy analysis needs stint data

    # Medium precision - can work with partial data
    AnalysisType.PACE: 0.65,          # Pace analysis can interpolate
    AnalysisType.INCIDENT: 0.6,       # Incidents often have limited data

    # Lower precision acceptable - more contextual
    AnalysisType.HISTORICAL: 0.5,     # Historical can use RAG context
    AnalysisType.PREDICTION: 0.5,     # Predictions are inherently uncertain
    AnalysisType.WHAT_IF: 0.5,        # What-if is speculative
    AnalysisType.GENERAL: 0.5,        # General queries are flexible
}

# Default threshold if query type not found
DEFAULT_THRESHOLD = 0.7


def get_threshold_for_query_type(query_type: AnalysisType) -> float:
    """Get the completeness threshold for a specific query type."""
    return THRESHOLD_BY_QUERY_TYPE.get(query_type, DEFAULT_THRESHOLD)


async def evaluate_data(state: dict) -> dict[str, Any]:
    """
    EVALUATE node: Assess if data is sufficient to generate a good response.

    Implements the CRAG (Corrective RAG) pattern - if data is insufficient,
    generates feedback and loops back to PLAN.

    Uses adaptive thresholds based on query type - telemetry analysis needs
    more complete data than historical/prediction queries.

    Args:
        state: Current agent state with processed_analysis

    Returns:
        Updated state with evaluation result
    """
    processed = ProcessedAnalysis(**state.get("processed_analysis", {}))
    iteration = state.get("iteration_count", 0)

    # Get query type for adaptive threshold
    understanding_data = state.get("query_understanding", {})
    query_type = AnalysisType.GENERAL
    if understanding_data:
        understanding = QueryUnderstanding(**understanding_data)
        query_type = understanding.query_type

    # Get adaptive threshold
    threshold = get_threshold_for_query_type(query_type)

    # Check if we should continue or loop
    is_sufficient = (
        processed.completeness_score >= threshold or
        iteration >= MAX_ITERATIONS
    )

    # Generate feedback if insufficient
    feedback = ""
    if not is_sufficient:
        feedback = _generate_feedback(processed, iteration)
        logger.info(
            f"Evaluation: insufficient (score={processed.completeness_score:.2f}, "
            f"threshold={threshold:.2f} for {query_type.value}), looping"
        )
    else:
        logger.info(
            f"Evaluation: sufficient (score={processed.completeness_score:.2f}, "
            f"threshold={threshold:.2f} for {query_type.value}), continuing"
        )

    result = EvaluationResult(
        is_sufficient=is_sufficient,
        score=processed.completeness_score,
        feedback=feedback,
        iteration=iteration,
    )

    # Add breadcrumb for observability
    if SENTRY_AVAILABLE:
        add_breadcrumb(
            message=f"EVALUATE node: score={processed.completeness_score:.2f}, sufficient={is_sufficient}",
            category="agent",
            level="info" if is_sufficient else "warning",
            data={
                "completeness_score": processed.completeness_score,
                "threshold": threshold,
                "query_type": query_type.value,
                "is_sufficient": is_sufficient,
                "iteration": iteration,
                "will_loop": not is_sufficient,
            },
        )

    return {
        "evaluation": result.model_dump(),
        "evaluation_feedback": feedback if not is_sufficient else "",
        "iteration_count": iteration + 1 if not is_sufficient else iteration,
    }


def should_continue(state: dict) -> Literal["plan", "generate"]:
    """
    Router function: Decide whether to loop back to PLAN or continue to GENERATE.

    Args:
        state: Current agent state

    Returns:
        Next node name ("plan" or "generate")
    """
    evaluation = state.get("evaluation", {})
    is_sufficient = evaluation.get("is_sufficient", True)

    if is_sufficient:
        return "generate"
    else:
        return "plan"


def _generate_feedback(processed: ProcessedAnalysis, iteration: int) -> str:
    """Generate feedback for the PLAN node about what data is missing."""
    feedback_parts = []

    # Missing data from errors
    if processed.missing_data:
        feedback_parts.append(
            f"The following data could not be retrieved: {', '.join(processed.missing_data)}"
        )

    # Check if we need more lap data
    total_laps = sum(a.total_laps for a in processed.lap_analysis.values())
    if total_laps < 50:
        feedback_parts.append(
            f"Only {total_laps} laps retrieved. Need more lap data - "
            "increase limit or fetch additional sessions."
        )

    # Check if comparison data is missing
    if not processed.comparisons and len(processed.lap_analysis) >= 2:
        feedback_parts.append(
            "Comparison data not computed - ensure lap times are retrieved for all drivers."
        )

    # Check if stint data is missing
    if not processed.stint_summaries:
        feedback_parts.append(
            "No stint/tire data available. Consider fetching stint summaries."
        )

    # Default feedback if nothing specific
    if not feedback_parts:
        feedback_parts.append(
            f"Data completeness is {processed.completeness_score:.0%}. "
            "Try fetching additional data sources."
        )

    return " ".join(feedback_parts)
