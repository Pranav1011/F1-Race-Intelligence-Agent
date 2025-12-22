"""Visualization specification generation."""

import uuid
from typing import Any

from agent.schemas.analysis import (
    ChartType,
    VisualizationSpec,
    LapAnalysis,
    StintSummary,
    DriverComparison,
)
from agent.schemas.query import AnalysisType


# F1 team colors for driver visualization
DRIVER_COLORS = {
    "VER": "#3671C6",  # Red Bull
    "PER": "#3671C6",
    "HAM": "#6CD3BF",  # Mercedes
    "RUS": "#6CD3BF",
    "LEC": "#F91536",  # Ferrari
    "SAI": "#F91536",
    "NOR": "#F58020",  # McLaren
    "PIA": "#F58020",
    "ALO": "#229971",  # Aston Martin
    "STR": "#229971",
    "GAS": "#0093CC",  # Alpine
    "OCO": "#0093CC",
    "ALB": "#64C4FF",  # Williams
    "SAR": "#64C4FF",
    "BOT": "#C92D4B",  # Alfa Romeo / Kick
    "ZHO": "#C92D4B",
    "MAG": "#B6BABD",  # Haas
    "HUL": "#B6BABD",
    "TSU": "#6692FF",  # RB / AlphaTauri
    "RIC": "#6692FF",
    "LAW": "#6692FF",
}

COMPOUND_COLORS = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFD700",
    "HARD": "#EEEEEE",
    "INTERMEDIATE": "#43B02A",
    "WET": "#0067AD",
}


def select_viz_type(
    analysis_type: AnalysisType,
    metrics: list[str],
    num_drivers: int = 0,
    has_lap_data: bool = False,
) -> list[ChartType]:
    """
    Select appropriate visualization types based on query and data characteristics.

    Args:
        analysis_type: Type of analysis being performed
        metrics: Metrics being analyzed
        num_drivers: Number of drivers in the analysis
        has_lap_data: Whether we have lap-by-lap data

    Returns:
        List of recommended chart types
    """
    charts = []

    # Check for specific metric keywords
    metrics_lower = [m.lower() for m in metrics]
    wants_consistency = any(
        word in m for m in metrics_lower
        for word in ["consistency", "consistent", "variation", "spread"]
    )
    wants_distribution = any(
        word in m for m in metrics_lower
        for word in ["distribution", "histogram", "frequency"]
    )
    wants_comparison = any(
        word in m for m in metrics_lower
        for word in ["compare", "vs", "versus", "difference", "delta"]
    )

    if analysis_type == AnalysisType.COMPARISON:
        if num_drivers == 2 and has_lap_data:
            # Head-to-head: show lap comparison line + delta chart
            charts = [ChartType.LAP_COMPARISON, ChartType.DELTA_LINE, ChartType.BOX_PLOT]
        elif num_drivers == 2:
            # Summary comparison without lap data
            charts = [ChartType.BAR_CHART, ChartType.BOX_PLOT]
        else:
            # Multiple drivers
            charts = [ChartType.BAR_CHART, ChartType.BOX_PLOT]

        if wants_consistency:
            charts = [ChartType.BOX_PLOT, ChartType.VIOLIN_PLOT] + charts

    elif analysis_type == AnalysisType.PACE:
        if has_lap_data:
            charts = [ChartType.LAP_PROGRESSION, ChartType.BOX_PLOT]
            if num_drivers >= 2:
                charts.append(ChartType.DELTA_LINE)
        else:
            charts = [ChartType.BAR_CHART]

        if wants_distribution:
            charts = [ChartType.HISTOGRAM] + charts
        if wants_consistency:
            charts = [ChartType.BOX_PLOT] + charts

    elif analysis_type == AnalysisType.STRATEGY:
        charts = [ChartType.TIRE_STRATEGY]
        if has_lap_data:
            charts.append(ChartType.SCATTER)  # Tire degradation scatter

    elif analysis_type == AnalysisType.TELEMETRY:
        charts = [ChartType.SPEED_TRACE, ChartType.LAP_PROGRESSION]

    elif analysis_type == AnalysisType.RESULTS:
        charts = [ChartType.POSITION_BATTLE, ChartType.TABLE]
        if has_lap_data:
            charts.insert(0, ChartType.RACE_PROGRESS)

    else:
        charts = [ChartType.TABLE]

    # Remove duplicates while preserving order
    seen = set()
    unique_charts = []
    for c in charts:
        if c not in seen:
            seen.add(c)
            unique_charts.append(c)

    return unique_charts[:3]  # Return top 3 recommended


def generate_viz_spec(
    viz_type: ChartType,
    data: dict[str, Any],
    drivers: list[str],
    title: str = "",
) -> VisualizationSpec | None:
    """
    Generate a visualization specification for the frontend.

    Args:
        viz_type: Type of chart to generate
        data: Processed data dict
        drivers: List of driver codes
        title: Chart title

    Returns:
        VisualizationSpec or None if insufficient data
    """
    generators = {
        ChartType.LAP_PROGRESSION: _generate_lap_progression,
        ChartType.SECTOR_COMPARISON: _generate_sector_comparison,
        ChartType.TIRE_STRATEGY: _generate_tire_strategy,
        ChartType.GAP_EVOLUTION: _generate_gap_evolution,
        ChartType.BAR_CHART: _generate_bar_chart,
        ChartType.TABLE: _generate_table,
        ChartType.RACE_PROGRESS: _generate_race_progress,
        ChartType.LAP_COMPARISON: _generate_lap_comparison,
        # New chart types
        ChartType.DELTA_LINE: _generate_delta_line,
        ChartType.BOX_PLOT: _generate_box_plot,
        ChartType.HISTOGRAM: _generate_histogram,
        ChartType.VIOLIN_PLOT: _generate_violin_plot,
        ChartType.SCATTER: _generate_scatter,
    }

    generator = generators.get(viz_type)
    if not generator:
        return None

    return generator(data, drivers, title)


def _generate_lap_progression(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate lap time progression line chart."""
    lap_data = data.get("lap_times", {})
    if not lap_data:
        return None

    # Format data for Recharts
    chart_data = []
    max_laps = 0

    for driver, laps in lap_data.items():
        if driver not in drivers:
            continue
        max_laps = max(max_laps, len(laps))

    for lap_num in range(1, max_laps + 1):
        point = {"lap": lap_num}
        for driver in drivers:
            driver_laps = lap_data.get(driver, [])
            lap_record = next(
                (l for l in driver_laps if l.get("lap_number") == lap_num),
                None
            )
            if lap_record:
                # Handle both 'lap_time' and 'lap_time_seconds' field names
                lap_time = lap_record.get("lap_time") or lap_record.get("lap_time_seconds")
                if lap_time:
                    point[driver] = round(lap_time, 3)
        chart_data.append(point)

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.LAP_PROGRESSION,
        title=title or "Lap Time Progression",
        data=chart_data,
        config={
            "xAxis": "lap",
            "yAxis": drivers,
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
        },
        drivers=drivers,
    )


def _generate_sector_comparison(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate sector comparison grouped bar chart."""
    lap_analysis = data.get("lap_analysis", {})
    if not lap_analysis:
        return None

    chart_data = []
    for sector in ["S1", "S2", "S3"]:
        point = {"sector": sector}
        for driver in drivers:
            analysis = lap_analysis.get(driver)
            if analysis:
                sector_key = f"sector_{sector[-1]}_best"
                if hasattr(analysis, sector_key):
                    point[driver] = getattr(analysis, sector_key)
        chart_data.append(point)

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.SECTOR_COMPARISON,
        title=title or "Best Sector Times Comparison",
        data=chart_data,
        config={
            "xAxis": "sector",
            "yAxis": drivers,
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
        },
        drivers=drivers,
    )


def _generate_tire_strategy(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate tire strategy Gantt-style chart."""
    stint_data = data.get("stint_summaries", {})
    if not stint_data:
        return None

    chart_data = []
    for driver in drivers:
        stints = stint_data.get(driver, [])
        for stint in stints:
            if isinstance(stint, StintSummary):
                chart_data.append({
                    "driver": driver,
                    "stint": stint.stint_number,
                    "compound": stint.compound,
                    "start_lap": stint.start_lap,
                    "end_lap": stint.end_lap,
                    "total_laps": stint.total_laps,
                    "avg_pace": stint.average_pace,
                    "color": COMPOUND_COLORS.get(stint.compound.upper(), "#888888"),
                })
            elif isinstance(stint, dict):
                chart_data.append({
                    "driver": driver,
                    "stint": stint.get("stint_number", 1),
                    "compound": stint.get("compound", "UNKNOWN"),
                    "start_lap": stint.get("start_lap", 0),
                    "end_lap": stint.get("end_lap", 0),
                    "total_laps": stint.get("total_laps", 0),
                    "avg_pace": stint.get("average_pace"),
                    "color": COMPOUND_COLORS.get(stint.get("compound", "").upper(), "#888888"),
                })

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.TIRE_STRATEGY,
        title=title or "Tire Strategy Timeline",
        data=chart_data,
        config={
            "compoundColors": COMPOUND_COLORS,
        },
        drivers=drivers,
    )


def _generate_gap_evolution(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate gap to leader evolution chart."""
    # TODO: Implement when gap data available
    return None


def _generate_bar_chart(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate generic bar chart."""
    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.BAR_CHART,
        title=title or "Comparison",
        data=[],
        config={},
        drivers=drivers,
    )


def _generate_table(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate data table visualization."""
    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.TABLE,
        title=title or "Data Table",
        data=[],
        config={},
        drivers=drivers,
    )


def _generate_race_progress(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate animated race progress visualization with car icons."""
    lap_data = data.get("lap_times", {})
    if not lap_data:
        return None

    # Format data for RaceProgressChart component
    # Structure: list of {lap, driver1_position, driver2_position, ...}
    chart_data = []
    max_laps = 0

    for driver, laps in lap_data.items():
        if driver not in drivers:
            continue
        max_laps = max(max_laps, len(laps))

    for lap_num in range(1, max_laps + 1):
        point = {"lap": lap_num}
        for driver in drivers:
            driver_laps = lap_data.get(driver, [])
            lap_record = next(
                (l for l in driver_laps if l.get("lap_number") == lap_num),
                None
            )
            if lap_record:
                point[f"{driver}_position"] = lap_record.get("position", 0)
                point[f"{driver}_time"] = lap_record.get("lap_time_seconds") or lap_record.get("lap_time")
                point[f"{driver}_compound"] = lap_record.get("compound", "MEDIUM")
                point[f"{driver}_pit"] = lap_record.get("stint", 1) != lap_record.get("prev_stint", 1) if "prev_stint" in lap_record else False
        chart_data.append(point)

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.RACE_PROGRESS,
        title=title or "Race Progress",
        data=chart_data,
        config={
            "totalLaps": max_laps,
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
            "compoundColors": COMPOUND_COLORS,
        },
        drivers=drivers,
    )


def _generate_lap_comparison(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate head-to-head lap time comparison visualization."""
    lap_data = data.get("lap_times", {})
    lap_analysis = data.get("lap_analysis", {})

    if not lap_data and not lap_analysis:
        return None

    # Format data for LapTimeComparison component
    # Structure: list of {lap, driver1, driver2, driver1_compound, driver2_compound}
    chart_data = []
    max_laps = 0

    for driver, laps in lap_data.items():
        if driver not in drivers:
            continue
        max_laps = max(max_laps, len(laps))

    # If we have lap-by-lap data, use it for line chart
    if max_laps > 0:
        for lap_num in range(1, max_laps + 1):
            point = {"lap": lap_num}
            for driver in drivers:
                driver_laps = lap_data.get(driver, [])
                lap_record = next(
                    (l for l in driver_laps if l.get("lap_number") == lap_num),
                    None
                )
                if lap_record:
                    lap_time = lap_record.get("lap_time") or lap_record.get("lap_time_seconds")
                    if lap_time:
                        point[driver] = round(lap_time, 3)
                    point[f"{driver}_compound"] = lap_record.get("compound", "MEDIUM")
                    point[f"{driver}_sector1"] = lap_record.get("sector_1_seconds")
                    point[f"{driver}_sector2"] = lap_record.get("sector_2_seconds")
                    point[f"{driver}_sector3"] = lap_record.get("sector_3_seconds")
            chart_data.append(point)
    elif lap_analysis:
        # Fallback: Create comparison bar data from lap_analysis
        # This creates a summary comparison when we don't have lap-by-lap data
        for metric in ["Average Pace", "Fastest Lap"]:
            point = {"metric": metric}
            for driver in drivers:
                analysis = lap_analysis.get(driver)
                if analysis:
                    if isinstance(analysis, dict):
                        if metric == "Average Pace":
                            point[driver] = analysis.get("average_pace")
                        elif metric == "Fastest Lap":
                            point[driver] = analysis.get("fastest_lap")
                    elif hasattr(analysis, "average_pace"):
                        if metric == "Average Pace":
                            point[driver] = analysis.average_pace
                        elif metric == "Fastest Lap":
                            point[driver] = analysis.fastest_lap
            chart_data.append(point)

    # Extract driver stats from lap_analysis
    driver_stats = {}
    for driver in drivers:
        analysis = lap_analysis.get(driver)
        if analysis:
            if hasattr(analysis, "model_dump"):
                driver_stats[driver] = analysis.model_dump()
            elif isinstance(analysis, dict):
                driver_stats[driver] = analysis

    # Use BAR_CHART type for summary comparison, LAP_COMPARISON for detailed
    chart_type = ChartType.LAP_COMPARISON if max_laps > 0 else ChartType.BAR_CHART

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=chart_type,
        title=title or "Lap Time Comparison",
        data=chart_data,
        config={
            "xAxis": "lap" if max_laps > 0 else "metric",
            "yAxis": drivers,
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
            "compoundColors": COMPOUND_COLORS,
            "driverStats": driver_stats,
        },
        drivers=drivers,
    )


def _generate_delta_line(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate lap-by-lap time delta chart between drivers."""
    lap_data = data.get("lap_times", {})
    if not lap_data or len(drivers) < 2:
        return None

    # Get lap times for first two drivers
    driver_1, driver_2 = drivers[0], drivers[1]
    laps_1 = {l.get("lap_number"): l for l in lap_data.get(driver_1, [])}
    laps_2 = {l.get("lap_number"): l for l in lap_data.get(driver_2, [])}

    if not laps_1 or not laps_2:
        return None

    # Calculate lap-by-lap delta
    chart_data = []
    cumulative_delta = 0.0
    all_laps = sorted(set(laps_1.keys()) & set(laps_2.keys()))

    for lap_num in all_laps:
        lap_1 = laps_1.get(lap_num, {})
        lap_2 = laps_2.get(lap_num, {})

        time_1 = lap_1.get("lap_time") or lap_1.get("lap_time_seconds")
        time_2 = lap_2.get("lap_time") or lap_2.get("lap_time_seconds")

        if time_1 and time_2:
            lap_delta = time_2 - time_1  # Positive = driver_1 faster
            cumulative_delta += lap_delta

            chart_data.append({
                "lap": lap_num,
                "lap_delta": round(lap_delta, 3),
                "cumulative_delta": round(cumulative_delta, 3),
                "faster": driver_1 if lap_delta > 0 else driver_2,
            })

    if not chart_data:
        return None

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.DELTA_LINE,
        title=title or f"Gap Evolution: {driver_1} vs {driver_2}",
        data=chart_data,
        config={
            "xAxis": "lap",
            "yAxis": ["lap_delta", "cumulative_delta"],
            "colors": {
                driver_1: DRIVER_COLORS.get(driver_1, "#E31937"),
                driver_2: DRIVER_COLORS.get(driver_2, "#3671C6"),
            },
            "referenceDriver": driver_1,
            "comparisonDriver": driver_2,
        },
        drivers=[driver_1, driver_2],
    )


def _generate_box_plot(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate box plot for lap time distribution/consistency."""
    lap_data = data.get("lap_times", {})
    lap_analysis = data.get("lap_analysis", {})

    chart_data = []

    for driver in drivers:
        laps = lap_data.get(driver, [])
        analysis = lap_analysis.get(driver, {})

        # Get all lap times
        lap_times = []
        for lap in laps:
            time = lap.get("lap_time") or lap.get("lap_time_seconds")
            if time and time < 200:  # Filter outliers (pit laps, etc.)
                lap_times.append(time)

        if lap_times:
            lap_times_sorted = sorted(lap_times)
            n = len(lap_times_sorted)

            # Calculate quartiles
            q1_idx = n // 4
            q2_idx = n // 2
            q3_idx = (3 * n) // 4

            chart_data.append({
                "driver": driver,
                "min": round(lap_times_sorted[0], 3),
                "q1": round(lap_times_sorted[q1_idx], 3),
                "median": round(lap_times_sorted[q2_idx], 3),
                "q3": round(lap_times_sorted[q3_idx], 3),
                "max": round(lap_times_sorted[-1], 3),
                "mean": round(sum(lap_times) / len(lap_times), 3),
                "count": n,
                "color": DRIVER_COLORS.get(driver, "#888888"),
            })
        elif isinstance(analysis, dict) and analysis.get("average_pace"):
            # Fallback to analysis data
            chart_data.append({
                "driver": driver,
                "min": analysis.get("fastest_lap"),
                "q1": None,
                "median": analysis.get("average_pace"),
                "q3": None,
                "max": None,
                "mean": analysis.get("average_pace"),
                "count": analysis.get("total_laps", 0),
                "color": DRIVER_COLORS.get(driver, "#888888"),
            })

    if not chart_data:
        return None

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.BOX_PLOT,
        title=title or "Lap Time Distribution",
        data=chart_data,
        config={
            "xAxis": "driver",
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
        },
        drivers=drivers,
    )


def _generate_histogram(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate histogram of lap time frequency distribution."""
    lap_data = data.get("lap_times", {})
    if not lap_data:
        return None

    # Collect all lap times per driver
    all_times = {}
    for driver in drivers:
        laps = lap_data.get(driver, [])
        times = []
        for lap in laps:
            time = lap.get("lap_time") or lap.get("lap_time_seconds")
            if time and time < 200:
                times.append(time)
        if times:
            all_times[driver] = times

    if not all_times:
        return None

    # Create bins
    all_values = [t for times in all_times.values() for t in times]
    min_time = min(all_values)
    max_time = max(all_values)
    bin_width = (max_time - min_time) / 15  # 15 bins

    chart_data = []
    for i in range(15):
        bin_start = min_time + i * bin_width
        bin_end = bin_start + bin_width
        bin_label = f"{bin_start:.1f}-{bin_end:.1f}"

        point = {"bin": bin_label, "bin_start": round(bin_start, 2)}
        for driver, times in all_times.items():
            count = sum(1 for t in times if bin_start <= t < bin_end)
            point[driver] = count

        chart_data.append(point)

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.HISTOGRAM,
        title=title or "Lap Time Distribution",
        data=chart_data,
        config={
            "xAxis": "bin",
            "yAxis": drivers,
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
            "binWidth": round(bin_width, 2),
        },
        drivers=drivers,
    )


def _generate_violin_plot(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate violin plot data for distribution comparison."""
    lap_data = data.get("lap_times", {})
    if not lap_data:
        return None

    chart_data = []

    for driver in drivers:
        laps = lap_data.get(driver, [])
        times = []
        for lap in laps:
            time = lap.get("lap_time") or lap.get("lap_time_seconds")
            if time and time < 200:
                times.append(time)

        if times:
            times_sorted = sorted(times)
            n = len(times_sorted)

            # Calculate density estimation points (simplified)
            # For frontend, we'll pass the raw distribution data
            chart_data.append({
                "driver": driver,
                "values": [round(t, 3) for t in times_sorted],
                "min": round(times_sorted[0], 3),
                "max": round(times_sorted[-1], 3),
                "median": round(times_sorted[n // 2], 3),
                "mean": round(sum(times) / len(times), 3),
                "color": DRIVER_COLORS.get(driver, "#888888"),
            })

    if not chart_data:
        return None

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.VIOLIN_PLOT,
        title=title or "Pace Distribution Comparison",
        data=chart_data,
        config={
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
        },
        drivers=drivers,
    )


def _generate_scatter(
    data: dict[str, Any],
    drivers: list[str],
    title: str,
) -> VisualizationSpec | None:
    """Generate scatter plot (e.g., tire age vs lap time for degradation)."""
    lap_data = data.get("lap_times", {})
    if not lap_data:
        return None

    chart_data = []

    for driver in drivers:
        laps = lap_data.get(driver, [])
        for lap in laps:
            time = lap.get("lap_time") or lap.get("lap_time_seconds")
            tire_life = lap.get("tyre_life") or lap.get("tire_life")

            if time and tire_life and time < 200:
                chart_data.append({
                    "driver": driver,
                    "tire_age": tire_life,
                    "lap_time": round(time, 3),
                    "compound": lap.get("compound", "UNKNOWN"),
                    "lap_number": lap.get("lap_number"),
                    "color": DRIVER_COLORS.get(driver, "#888888"),
                })

    if not chart_data:
        return None

    return VisualizationSpec(
        id=str(uuid.uuid4()),
        type=ChartType.SCATTER,
        title=title or "Tire Degradation",
        data=chart_data,
        config={
            "xAxis": "tire_age",
            "yAxis": "lap_time",
            "colors": {d: DRIVER_COLORS.get(d, "#888888") for d in drivers},
            "compoundColors": COMPOUND_COLORS,
        },
        drivers=drivers,
    )
