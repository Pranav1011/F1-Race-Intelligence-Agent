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
    has_head_to_head = False

    # Process lap times for each driver
    lap_times_by_driver: dict[str, list[dict]] = {}
    head_to_head_data: list[dict] = []

    for tool_id, result in raw_data.items():
        if isinstance(result, dict) and result.get("error"):
            processed.missing_data.append(f"{tool_id}: {result['error']}")
            continue

        # Process head-to-head comparison data (from get_head_to_head tool)
        # Check multiple patterns: "head_to_head", "h2h", "head2head", "comparison"
        tool_lower = tool_id.lower()
        is_h2h_tool = (
            "head_to_head" in tool_lower or
            "h2h" in tool_lower or
            "head2head" in tool_lower or
            ("compare" in tool_lower and "driver" in tool_lower)
        )

        # Also detect h2h data by structure (has pace_delta, comparable_laps fields)
        is_h2h_data = False
        if isinstance(result, list) and len(result) > 0:
            first_item = result[0] if isinstance(result[0], dict) else {}
            is_h2h_data = "pace_delta" in first_item or "comparable_laps" in first_item

        if is_h2h_tool or is_h2h_data:
            if isinstance(result, list) and len(result) > 0:
                has_head_to_head = True
                head_to_head_data.extend(result)
                # Mark as having lap times since h2h includes pace data
                has_lap_times = True
                logger.info(f"Found head_to_head data: {len(result)} comparisons")

        # Extract lap times
        elif "laps" in tool_id.lower() or "lap_times" in tool_id.lower():
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

    # Process head-to-head comparison data (pre-computed from materialized views)
    if has_head_to_head and head_to_head_data:
        for h2h in head_to_head_data:
            driver_1 = h2h.get("driver_1", "")
            driver_2 = h2h.get("driver_2", "")

            # Create lap analysis entries from h2h data for each driver
            if driver_1 and driver_1 not in processed.lap_analysis:
                processed.lap_analysis[driver_1] = LapAnalysis(
                    driver=driver_1,
                    total_laps=h2h.get("comparable_laps", 0),
                    average_pace=h2h.get("driver_1_pace"),
                    fastest_lap=h2h.get("driver_1_fastest"),
                    consistency=0.0,  # Not in h2h data
                )
            if driver_2 and driver_2 not in processed.lap_analysis:
                processed.lap_analysis[driver_2] = LapAnalysis(
                    driver=driver_2,
                    total_laps=h2h.get("comparable_laps", 0),
                    average_pace=h2h.get("driver_2_pace"),
                    fastest_lap=h2h.get("driver_2_fastest"),
                    consistency=0.0,
                )

            # Add comparison insights from head-to-head
            pace_delta = h2h.get("pace_delta", 0)
            fastest_delta = h2h.get("fastest_delta", 0)
            comparable_laps = h2h.get("comparable_laps", 0)
            event_name = h2h.get("event_name", "")
            year = h2h.get("year", "")

            # Pace comparison
            if pace_delta is not None:
                faster_driver = driver_1 if pace_delta < 0 else driver_2
                slower_driver = driver_2 if pace_delta < 0 else driver_1
                delta_abs = abs(pace_delta)
                processed.key_insights.append(
                    f"Average pace: {faster_driver} was {delta_abs:.3f}s faster than {slower_driver} per lap at {year} {event_name}"
                )

            # Fastest lap comparison
            if fastest_delta is not None and fastest_delta != 0:
                faster_driver = driver_1 if fastest_delta < 0 else driver_2
                delta_abs = abs(fastest_delta)
                processed.key_insights.append(
                    f"Fastest lap: {faster_driver} set the faster lap by {delta_abs:.3f}s"
                )

            # Sector deltas
            s1_delta = h2h.get("s1_delta", 0)
            s2_delta = h2h.get("s2_delta", 0)
            s3_delta = h2h.get("s3_delta", 0)
            if s1_delta or s2_delta or s3_delta:
                sector_insights = []
                if s1_delta: sector_insights.append(f"S1: {'+' if s1_delta > 0 else ''}{s1_delta:.3f}s")
                if s2_delta: sector_insights.append(f"S2: {'+' if s2_delta > 0 else ''}{s2_delta:.3f}s")
                if s3_delta: sector_insights.append(f"S3: {'+' if s3_delta > 0 else ''}{s3_delta:.3f}s")
                processed.key_insights.append(
                    f"Sector deltas ({driver_1} vs {driver_2}): {', '.join(sector_insights)}"
                )

            # Add context about comparison
            if comparable_laps:
                processed.key_insights.append(
                    f"Analysis based on {comparable_laps} comparable racing laps"
                )

            logger.info(f"Processed head-to-head: {driver_1} vs {driver_2}, {comparable_laps} laps")

    # Compute driver comparisons from lap analysis
    if understanding.query_type == AnalysisType.COMPARISON and len(processed.lap_analysis) >= 2:
        drivers = list(processed.lap_analysis.keys())
        if len(drivers) >= 2 and not has_head_to_head:
            # Only compute from lap data if we don't have h2h data
            comparison = compute_driver_comparison(
                processed.lap_analysis[drivers[0]],
                processed.lap_analysis[drivers[1]],
            )
            processed.comparisons.append(comparison)

            # Extract insights
            insights = extract_comparison_insights(comparison)
            processed.key_insights.extend(insights)

    # Add general insights (only if not from h2h)
    if not has_head_to_head:
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
        understanding, processed, has_lap_times, has_stints, has_head_to_head
    )

    # Calculate confidence score
    processed.confidence_score = _calculate_confidence(processed, raw_data, has_head_to_head)

    # Select recommended visualizations with smarter logic
    has_lap_data = bool(lap_times_by_driver) or has_head_to_head
    num_drivers = len(processed.lap_analysis)

    processed.recommended_viz = select_viz_type(
        understanding.query_type,
        understanding.metrics,
        num_drivers=num_drivers,
        has_lap_data=has_lap_data,
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
    has_head_to_head: bool = False,
) -> float:
    """Calculate how complete our data is for the query."""
    score = 0.0
    max_score = 0.0

    # For comparison queries with head-to-head data, we have everything we need
    if has_head_to_head and understanding.query_type == AnalysisType.COMPARISON:
        # Head-to-head data provides complete comparison information
        return 0.95  # High score - we have pre-computed comparison data

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
        if processed.comparisons or has_head_to_head:
            score += 1.0

    return score / max_score if max_score > 0 else 0.5


def _calculate_confidence(
    processed: ProcessedAnalysis,
    raw_data: dict,
    has_head_to_head: bool = False,
) -> float:
    """Calculate confidence in data quality."""
    # Count errors vs successful results
    error_count = len(processed.missing_data)
    total_count = len(raw_data)

    if total_count == 0:
        return 0.0

    success_rate = (total_count - error_count) / total_count

    # For head-to-head comparisons, we have pre-computed high-quality data
    if has_head_to_head and processed.key_insights:
        # High confidence for h2h data with insights
        return min(0.85 + (0.15 * success_rate), 1.0)

    # Penalize if we have very few data points
    total_laps = sum(a.total_laps for a in processed.lap_analysis.values())

    # More lenient lap threshold - 30 laps is reasonable for focused analysis
    if total_laps >= 30:
        lap_penalty = 1.0
    elif total_laps >= 15:
        lap_penalty = 0.8
    elif total_laps >= 5:
        lap_penalty = 0.6
    else:
        lap_penalty = min(total_laps / 30, 0.5)

    return success_rate * lap_penalty
