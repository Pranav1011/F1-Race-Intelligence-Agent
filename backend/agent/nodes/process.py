"""PROCESS node - Aggregate raw data into analysis."""

import logging
from typing import Any

from agent.schemas.query import QueryUnderstanding, AnalysisType
from agent.schemas.analysis import (
    ProcessedAnalysis,
    ChartType,
    LapAnalysis,
    StintSummary,
)
from agent.processors.lap_analysis import process_lap_times, calculate_lap_statistics
from agent.processors.comparison import compute_driver_comparison, extract_comparison_insights
from agent.processors.strategy import process_stint_data
from agent.processors.visualization import select_viz_type

logger = logging.getLogger(__name__)


async def process_data(state: dict) -> dict[str, Any]:
    """
    PROCESS node: Aggregate raw data into structured analysis.

    This node does NOT use an LLM - it uses Python to compute
    statistics, comparisons, and insights from the raw data.

    Args:
        state: Current agent state with raw_data and query_understanding

    Returns:
        Updated state with processed_analysis
    """
    raw_data = state.get("raw_data", {})
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))

    processed = ProcessedAnalysis()

    # Track what data we have
    has_lap_times = False
    has_stints = False

    # Process lap times for each driver
    lap_times_by_driver: dict[str, list[dict]] = {}

    for tool_id, result in raw_data.items():
        if isinstance(result, dict) and result.get("error"):
            processed.missing_data.append(f"{tool_id}: {result['error']}")
            continue

        # Extract lap times
        if "laps" in tool_id.lower() or "lap_times" in tool_id.lower():
            has_lap_times = True
            driver = _extract_driver_from_tool_id(tool_id)
            if driver:
                if isinstance(result, list):
                    lap_times_by_driver[driver] = process_lap_times(result)
                elif isinstance(result, dict) and "data" in result:
                    lap_times_by_driver[driver] = process_lap_times(result["data"])

    # Calculate lap analysis for each driver
    for driver, laps in lap_times_by_driver.items():
        analysis = calculate_lap_statistics(laps, driver)
        processed.lap_analysis[driver] = analysis

        # Also process stint data
        stint_summaries = process_stint_data(laps, driver)
        if stint_summaries:
            processed.stint_summaries[driver] = stint_summaries
            has_stints = True

    # Compute driver comparisons
    if understanding.query_type == AnalysisType.COMPARISON and len(processed.lap_analysis) >= 2:
        drivers = list(processed.lap_analysis.keys())
        if len(drivers) >= 2:
            comparison = compute_driver_comparison(
                processed.lap_analysis[drivers[0]],
                processed.lap_analysis[drivers[1]],
            )
            processed.comparisons.append(comparison)

            # Extract insights
            insights = extract_comparison_insights(comparison)
            processed.key_insights.extend(insights)

    # Add general insights
    for driver, analysis in processed.lap_analysis.items():
        if analysis.fastest_lap:
            processed.key_insights.append(
                f"{driver}'s fastest lap: {analysis.fastest_lap:.3f}s (Lap {analysis.fastest_lap_number})"
            )
        if analysis.average_pace:
            processed.key_insights.append(
                f"{driver}'s average pace: {analysis.average_pace:.3f}s over {analysis.total_laps} laps"
            )

    # Calculate completeness score
    processed.completeness_score = _calculate_completeness(
        understanding, processed, has_lap_times, has_stints
    )

    # Calculate confidence score
    processed.confidence_score = _calculate_confidence(processed, raw_data)

    # Select recommended visualizations
    processed.recommended_viz = select_viz_type(
        understanding.query_type,
        understanding.metrics
    )

    logger.info(
        f"Processing complete: {len(processed.lap_analysis)} drivers analyzed, "
        f"completeness={processed.completeness_score:.2f}"
    )

    return {"processed_analysis": processed.model_dump()}


def _extract_driver_from_tool_id(tool_id: str) -> str | None:
    """Extract driver code from tool ID like 'laps_VER' or 'lap_times_NOR'."""
    parts = tool_id.split("_")
    for part in parts:
        if len(part) == 3 and part.isupper():
            return part
    return None


def _calculate_completeness(
    understanding: QueryUnderstanding,
    processed: ProcessedAnalysis,
    has_lap_times: bool,
    has_stints: bool,
) -> float:
    """Calculate how complete our data is for the query."""
    score = 0.0
    max_score = 0.0

    # Drivers requested vs found
    if understanding.drivers:
        max_score += 1.0
        found_drivers = len(processed.lap_analysis)
        requested_drivers = len(understanding.drivers)
        score += min(found_drivers / requested_drivers, 1.0) if requested_drivers > 0 else 0.5

    # Lap times (critical for most analysis)
    if understanding.query_type in [AnalysisType.COMPARISON, AnalysisType.PACE]:
        max_score += 1.0
        if has_lap_times:
            # Check if we have meaningful number of laps
            total_laps = sum(a.total_laps for a in processed.lap_analysis.values())
            if total_laps >= 50:  # At least half a race
                score += 1.0
            elif total_laps >= 20:
                score += 0.7
            else:
                score += 0.3

    # Strategy data
    if understanding.query_type == AnalysisType.STRATEGY:
        max_score += 1.0
        if has_stints and any(processed.stint_summaries.values()):
            score += 1.0

    # Comparison data
    if understanding.query_type == AnalysisType.COMPARISON:
        max_score += 1.0
        if processed.comparisons:
            score += 1.0

    return score / max_score if max_score > 0 else 0.5


def _calculate_confidence(processed: ProcessedAnalysis, raw_data: dict) -> float:
    """Calculate confidence in data quality."""
    # Count errors vs successful results
    error_count = len(processed.missing_data)
    total_count = len(raw_data)

    if total_count == 0:
        return 0.0

    success_rate = (total_count - error_count) / total_count

    # Penalize if we have very few data points
    total_laps = sum(a.total_laps for a in processed.lap_analysis.values())
    lap_penalty = min(total_laps / 100, 1.0)  # Full confidence at 100+ laps

    return success_rate * lap_penalty
