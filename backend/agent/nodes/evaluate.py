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

# Values of state["data_outcome"] set by this node
DATA_OK = "ok"  # Some tool returned usable data
DATA_RETRY = "retry"  # No usable data yet, looping back to PLAN
DATA_NONE = "no_data"  # No usable data and no retries left


def get_threshold_for_query_type(query_type: AnalysisType) -> float:
    """Get the completeness threshold for a specific query type."""
    return THRESHOLD_BY_QUERY_TYPE.get(query_type, DEFAULT_THRESHOLD)


def is_error_result(result: Any) -> bool:
    """True for a tool result that reports a failure instead of data.

    Tools report failures either as {"error": ...} or as a list whose rows
    are all {"error": ...}.
    """
    if isinstance(result, dict):
        return bool(result.get("error"))
    if isinstance(result, list) and result:
        return all(isinstance(row, dict) and row.get("error") for row in result)
    return False


def is_usable_result(result: Any) -> bool:
    """True for a tool result that carries data the answer can rest on."""
    if result is None or is_error_result(result):
        return False
    if isinstance(result, dict):
        # {"rows": []} and similar wrappers around nothing carry no data
        return any(value not in (None, "", [], {}) for value in result.values())
    if isinstance(result, (list, str)):
        return bool(result)
    return True


def count_usable_results(raw_data: dict) -> int:
    """Number of tool results that returned usable data."""
    return sum(1 for result in raw_data.values() if is_usable_result(result))


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

    # Zero usable tool data is never sufficient, whatever the score says:
    # retry while iterations remain, then report no data instead of answering.
    raw_data = state.get("raw_data", {})
    has_data = count_usable_results(raw_data) > 0
    out_of_retries = iteration >= MAX_ITERATIONS
    if has_data:
        data_outcome = DATA_OK
    elif out_of_retries:
        data_outcome = DATA_NONE
    else:
        data_outcome = DATA_RETRY

    # Check if we should continue or loop
    is_sufficient = has_data and (
        processed.completeness_score >= threshold or out_of_retries
    )
    will_loop = not is_sufficient and not out_of_retries

    # Generate feedback if insufficient
    feedback = ""
    if will_loop:
        feedback = _generate_feedback(processed, iteration)
        if not has_data:
            feedback = (
                f"None of the {len(raw_data)} tool calls returned usable data. "
                + feedback
            )
        logger.info(
            f"Evaluation: insufficient (score={processed.completeness_score:.2f}, "
            f"threshold={threshold:.2f} for {query_type.value}, "
            f"has_usable_data={has_data}), looping"
        )
    elif not has_data:
        logger.warning(
            f"Evaluation: no usable data from {len(raw_data)} tool calls after "
            f"{iteration + 1} attempts, stopping without an answer"
        )
    else:
        logger.info(
            f"Evaluation: sufficient (score={processed.completeness_score:.2f}, "
            f"threshold={threshold:.2f} for {query_type.value}), continuing"
        )

    result = EvaluationResult(
        is_sufficient=is_sufficient,
        score=processed.completeness_score if has_data else 0.0,
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
                "will_loop": will_loop,
                "data_outcome": data_outcome,
            },
        )

    return {
        "evaluation": result.model_dump(),
        "evaluation_feedback": feedback,
        "iteration_count": iteration + 1 if will_loop else iteration,
        "data_outcome": data_outcome,
    }


def should_continue(state: dict) -> Literal["plan", "generate", "no_data"]:
    """
    Router function: loop back to PLAN, continue to GENERATE, or stop with
    no data.

    Args:
        state: Current agent state

    Returns:
        Next node name ("plan", "generate" or "no_data")
    """
    if state.get("data_outcome") == DATA_NONE:
        return "no_data"

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
