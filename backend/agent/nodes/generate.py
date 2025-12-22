"""GENERATE node - Generate response with visualization."""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.schemas.query import QueryUnderstanding
from agent.schemas.analysis import ProcessedAnalysis
from agent.prompts.generate import GENERATE_SYSTEM, GENERATE_PROMPT
from agent.processors.visualization import generate_viz_spec
from agent.llm import LLMRouter
from agent.nodes.understand import get_last_human_message

logger = logging.getLogger(__name__)

# Observability imports (optional - graceful degradation)
try:
    from observability.sentry_integration import add_breadcrumb, capture_exception
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


async def generate_response(state: dict, llm_router: LLMRouter) -> dict[str, Any]:
    """
    GENERATE node: Create the final response with visualization.

    Uses processed data AND enriched RAG context to generate an accurate,
    data-driven response with historical/community context.

    Args:
        state: Current agent state with processed_analysis and enriched_context
        llm_router: LLM router for inference

    Returns:
        Updated state with analysis_result and visualization_spec
    """
    processed = ProcessedAnalysis(**state.get("processed_analysis", {}))
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))
    enriched_context = state.get("enriched_context", {})
    user_query = get_last_human_message(state)

    # Add breadcrumb for observability
    if SENTRY_AVAILABLE:
        add_breadcrumb(
            message=f"GENERATE node creating response for {understanding.query_type}",
            category="agent",
            level="info",
            data={
                "query_type": understanding.query_type.value if hasattr(understanding.query_type, "value") else str(understanding.query_type),
                "completeness_score": processed.completeness_score,
                "has_viz": bool(processed.recommended_viz),
                "has_enriched_context": bool(enriched_context),
            },
        )

    # Format data for prompt
    lap_analysis_str = _format_lap_analysis(processed)
    stint_str = _format_stint_summaries(processed)
    comparison_str = _format_comparisons(processed)
    insights_str = "\n".join(f"- {i}" for i in processed.key_insights) or "No key insights computed"

    # Format RAW tool results - this is critical for data-driven responses
    raw_tool_results_str = _format_raw_tool_results(state.get("raw_data", {}))

    # Format enriched context
    race_context_str = _format_race_context(enriched_context.get("race_context", []))
    community_str = _format_community_insights(enriched_context.get("community_insights", []))
    regulations_str = _format_regulations(enriched_context.get("regulations", []))

    # Check if we're generating a visualization
    viz_note = ""
    if processed.recommended_viz:
        viz_note = f"\nA {processed.recommended_viz[0].value} visualization will be displayed alongside your response."

    prompt = GENERATE_PROMPT.format(
        user_query=user_query,
        raw_tool_results=raw_tool_results_str,
        lap_analysis=lap_analysis_str,
        stint_summaries=stint_str,
        comparisons=comparison_str,
        key_insights=insights_str,
        completeness_score=processed.completeness_score,
        missing_data=", ".join(processed.missing_data) or "None",
        visualization_note=viz_note,
        race_context=race_context_str,
        community_insights=community_str,
        regulations=regulations_str,
    )

    try:
        # Use router's ainvoke for automatic fallback on rate limits
        response = await llm_router.ainvoke([
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
        if SENTRY_AVAILABLE:
            capture_exception(
                e,
                extra={"node": "generate", "query_type": str(understanding.query_type)},
                tags={"agent_node": "generate"},
            )
        return {
            "analysis_result": f"I apologize, but I encountered an error generating the analysis: {str(e)}",
            "visualization_spec": None,
            "error": str(e),
        }


def _format_raw_tool_results(raw_data: dict) -> str:
    """
    Format raw tool results for the prompt.
    This passes the ACTUAL DATA to the LLM for data-driven responses.
    """
    if not raw_data:
        return "No raw tool data available"

    import json

    lines = []
    for tool_id, result in raw_data.items():
        # Skip empty results or errors
        if not result:
            continue
        if isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            if isinstance(first_item, dict) and "error" in first_item:
                lines.append(f"### {tool_id}\nError: {first_item.get('error')}")
                continue

        # Format the tool result
        lines.append(f"### {tool_id}")

        if isinstance(result, list):
            # For lists (like pit stops, lap times), show first 20 items
            if len(result) > 0:
                # Check if it's a simple list of dicts - format as table
                if isinstance(result[0], dict):
                    # Show first 20 results
                    display_results = result[:20]
                    lines.append(f"(Showing {len(display_results)} of {len(result)} results)")
                    lines.append("```json")
                    lines.append(json.dumps(display_results, indent=2, default=str))
                    lines.append("```")
                else:
                    lines.append(str(result[:20]))
        elif isinstance(result, dict):
            lines.append("```json")
            lines.append(json.dumps(result, indent=2, default=str))
            lines.append("```")
        else:
            lines.append(str(result))

        lines.append("")  # Empty line between tools

    return "\n".join(lines) if lines else "No raw tool data available"


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


def _format_race_context(race_context: list[dict]) -> str:
    """Format race context from RAG for the prompt."""
    if not race_context:
        return "No race context available"

    lines = []
    for ctx in race_context:
        source = ctx.get("source", "race report")
        content = ctx.get("content", "")
        if content:
            lines.append(f"**{source}**: {content}")

    return "\n\n".join(lines) if lines else "No race context available"


def _format_community_insights(community_insights: list[dict]) -> str:
    """Format community insights from Reddit for the prompt."""
    if not community_insights:
        return "No community insights available"

    lines = []
    for insight in community_insights:
        content = insight.get("content", "")
        score = insight.get("score", 0)
        if content:
            lines.append(f"- {content} (score: {score})")

    return "\n".join(lines) if lines else "No community insights available"


def _format_regulations(regulations: list[dict]) -> str:
    """Format regulations for the prompt."""
    if not regulations:
        return "No relevant regulations found"

    lines = []
    for reg in regulations:
        article = reg.get("article", "")
        content = reg.get("content", "")
        if content:
            prefix = f"**{article}**: " if article else ""
            lines.append(f"{prefix}{content}")

    return "\n\n".join(lines) if lines else "No relevant regulations found"


def _format_similar_analyses(similar_analyses: list[dict]) -> str:
    """Format similar past analyses for the prompt."""
    if not similar_analyses:
        return "No similar past analyses found"

    lines = []
    for analysis in similar_analyses:
        query = analysis.get("query", "")
        preview = analysis.get("analysis_preview", "")
        if preview:
            lines.append(f"**Query**: {query}\n{preview}")

    return "\n\n".join(lines) if lines else "No similar past analyses found"


def _extract_lap_times_for_viz(state: dict) -> dict[str, list[dict]]:
    """Extract lap times from raw data for visualization."""
    raw_data = state.get("raw_data", {})
    lap_times = {}

    for tool_id, result in raw_data.items():
        tool_lower = tool_id.lower()

        # Handle standard lap times data
        if "laps" in tool_lower or "lap_times" in tool_lower:
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

        # Handle head-to-head comparison data
        elif "head_to_head" in tool_lower or "h2h" in tool_lower or "compare" in tool_lower:
            if isinstance(result, list) and len(result) > 0:
                # Head-to-head data contains lap-by-lap comparisons
                # Extract and structure for visualization
                for h2h in result:
                    if not isinstance(h2h, dict):
                        continue

                    driver_1 = h2h.get("driver_1", "")
                    driver_2 = h2h.get("driver_2", "")

                    # Check if we have lap-by-lap data in the h2h result
                    lap_data = h2h.get("lap_data", [])
                    if lap_data:
                        # Structure lap data per driver
                        if driver_1 and driver_1 not in lap_times:
                            lap_times[driver_1] = []
                        if driver_2 and driver_2 not in lap_times:
                            lap_times[driver_2] = []

                        for lap in lap_data:
                            lap_num = lap.get("lap_number", lap.get("lap", 0))
                            if driver_1:
                                lap_times[driver_1].append({
                                    "lap_number": lap_num,
                                    "lap_time": lap.get(f"{driver_1}_time") or lap.get("driver_1_time"),
                                    "lap_time_seconds": lap.get(f"{driver_1}_time") or lap.get("driver_1_time"),
                                })
                            if driver_2:
                                lap_times[driver_2].append({
                                    "lap_number": lap_num,
                                    "lap_time": lap.get(f"{driver_2}_time") or lap.get("driver_2_time"),
                                    "lap_time_seconds": lap.get(f"{driver_2}_time") or lap.get("driver_2_time"),
                                })

    return lap_times
