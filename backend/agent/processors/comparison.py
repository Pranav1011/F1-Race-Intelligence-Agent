"""Driver comparison processing."""

from agent.schemas.analysis import DriverComparison, LapAnalysis


def compute_driver_comparison(
    driver_1_analysis: LapAnalysis,
    driver_2_analysis: LapAnalysis,
) -> DriverComparison:
    """
    Compute head-to-head comparison between two drivers.

    Args:
        driver_1_analysis: First driver's lap analysis
        driver_2_analysis: Second driver's lap analysis

    Returns:
        DriverComparison with deltas
    """
    # Pace delta (positive = driver_1 faster)
    pace_delta = None
    if driver_1_analysis.average_pace and driver_2_analysis.average_pace:
        pace_delta = round(driver_2_analysis.average_pace - driver_1_analysis.average_pace, 3)

    # Fastest lap delta
    fastest_delta = None
    if driver_1_analysis.fastest_lap and driver_2_analysis.fastest_lap:
        fastest_delta = round(driver_2_analysis.fastest_lap - driver_1_analysis.fastest_lap, 3)

    # Sector deltas
    sector_deltas = {}
    if driver_1_analysis.sector_1_best and driver_2_analysis.sector_1_best:
        sector_deltas["S1"] = round(driver_2_analysis.sector_1_best - driver_1_analysis.sector_1_best, 3)
    if driver_1_analysis.sector_2_best and driver_2_analysis.sector_2_best:
        sector_deltas["S2"] = round(driver_2_analysis.sector_2_best - driver_1_analysis.sector_2_best, 3)
    if driver_1_analysis.sector_3_best and driver_2_analysis.sector_3_best:
        sector_deltas["S3"] = round(driver_2_analysis.sector_3_best - driver_1_analysis.sector_3_best, 3)

    return DriverComparison(
        driver_1=driver_1_analysis.driver,
        driver_2=driver_2_analysis.driver,
        driver_1_avg_pace=driver_1_analysis.average_pace,
        driver_2_avg_pace=driver_2_analysis.average_pace,
        pace_delta=pace_delta,
        driver_1_fastest=driver_1_analysis.fastest_lap,
        driver_2_fastest=driver_2_analysis.fastest_lap,
        fastest_lap_delta=fastest_delta,
        sector_deltas=sector_deltas,
        laps_compared=min(driver_1_analysis.total_laps, driver_2_analysis.total_laps),
    )


def extract_comparison_insights(comparison: DriverComparison) -> list[str]:
    """
    Extract key insights from a driver comparison.

    Args:
        comparison: DriverComparison object

    Returns:
        List of insight strings
    """
    insights = []

    # Overall pace
    if comparison.pace_delta is not None:
        faster = comparison.driver_1 if comparison.pace_delta > 0 else comparison.driver_2
        delta = abs(comparison.pace_delta)
        insights.append(
            f"{faster} was {delta:.3f}s faster on average pace over {comparison.laps_compared} laps"
        )

    # Fastest lap
    if comparison.fastest_lap_delta is not None:
        faster = comparison.driver_1 if comparison.fastest_lap_delta > 0 else comparison.driver_2
        delta = abs(comparison.fastest_lap_delta)
        insights.append(f"{faster} set the faster lap by {delta:.3f}s")

    # Sector analysis
    if comparison.sector_deltas:
        for sector, delta in comparison.sector_deltas.items():
            if delta != 0:
                faster = comparison.driver_1 if delta > 0 else comparison.driver_2
                insights.append(f"{faster} was {abs(delta):.3f}s faster in {sector}")

    # Consistency comparison (if we had std dev data)
    # TODO: Add consistency insight when data available

    return insights


def compute_multi_driver_comparison(
    analyses: dict[str, LapAnalysis]
) -> list[DriverComparison]:
    """
    Compute pairwise comparisons for multiple drivers.

    Args:
        analyses: Dict mapping driver code to LapAnalysis

    Returns:
        List of all pairwise comparisons
    """
    comparisons = []
    drivers = list(analyses.keys())

    for i, driver_1 in enumerate(drivers):
        for driver_2 in drivers[i + 1:]:
            comparison = compute_driver_comparison(
                analyses[driver_1],
                analyses[driver_2]
            )
            comparisons.append(comparison)

    return comparisons
