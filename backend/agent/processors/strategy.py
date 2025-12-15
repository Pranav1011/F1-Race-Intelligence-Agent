"""Strategy and stint processing."""

import statistics
from typing import Any

from agent.schemas.analysis import StintSummary
from agent.processors.lap_analysis import calculate_degradation


def process_stint_data(laps: list[dict], driver: str) -> list[StintSummary]:
    """
    Process lap data into stint summaries.

    Args:
        laps: List of lap records with stint info
        driver: Driver code

    Returns:
        List of StintSummary objects
    """
    if not laps:
        return []

    # Group by stint
    stints: dict[int, list[dict]] = {}
    for lap in laps:
        stint_num = lap.get("stint", 1)
        if stint_num not in stints:
            stints[stint_num] = []
        stints[stint_num].append(lap)

    summaries = []
    for stint_num in sorted(stints.keys()):
        stint_laps = stints[stint_num]
        if not stint_laps:
            continue

        # Get compound (should be same for whole stint)
        compound = stint_laps[0].get("compound", "UNKNOWN")

        # Calculate lap range
        lap_numbers = [lap["lap_number"] for lap in stint_laps if lap.get("lap_number")]
        start_lap = min(lap_numbers) if lap_numbers else 0
        end_lap = max(lap_numbers) if lap_numbers else 0

        # Calculate average pace
        lap_times = [lap["lap_time"] for lap in stint_laps if lap.get("lap_time")]
        avg_pace = statistics.mean(lap_times) if lap_times else None

        # Calculate degradation
        degradation = calculate_degradation(stint_laps)

        # Find pit lap (last lap of stint, if not the final stint)
        pit_lap = end_lap if stint_num < max(stints.keys()) else None

        summaries.append(StintSummary(
            stint_number=stint_num,
            compound=compound,
            start_lap=start_lap,
            end_lap=end_lap,
            total_laps=len(stint_laps),
            average_pace=round(avg_pace, 3) if avg_pace else None,
            degradation_per_lap=degradation,
            pit_in_lap=pit_lap,
        ))

    return summaries


def analyze_strategy(
    driver_stints: dict[str, list[StintSummary]]
) -> dict[str, Any]:
    """
    Analyze and compare strategies across drivers.

    Args:
        driver_stints: Dict mapping driver code to stint summaries

    Returns:
        Strategy analysis dict
    """
    analysis = {
        "drivers": {},
        "insights": [],
    }

    for driver, stints in driver_stints.items():
        if not stints:
            continue

        total_stops = len(stints) - 1
        compounds_used = [s.compound for s in stints]

        # Find longest stint
        longest_stint = max(stints, key=lambda s: s.total_laps)

        analysis["drivers"][driver] = {
            "total_stops": total_stops,
            "compounds_used": compounds_used,
            "strategy_type": _classify_strategy(compounds_used),
            "longest_stint": longest_stint.total_laps,
            "longest_stint_compound": longest_stint.compound,
        }

    # Generate strategy insights
    if len(driver_stints) >= 2:
        drivers = list(driver_stints.keys())
        d1, d2 = drivers[0], drivers[1]

        if analysis["drivers"].get(d1) and analysis["drivers"].get(d2):
            d1_stops = analysis["drivers"][d1]["total_stops"]
            d2_stops = analysis["drivers"][d2]["total_stops"]

            if d1_stops != d2_stops:
                more_stops = d1 if d1_stops > d2_stops else d2
                analysis["insights"].append(
                    f"{more_stops} used a more aggressive strategy with {max(d1_stops, d2_stops)} stops"
                )

    return analysis


def _classify_strategy(compounds: list[str]) -> str:
    """Classify strategy based on compounds used."""
    compounds_upper = [c.upper() for c in compounds]

    if len(compounds_upper) == 2:
        if "SOFT" in compounds_upper and "MEDIUM" in compounds_upper:
            return "aggressive_one_stop"
        elif "MEDIUM" in compounds_upper and "HARD" in compounds_upper:
            return "conservative_one_stop"
    elif len(compounds_upper) == 3:
        return "two_stop"
    elif len(compounds_upper) >= 4:
        return "multi_stop"

    return "standard"
