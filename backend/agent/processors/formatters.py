"""
Output Formatters for LLM Context Optimization

Converts tool results from verbose dictionaries to compact, LLM-friendly text.
Goal: Reduce token count by 70-90% while preserving information.

Example:
    Input (dict): {"driver": "VER", "lap_time": 74.523, "sector_1": 24.1, ...} × 78 rows
    Output (text): "VER Monaco 2024: 78 laps, avg 74.52s, fastest 73.20s, MEDIUM→HARD"
    Token reduction: ~1500 tokens → ~50 tokens
"""

from typing import Any


def format_head_to_head(results: list[dict]) -> str:
    """
    Format head-to-head comparison for minimal tokens.

    Input: List of race-by-race comparison dicts
    Output: Compact summary text
    """
    if not results or (len(results) == 1 and "error" in results[0]):
        return "No head-to-head data available."

    if len(results) == 0:
        return "No comparison data found for these drivers."

    # Get driver names from first result
    d1 = results[0].get("driver_1", "D1")
    d2 = results[0].get("driver_2", "D2")

    lines = [f"## {d1} vs {d2} Head-to-Head\n"]

    # Summary stats (handle None values)
    pace_deltas = [r.get("pace_delta") for r in results if r.get("pace_delta") is not None]
    d1_faster_count = sum(1 for d in pace_deltas if d > 0)
    d2_faster_count = len(pace_deltas) - d1_faster_count
    avg_pace_delta = sum(pace_deltas) / len(pace_deltas) if pace_deltas else 0

    lines.append(f"Races compared: {len(results)}")
    lines.append(f"Faster on pace: {d1} {d1_faster_count}, {d2} {d2_faster_count}")
    lines.append(f"Avg pace delta: {avg_pace_delta:+.3f}s ({d1} reference)\n")

    # Per-race breakdown (compact)
    lines.append("Race breakdown:")
    for r in results:
        event = r.get("event_name", "Unknown")[:20]
        year = r.get("year", "")
        delta = r.get("pace_delta")
        laps = r.get("comparable_laps", 0)
        if delta is not None:
            winner = d1 if delta > 0 else d2
            lines.append(f"  {year} {event}: {winner} faster by {abs(delta):.3f}s ({laps} laps)")
        else:
            lines.append(f"  {year} {event}: No pace data ({laps} laps)")

    return "\n".join(lines)


def format_driver_season_summary(result: dict) -> str:
    """
    Format season summary for minimal tokens.
    """
    if not result or "error" in result:
        return "No season data available."

    driver = result.get("driver_id", "Unknown")
    year = result.get("year", "")

    lines = [f"## {driver} {year} Season Summary\n"]

    # Key stats
    races = result.get("races_completed", 0)
    wins = result.get("wins", 0)
    podiums = result.get("podiums", 0)
    points = result.get("total_points", 0)
    avg_finish = result.get("avg_finish_position", 0)

    lines.append(f"Races: {races} | Wins: {wins} | Podiums: {podiums}")
    lines.append(f"Points: {points} | Avg finish: {avg_finish:.1f}")

    # Pace stats if available
    if "avg_lap_time" in result:
        lines.append(f"Avg pace: {result['avg_lap_time']:.3f}s")

    if "fastest_laps" in result:
        lines.append(f"Fastest laps: {result['fastest_laps']}")

    return "\n".join(lines)


def format_stint_analysis(results: list[dict]) -> str:
    """
    Format stint analysis for minimal tokens.
    """
    if not results or (len(results) == 1 and "error" in results[0]):
        return "No stint data available."

    lines = ["## Stint Analysis\n"]

    # Group by driver
    drivers = {}
    for r in results:
        driver = r.get("driver_id", "Unknown")
        if driver not in drivers:
            drivers[driver] = []
        drivers[driver].append(r)

    for driver, stints in drivers.items():
        lines.append(f"\n{driver}:")
        for s in sorted(stints, key=lambda x: x.get("stint", 0)):
            stint_num = s.get("stint", 0)
            compound = s.get("compound", "?")[:3].upper()
            laps = s.get("stint_laps", 0)
            avg_pace = s.get("avg_lap_time", 0)
            deg = s.get("degradation_per_lap", 0)
            lines.append(f"  S{stint_num}: {compound} {laps}laps {avg_pace:.2f}s avg, {deg:+.3f}s/lap deg")

    return "\n".join(lines)


def format_lap_times(results: list[dict], driver: str = None) -> str:
    """
    Format lap times into compact summary.
    Never return raw lap-by-lap data to LLM.
    """
    if not results or (len(results) == 1 and "error" in results[0]):
        return "No lap time data available."

    # Aggregate instead of listing
    total_laps = len(results)
    lap_times = [r.get("lap_time_seconds") for r in results if r.get("lap_time_seconds")]

    if not lap_times:
        return f"Found {total_laps} laps but no valid times."

    avg_time = sum(lap_times) / len(lap_times)
    min_time = min(lap_times)
    max_time = max(lap_times)

    # Get compound distribution
    compounds = {}
    for r in results:
        c = r.get("compound", "Unknown")
        compounds[c] = compounds.get(c, 0) + 1

    compound_str = ", ".join(f"{c}:{n}" for c, n in sorted(compounds.items()))

    driver_str = results[0].get("driver_id", driver or "Driver")
    event = results[0].get("event_name", "")

    lines = [
        f"## {driver_str} Lap Times - {event}",
        f"Laps: {total_laps} | Avg: {avg_time:.3f}s | Best: {min_time:.3f}s | Worst: {max_time:.3f}s",
        f"Compounds: {compound_str}",
    ]

    return "\n".join(lines)


def format_race_results(results: list[dict]) -> str:
    """
    Format race results into compact text.
    """
    if not results or (len(results) == 1 and "error" in results[0]):
        return "No race results available."

    # Sort by position
    sorted_results = sorted(results, key=lambda x: x.get("position", 99))

    event = sorted_results[0].get("event_name", "Race") if sorted_results else "Race"
    year = sorted_results[0].get("year", "") if sorted_results else ""

    lines = [f"## {year} {event} Results\n"]

    for r in sorted_results[:10]:  # Top 10 only
        pos = r.get("position", "?")
        driver = r.get("driver_id", "???")
        team = r.get("team_name", "")[:15] if r.get("team_name") else ""
        gap = r.get("gap_to_leader", "")
        status = r.get("status", "")

        if pos == 1:
            lines.append(f"  P{pos}: {driver} ({team}) - Winner")
        elif status and status != "Finished":
            lines.append(f"  P{pos}: {driver} ({team}) - {status}")
        else:
            lines.append(f"  P{pos}: {driver} ({team}) {gap}")

    if len(sorted_results) > 10:
        lines.append(f"  ... and {len(sorted_results) - 10} more")

    return "\n".join(lines)


def format_strategy_simulation(result: dict) -> str:
    """
    Format strategy simulation results.
    """
    if not result or "error" in result:
        return "Strategy simulation failed."

    lines = ["## Strategy Simulation Results\n"]

    if "scenarios" in result:
        for scenario in result["scenarios"]:
            name = scenario.get("name", "Scenario")
            predicted_pos = scenario.get("predicted_position", "?")
            time_delta = scenario.get("time_delta_seconds", 0)

            lines.append(f"{name}: P{predicted_pos} ({time_delta:+.1f}s vs actual)")

            if "stints" in scenario:
                stint_str = " → ".join(
                    f"{s['compound']}({s['laps']})" for s in scenario["stints"]
                )
                lines.append(f"  Strategy: {stint_str}")

    if "recommendation" in result:
        lines.append(f"\nRecommendation: {result['recommendation']}")

    return "\n".join(lines)


def format_similar_scenarios(results: list[dict]) -> str:
    """
    Format historical pattern matching results.
    """
    if not results or (len(results) == 1 and "error" in results[0]):
        return "No similar historical scenarios found."

    lines = ["## Similar Historical Scenarios\n"]

    for i, r in enumerate(results[:5], 1):  # Top 5
        event = r.get("event_name", "Unknown")
        year = r.get("year", "")
        similarity = r.get("similarity_score", 0)
        outcome = r.get("outcome", "")

        lines.append(f"{i}. {year} {event} ({similarity:.0%} similar)")
        if outcome:
            lines.append(f"   Outcome: {outcome}")

    return "\n".join(lines)


def format_regulations_search(results: list[dict]) -> str:
    """
    Format regulation search results.
    """
    if not results:
        return "No relevant regulations found."

    lines = ["## Relevant FIA Regulations\n"]

    for r in results[:3]:  # Top 3 most relevant
        doc_type = r.get("metadata", {}).get("document_type", "regulation")
        article = r.get("metadata", {}).get("article_number", "")
        section = r.get("metadata", {}).get("section", "")
        content = r.get("content", "")[:200]  # Truncate
        score = r.get("score", 0)

        header = f"Art. {article}" if article else section
        lines.append(f"**{doc_type.title()} - {header}** (relevance: {score:.2f})")
        lines.append(f"  {content}...")
        lines.append("")

    return "\n".join(lines)


def format_tool_output(tool_name: str, result: Any) -> str:
    """
    Main dispatcher - formats any tool output for LLM consumption.

    Args:
        tool_name: Name of the tool that produced the result
        result: Raw tool output (dict or list)

    Returns:
        Compact text formatted for minimal LLM tokens
    """
    formatters = {
        "get_head_to_head": format_head_to_head,
        "get_driver_season_summary": format_driver_season_summary,
        "get_stint_analysis": format_stint_analysis,
        "get_lap_times": format_lap_times,
        "get_race_results": format_race_results,
        "simulate_strategy": format_strategy_simulation,
        "find_similar_scenarios": format_similar_scenarios,
        "search_regulations": format_regulations_search,
        "search_race_reports": format_regulations_search,  # Same format
    }

    formatter = formatters.get(tool_name)

    if formatter:
        try:
            return formatter(result)
        except Exception as e:
            return f"Error formatting {tool_name} output: {e}\nRaw: {str(result)[:200]}"

    # Default: return truncated JSON-like representation
    if isinstance(result, list):
        return f"Tool returned {len(result)} items. First: {str(result[0])[:200] if result else 'empty'}"
    elif isinstance(result, dict):
        return f"Tool returned: {str(result)[:300]}"
    else:
        return str(result)[:500]


# Token estimation helper
def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for English text."""
    return len(text) // 4
