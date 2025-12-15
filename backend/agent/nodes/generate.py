"""GENERATE node - Generate response with visualization."""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.schemas.query import QueryUnderstanding
from agent.schemas.analysis import ProcessedAnalysis, ChartType
from agent.prompts.generate import GENERATE_SYSTEM, GENERATE_PROMPT
from agent.processors.visualization import generate_viz_spec
from agent.llm import LLMRouter
from agent.nodes.understand import get_last_human_message

logger = logging.getLogger(__name__)


async def generate_response(state: dict, llm_router: LLMRouter) -> dict[str, Any]:
    """
    GENERATE node: Create the final response with visualization.

    Uses processed data (not raw data) to generate an accurate,
    data-driven response.

    Args:
        state: Current agent state with processed_analysis
        llm_router: LLM router for inference

    Returns:
        Updated state with analysis_result and visualization_spec
    """
    processed = ProcessedAnalysis(**state.get("processed_analysis", {}))
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))
    user_query = get_last_human_message(state)

    # Format data for prompt
    lap_analysis_str = _format_lap_analysis(processed)
    stint_str = _format_stint_summaries(processed)
    comparison_str = _format_comparisons(processed)
    insights_str = "\n".join(f"- {i}" for i in processed.key_insights) or "No key insights computed"

    # Check if we're generating a visualization
    viz_note = ""
    if processed.recommended_viz:
        viz_note = f"\nA {processed.recommended_viz[0].value} visualization will be displayed alongside your response."

    prompt = GENERATE_PROMPT.format(
        user_query=user_query,
        lap_analysis=lap_analysis_str,
        stint_summaries=stint_str,
        comparisons=comparison_str,
        key_insights=insights_str,
        completeness_score=processed.completeness_score,
        missing_data=", ".join(processed.missing_data) or "None",
        visualization_note=viz_note,
    )

    try:
        llm = llm_router.get_llm()
        response = await llm.ainvoke([
            SystemMessage(content=GENERATE_SYSTEM),
            HumanMessage(content=prompt),
        ])

        analysis_result = response.content

        # Generate visualization spec
        viz_spec = None
        if processed.recommended_viz:
            viz_data = {
                "lap_analysis": {
                    d: a.model_dump() for d, a in processed.lap_analysis.items()
                },
                "stint_summaries": {
                    d: [s.model_dump() for s in stints]
                    for d, stints in processed.stint_summaries.items()
                },
                "lap_times": _extract_lap_times_for_viz(state),
            }

            viz_spec = generate_viz_spec(
                viz_type=processed.recommended_viz[0],
                data=viz_data,
                drivers=understanding.drivers,
                title=f"{understanding.query_type.value.title()} Analysis",
            )

        # Update messages
        messages = state.get("messages", [])
        messages.append(AIMessage(content=analysis_result))

        logger.info("Response generated successfully")

        return {
            "analysis_result": analysis_result,
            "visualization_spec": viz_spec.model_dump() if viz_spec else None,
            "messages": messages,
            "response_type": "MIXED" if viz_spec else "TEXT",
        }

    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return {
            "analysis_result": f"I apologize, but I encountered an error generating the analysis: {str(e)}",
            "visualization_spec": None,
            "error": str(e),
        }


def _format_lap_analysis(processed: ProcessedAnalysis) -> str:
    """Format lap analysis for the prompt."""
    if not processed.lap_analysis:
        return "No lap analysis available"

    lines = []
    for driver, analysis in processed.lap_analysis.items():
        lines.append(f"\n### {driver}")
        lines.append(f"- Total laps: {analysis.total_laps}")
        if analysis.fastest_lap:
            lines.append(f"- Fastest lap: {analysis.fastest_lap:.3f}s (Lap {analysis.fastest_lap_number})")
        if analysis.average_pace:
            lines.append(f"- Average pace: {analysis.average_pace:.3f}s")
        if analysis.consistency:
            lines.append(f"- Consistency (std dev): {analysis.consistency:.3f}s")
        if analysis.sector_1_best:
            lines.append(f"- Best sectors: S1={analysis.sector_1_best:.3f}s, S2={analysis.sector_2_best:.3f}s, S3={analysis.sector_3_best:.3f}s")

    return "\n".join(lines)


def _format_stint_summaries(processed: ProcessedAnalysis) -> str:
    """Format stint summaries for the prompt."""
    if not processed.stint_summaries:
        return "No stint data available"

    lines = []
    for driver, stints in processed.stint_summaries.items():
        lines.append(f"\n### {driver}")
        for stint in stints:
            lines.append(
                f"- Stint {stint.stint_number}: {stint.compound} compound, "
                f"Laps {stint.start_lap}-{stint.end_lap} ({stint.total_laps} laps)"
            )
            if stint.average_pace:
                lines.append(f"  Avg pace: {stint.average_pace:.3f}s")
            if stint.degradation_per_lap:
                lines.append(f"  Degradation: {stint.degradation_per_lap:.3f}s/lap")

    return "\n".join(lines)


def _format_comparisons(processed: ProcessedAnalysis) -> str:
    """Format driver comparisons for the prompt."""
    if not processed.comparisons:
        return "No direct comparisons computed"

    lines = []
    for comp in processed.comparisons:
        lines.append(f"\n### {comp.driver_1} vs {comp.driver_2}")
        if comp.pace_delta:
            faster = comp.driver_1 if comp.pace_delta > 0 else comp.driver_2
            lines.append(f"- Average pace delta: {abs(comp.pace_delta):.3f}s ({faster} faster)")
        if comp.fastest_lap_delta:
            faster = comp.driver_1 if comp.fastest_lap_delta > 0 else comp.driver_2
            lines.append(f"- Fastest lap delta: {abs(comp.fastest_lap_delta):.3f}s ({faster} faster)")
        if comp.sector_deltas:
            for sector, delta in comp.sector_deltas.items():
                if delta != 0:
                    faster = comp.driver_1 if delta > 0 else comp.driver_2
                    lines.append(f"- {sector} delta: {abs(delta):.3f}s ({faster} faster)")
        lines.append(f"- Laps compared: {comp.laps_compared}")

    return "\n".join(lines)


def _extract_lap_times_for_viz(state: dict) -> dict[str, list[dict]]:
    """Extract lap times from raw data for visualization."""
    raw_data = state.get("raw_data", {})
    lap_times = {}

    for tool_id, result in raw_data.items():
        if "laps" in tool_id.lower() or "lap_times" in tool_id.lower():
            # Extract driver code from tool_id
            parts = tool_id.split("_")
            driver = None
            for part in parts:
                if len(part) == 3 and part.isupper():
                    driver = part
                    break

            if driver and isinstance(result, list):
                lap_times[driver] = result
            elif driver and isinstance(result, dict) and "data" in result:
                lap_times[driver] = result["data"]

    return lap_times
