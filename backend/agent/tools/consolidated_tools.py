"""Consolidated tool interface (WO F1 2f).

The agent originally bound 92 narrow tools (79 TimescaleDB + 8 Neo4j + 5 vector),
injecting ~14.6k tokens of schema into *every* request and forcing the model to
pick among 79 near-identical `get_*` options. This module exposes a small set of
**dispatcher tools** that route to the same underlying functions by an enum
parameter — the working query logic is unchanged (delegated via `.ainvoke`), only
the surface the model sees shrinks.

Design: each dispatcher takes a `metric` (the exact underlying tool name) plus the
common F1 args and an `extra` dict for tool-specific params; `_dispatch` filters
to the args the target tool actually accepts, so no underlying signature changes.
The long tail is reachable via the guarded `query_f1_sql` text-to-SQL tool.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import tool

from agent.tools.timescale_tools import TIMESCALE_TOOLS

# name -> underlying StructuredTool
_TS = {t.name: t for t in TIMESCALE_TOOLS}


async def _dispatch(name: str, extra: dict[str, Any] | None = None, **common: Any) -> Any:
    """Call an underlying tool by name, passing only the args it accepts."""
    tool_obj = _TS.get(name)
    if tool_obj is None:
        return {"error": f"unknown metric: {name}"}
    accepted = set(tool_obj.args or {})
    payload = {**{k: v for k, v in common.items() if v is not None}, **(extra or {})}
    valid = {k: v for k, v in payload.items() if k in accepted}
    return await tool_obj.ainvoke(valid)


# --- Group membership: literal value == exact underlying tool name ------------
RACE = Literal[
    "get_lap_times",
    "get_pit_stops",
    "get_driver_stint_summary",
    "compare_driver_pace",
    "get_tire_degradation",
    "get_weather_conditions",
    "get_session_results",
    "get_stint_analysis",
    "get_race_summary",
    "get_sector_performance",
    "get_overtaking_analysis",
    "get_compound_performance",
    "get_race_dominance",
    "get_gap_to_leader",
    "get_strategy_effectiveness",
    "get_undercut_success",
    "get_drs_effectiveness",
    "get_tire_warmup_specialist",
    "get_qualifying_improvement",
    "get_theoretical_best_lap",
    "get_race_pace_degradation",
    "get_pit_exit_performance",
    "get_traffic_management",
    "get_fuel_adjusted_pace",
    "get_tire_cliff_analysis",
    "get_average_race_position",
    "get_track_specialist",
    "get_team_lockouts",
]
DRIVER = Literal[
    "get_driver_season_summary",
    "get_qualifying_race_delta",
    "get_consistency_ranking",
    "get_wet_weather_performance",
    "get_lap1_performance",
    "get_fastest_lap_stats",
    "get_points_finish_rate",
    "get_career_stats",
    "get_qualifying_stats",
    "get_podium_stats",
    "get_sprint_performance",
    "get_winning_streaks",
    "get_home_race_performance",
    "get_comeback_drives",
    "get_grid_penalty_impact",
    "get_finishing_streaks",
    "get_safety_car_impact",
    "get_tire_life_masters",
    "get_points_per_start",
    "get_clean_weekend_rate",
    "get_pole_to_win_conversion",
    "get_circuit_type_performance",
    "get_q3_shootout_performance",
    "get_race_pace_vs_quali_pace",
    "get_position_battle_stats",
    "get_points_trajectory",
    "get_red_flag_restart_performance",
    "get_season_phase_performance",
    "get_back_to_back_performance",
    "get_championship_pressure_performance",
    "get_defensive_driving_stats",
    "get_reliability_stats",
    "get_final_lap_heroics",
    "get_grid_position_advantage",
    "get_performance_trend",
    "get_championship_momentum",
]
STANDINGS = Literal[
    "get_season_standings",
    "get_season_pace_ranking",
    "get_championship_evolution",
    "get_constructor_evolution",
    "get_rookie_comparison",
]
COMPARE = Literal[
    "get_head_to_head",
    "compare_teams",
    "get_driver_vs_field",
    "get_teammate_battle",
    "get_head_to_head_career",
]
WHATIF = Literal["simulate_pit_strategy", "find_similar_race_scenarios"]


@tool
async def race_analysis(
    metric: RACE,
    year: int | None = None,
    event_name: str | None = None,
    driver_id: str | None = None,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Analyze a specific race, session, or event: lap times, pit stops, tire and
    stint behaviour, sector/overtaking/DRS analysis, gaps, strategy, weather, and
    per-event driver form. `metric` selects the analysis; pass tool-specific params
    (e.g. compound, sector, stint, top_n) in `extra`."""
    return await _dispatch(
        metric, extra, year=year, event_name=event_name, driver_id=driver_id, session_id=session_id
    )


@tool
async def driver_stat(
    metric: DRIVER,
    driver_id: str | None = None,
    year: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Season- or career-level statistics for a driver: podiums, poles, points,
    consistency, streaks, wet-weather/home/circuit-type performance, reliability,
    and situational form. `metric` selects the statistic; extra params go in `extra`."""
    return await _dispatch(metric, extra, driver_id=driver_id, year=year)


@tool
async def standings(
    metric: STANDINGS,
    year: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Season-wide standings, rankings, and championship-points evolution for
    drivers or constructors. `metric` selects the view."""
    return await _dispatch(metric, extra, year=year)


@tool
async def compare(
    metric: COMPARE,
    year: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Head-to-head and comparative analysis between drivers or teams (season or
    career). Put the subjects (e.g. driver_1, driver_2, team, driver_ids) in `extra`."""
    return await _dispatch(metric, extra, year=year)


@tool
async def whatif(
    metric: WHATIF,
    year: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """What-if / scenario analysis: simulate an alternative pit strategy, or find
    historical races similar to a described scenario. Params go in `extra`."""
    return await _dispatch(metric, extra, year=year)


# --- Retained standalone tools (already single, well-scoped) ------------------
get_available_sessions = _TS["get_available_sessions"]
get_database_schema = _TS["get_database_schema"]
query_f1_sql = _TS[
    "query_f1_database"
]  # existing tool already SQL-validated (see agent/validation.py)


# Everything the model sees: 5 dispatchers + 3 standalone = 8 (was 79).
CONSOLIDATED_TIMESCALE_TOOLS = [
    race_analysis,
    driver_stat,
    standings,
    compare,
    whatif,
    get_available_sessions,
    get_database_schema,
    query_f1_sql,
]

# Literal groups, exposed for the coverage test.
_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "race_analysis": RACE.__args__,  # type: ignore[attr-defined]
    "driver_stat": DRIVER.__args__,  # type: ignore[attr-defined]
    "standings": STANDINGS.__args__,  # type: ignore[attr-defined]
    "compare": COMPARE.__args__,  # type: ignore[attr-defined]
    "whatif": WHATIF.__args__,  # type: ignore[attr-defined]
    "_standalone": ("get_available_sessions", "get_database_schema", "query_f1_database"),
}
