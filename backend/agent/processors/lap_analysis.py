"""Lap time processing and statistics."""

import statistics
from typing import Any

from agent.schemas.analysis import LapAnalysis


def process_lap_times(raw_data: list[dict]) -> list[dict]:
    """
    Clean and normalize lap time data.

    Args:
        raw_data: Raw lap time records from database

    Returns:
        Cleaned lap records with consistent fields
    """
    processed = []
    for record in raw_data:
        if record.get("error"):
            continue

        lap = {
            "lap_number": record.get("lap_number"),
            "lap_time": record.get("lap_time_seconds") or record.get("lap_time"),
            "sector_1": record.get("sector_1_seconds") or record.get("sector_1"),
            "sector_2": record.get("sector_2_seconds") or record.get("sector_2"),
            "sector_3": record.get("sector_3_seconds") or record.get("sector_3"),
            "compound": record.get("compound", "UNKNOWN"),
            "tire_life": record.get("tire_life", 0),
            "position": record.get("position"),
            "stint": record.get("stint", 1),
            "is_pit_lap": record.get("is_pit_lap", False),
        }

        # Filter out invalid laps (pit laps, outliers)
        if lap["lap_time"] and lap["lap_time"] > 60:  # Reasonable F1 lap time
            processed.append(lap)

    return processed


def calculate_lap_statistics(laps: list[dict], driver: str) -> LapAnalysis:
    """
    Calculate aggregate statistics from lap data.

    Args:
        laps: Processed lap records
        driver: Driver code

    Returns:
        LapAnalysis with computed statistics
    """
    if not laps:
        return LapAnalysis(driver=driver, total_laps=0)

    lap_times = [lap["lap_time"] for lap in laps if lap["lap_time"]]

    # Find fastest lap
    fastest_lap = min(lap_times) if lap_times else None
    fastest_lap_idx = lap_times.index(fastest_lap) if fastest_lap else None
    fastest_lap_number = laps[fastest_lap_idx]["lap_number"] if fastest_lap_idx is not None else None

    # Calculate average (excluding slowest 10% for outliers like safety car)
    sorted_times = sorted(lap_times)
    clean_times = sorted_times[:int(len(sorted_times) * 0.9)] if len(sorted_times) > 10 else sorted_times
    average_pace = statistics.mean(clean_times) if clean_times else None

    # Calculate consistency (std deviation)
    consistency = statistics.stdev(clean_times) if len(clean_times) > 1 else None

    # Best sectors
    sector_1_times = [lap["sector_1"] for lap in laps if lap["sector_1"]]
    sector_2_times = [lap["sector_2"] for lap in laps if lap["sector_2"]]
    sector_3_times = [lap["sector_3"] for lap in laps if lap["sector_3"]]

    return LapAnalysis(
        driver=driver,
        total_laps=len(laps),
        fastest_lap=fastest_lap,
        fastest_lap_number=fastest_lap_number,
        average_pace=average_pace,
        consistency=consistency,
        sector_1_best=min(sector_1_times) if sector_1_times else None,
        sector_2_best=min(sector_2_times) if sector_2_times else None,
        sector_3_best=min(sector_3_times) if sector_3_times else None,
    )


def aggregate_by_stint(laps: list[dict]) -> dict[int, list[dict]]:
    """Group laps by stint number."""
    stints: dict[int, list[dict]] = {}
    for lap in laps:
        stint = lap.get("stint", 1)
        if stint not in stints:
            stints[stint] = []
        stints[stint].append(lap)
    return stints


def calculate_degradation(stint_laps: list[dict]) -> float | None:
    """
    Calculate tire degradation rate (seconds lost per lap).

    Uses linear regression on lap times to estimate degradation.
    """
    if len(stint_laps) < 5:
        return None

    lap_times = [lap["lap_time"] for lap in stint_laps if lap["lap_time"]]
    if len(lap_times) < 5:
        return None

    # Simple linear regression: y = mx + b, we want m (slope)
    n = len(lap_times)
    x = list(range(n))

    x_mean = sum(x) / n
    y_mean = sum(lap_times) / n

    numerator = sum((x[i] - x_mean) * (lap_times[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return None

    slope = numerator / denominator
    return round(slope, 3) if slope > 0 else None  # Only positive degradation makes sense
