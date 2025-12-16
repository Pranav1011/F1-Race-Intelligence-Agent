"""
TimescaleDB Tools

Tools for querying F1 telemetry, lap times, and weather data from TimescaleDB.
Includes Redis caching for fast repeated queries.
Includes validation for year ranges, driver participation, and data availability.
"""

import logging
from typing import Any

import asyncpg
from langchain_core.tools import tool

from db.cache import cached, cache_get, cache_set, _generate_cache_key, CACHE_TTL
from agent.validation import (
    validate_year,
    validate_driver,
    validate_race_name,
    normalize_driver_id,
    normalize_race_name,
    validate_tool_result,
    check_driver_in_result,
    ErrorCode,
    create_user_friendly_error,
    suggest_alternatives_for_empty_result,
)

logger = logging.getLogger(__name__)

# Connection pool (initialized at startup)
_pool: asyncpg.Pool | None = None


async def init_pool(connection_string: str):
    """Initialize the connection pool."""
    global _pool
    _pool = await asyncpg.create_pool(connection_string, min_size=2, max_size=10)
    logger.info("TimescaleDB tool pool initialized")


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@tool
async def get_lap_times(
    session_id: str | None = None,
    driver_id: str | None = None,
    year: int | None = None,
    event_name: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Get lap times for a race session.

    Args:
        session_id: Specific session ID (e.g., "2024_1_R")
        driver_id: Filter by driver abbreviation (e.g., "VER", "HAM")
        year: Filter by season year (1950-2025)
        event_name: Filter by race name (partial match)
        limit: Maximum number of results

    Returns:
        List of lap time records with driver, lap number, times, tire info.
        Returns error dict with suggestions if validation fails or no data found.
    """
    if not _pool:
        return [{"error": "Database connection not initialized", "code": "DATABASE_CONNECTION_ERROR"}]

    # Validate inputs
    year_validation = validate_year(year)
    if not year_validation.is_valid:
        return [year_validation.to_dict()["error"]]

    driver_validation = validate_driver(driver_id)
    if not driver_validation.is_valid:
        return [driver_validation.to_dict()["error"]]

    race_validation = validate_race_name(event_name)
    if not race_validation.is_valid:
        return [race_validation.to_dict()["error"]]

    # Normalize inputs
    norm_driver = normalize_driver_id(driver_id) if driver_id else None
    norm_race = normalize_race_name(event_name) if event_name else None

    try:
        query = """
            SELECT
                lt.session_id,
                lt.driver_id,
                lt.lap_number,
                lt.lap_time_seconds,
                lt.sector_1_seconds,
                lt.sector_2_seconds,
                lt.sector_3_seconds,
                lt.compound,
                lt.tire_life,
                lt.stint,
                lt.position,
                s.event_name,
                s.year
            FROM lap_times lt
            JOIN sessions s ON lt.session_id = s.session_id
            WHERE 1=1
        """
        params = []
        param_idx = 1

        if session_id:
            query += f" AND lt.session_id = ${param_idx}"
            params.append(session_id)
            param_idx += 1

        if norm_driver:
            query += f" AND lt.driver_id = ${param_idx}"
            params.append(norm_driver)
            param_idx += 1

        if year:
            query += f" AND s.year = ${param_idx}"
            params.append(year)
            param_idx += 1

        if norm_race:
            # Use ILIKE for partial match with normalized name
            query += f" AND s.event_name ILIKE ${param_idx}"
            params.append(f"%{norm_race}%")
            param_idx += 1

        query += f" ORDER BY lt.lap_number LIMIT ${param_idx}"
        params.append(limit)

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            results = [dict(row) for row in rows]

        # Validate results
        if not results:
            suggestions = suggest_alternatives_for_empty_result(
                "lap_times",
                {"year": year, "driver_id": driver_id, "event_name": event_name}
            )
            return [{
                "error": "No lap time data found for the specified criteria",
                "code": "NO_TELEMETRY_DATA",
                "suggestions": suggestions,
                "query_params": {
                    "driver": norm_driver,
                    "year": year,
                    "race": norm_race,
                }
            }]

        # If driver was specified, verify they're in results
        if norm_driver:
            driver_check = check_driver_in_result(results, norm_driver)
            if not driver_check.is_valid:
                return [driver_check.to_dict()["error"]]

        return results

    except asyncpg.exceptions.QueryCanceledError:
        return [{"error": "Query timed out. Try adding more filters.", "code": "DATABASE_TIMEOUT"}]
    except Exception as e:
        logger.error(f"Error getting lap times: {e}")
        return [{"error": str(e), "code": "DATABASE_QUERY_ERROR"}]


@tool
async def get_driver_stint_summary(
    session_id: str,
    driver_id: str,
) -> list[dict]:
    """
    Get stint summary for a driver in a session.

    Args:
        session_id: Session ID (e.g., "2024_1_R")
        driver_id: Driver abbreviation (e.g., "VER")

    Returns:
        List of stints with compound, lap range, average pace
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                stint,
                compound,
                MIN(lap_number) as start_lap,
                MAX(lap_number) as end_lap,
                COUNT(*) as lap_count,
                AVG(lap_time_seconds) as avg_lap_time,
                MIN(lap_time_seconds) as best_lap_time,
                AVG(tire_life) as avg_tire_life
            FROM lap_times
            WHERE session_id = $1 AND driver_id = $2
            GROUP BY stint, compound
            ORDER BY stint
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, session_id, driver_id.upper())
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting stint summary: {e}")
        return [{"error": str(e)}]


@tool
async def compare_driver_pace(
    session_id: str,
    driver_ids: list[str],
    stint: int | None = None,
) -> dict:
    """
    Compare pace between drivers in a session.

    Args:
        session_id: Session ID (e.g., "2024_1_R")
        driver_ids: List of driver abbreviations or names to compare
        stint: Specific stint to compare (optional)

    Returns:
        Comparison data with average pace, best laps, consistency.
        Includes warnings for drivers not found in the session.
    """
    if not _pool:
        return {"error": "Database connection not initialized", "code": "DATABASE_CONNECTION_ERROR"}

    if not driver_ids or len(driver_ids) < 2:
        return {
            "error": "At least 2 drivers required for comparison",
            "code": "INVALID_PARAMETER",
            "suggestion": "Provide a list of 2 or more driver codes (e.g., ['VER', 'HAM'])"
        }

    # Validate and normalize driver IDs
    normalized_drivers = []
    validation_errors = []

    for driver_id in driver_ids:
        driver_validation = validate_driver(driver_id)
        if not driver_validation.is_valid:
            validation_errors.append(driver_validation.to_dict()["error"])
        else:
            normalized_drivers.append(normalize_driver_id(driver_id))

    # Remove duplicates
    normalized_drivers = list(set(normalized_drivers))

    if len(normalized_drivers) < 2:
        if validation_errors:
            return {"error": "Could not validate drivers", "validation_errors": validation_errors}
        return {
            "error": "Need at least 2 distinct drivers for comparison",
            "code": "INVALID_PARAMETER",
        }

    try:
        results = {}
        missing_drivers = []

        for driver in normalized_drivers:
            query = """
                SELECT
                    driver_id,
                    COUNT(*) as total_laps,
                    AVG(lap_time_seconds) as avg_lap_time,
                    MIN(lap_time_seconds) as best_lap_time,
                    STDDEV(lap_time_seconds) as pace_consistency,
                    AVG(CASE WHEN stint = $3 OR $3 IS NULL THEN lap_time_seconds END) as stint_avg
                FROM lap_times
                WHERE session_id = $1
                    AND driver_id = $2
                    AND lap_time_seconds IS NOT NULL
                    AND lap_time_seconds > 60  -- Filter out pit laps
                GROUP BY driver_id
            """

            async with _pool.acquire() as conn:
                row = await conn.fetchrow(query, session_id, driver, stint)
                if row:
                    results[driver] = dict(row)
                else:
                    missing_drivers.append(driver)

        # If no drivers found at all
        if not results:
            # Check if session exists
            async with _pool.acquire() as conn:
                session_check = await conn.fetchrow(
                    "SELECT event_name, year FROM sessions WHERE session_id = $1",
                    session_id
                )

            if not session_check:
                return {
                    "error": f"Session '{session_id}' not found",
                    "code": "SESSION_NOT_FOUND",
                    "suggestion": "Session IDs are formatted as '{year}_{round}_{type}' (e.g., '2024_1_R' for 2024 Bahrain Race)"
                }

            # Get drivers who did participate
            participants = await conn.fetch(
                "SELECT DISTINCT driver_id FROM lap_times WHERE session_id = $1",
                session_id
            )
            participant_list = [r["driver_id"] for r in participants]

            return {
                "error": f"None of the specified drivers participated in {session_check['event_name']} {session_check['year']}",
                "code": "DRIVER_NOT_IN_RACE",
                "requested_drivers": normalized_drivers,
                "available_drivers": participant_list[:10],
                "suggestion": "These drivers were in this session. Try comparing some of them."
            }

        # Some but not all drivers found - return results with warning
        response = {
            "comparison": results,
            "session_id": session_id,
            "drivers_compared": list(results.keys()),
        }

        if missing_drivers:
            response["warnings"] = [{
                "code": "DRIVER_NOT_IN_RACE",
                "message": f"Driver(s) not found in this session: {', '.join(missing_drivers)}",
                "missing_drivers": missing_drivers,
            }]

        if validation_errors:
            response["validation_warnings"] = validation_errors

        return response

    except Exception as e:
        logger.error(f"Error comparing driver pace: {e}")
        return {"error": str(e), "code": "DATABASE_QUERY_ERROR"}


@tool
async def get_tire_degradation(
    session_id: str,
    driver_id: str,
    compound: str | None = None,
) -> list[dict]:
    """
    Analyze tire degradation for a driver.

    Args:
        session_id: Session ID (e.g., "2024_1_R")
        driver_id: Driver abbreviation (e.g., "VER")
        compound: Specific tire compound (SOFT, MEDIUM, HARD)

    Returns:
        Lap-by-lap degradation data showing pace drop-off
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                lap_number,
                lap_time_seconds,
                tire_life,
                compound,
                stint,
                LAG(lap_time_seconds) OVER (PARTITION BY stint ORDER BY lap_number) as prev_lap_time,
                lap_time_seconds - LAG(lap_time_seconds) OVER (PARTITION BY stint ORDER BY lap_number) as delta
            FROM lap_times
            WHERE session_id = $1
                AND driver_id = $2
                AND lap_time_seconds IS NOT NULL
                AND lap_time_seconds > 60
        """
        params = [session_id, driver_id.upper()]

        if compound:
            query += " AND compound = $3"
            params.append(compound.upper())

        query += " ORDER BY lap_number"

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting tire degradation: {e}")
        return [{"error": str(e)}]


@tool
async def get_weather_conditions(
    session_id: str,
) -> list[dict]:
    """
    Get weather conditions during a session.

    Args:
        session_id: Session ID (e.g., "2024_1_R")

    Returns:
        Weather data including track temp, air temp, rainfall
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                time,
                air_temp,
                track_temp,
                humidity,
                wind_speed,
                wind_direction,
                rainfall
            FROM weather
            WHERE session_id = $1
            ORDER BY time
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, session_id)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting weather: {e}")
        return [{"error": str(e)}]


@tool
async def get_session_results(
    session_id: str | None = None,
    year: int | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Get race/qualifying results.

    Args:
        session_id: Specific session ID
        year: Filter by season
        driver_id: Filter by driver

    Returns:
        Results with positions, points, status
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                r.session_id,
                r.driver_id,
                r.driver_name,
                r.team,
                r.position,
                r.grid_position,
                r.status,
                r.points,
                s.event_name,
                s.year
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE 1=1
        """
        params = []
        param_idx = 1

        if session_id:
            query += f" AND r.session_id = ${param_idx}"
            params.append(session_id)
            param_idx += 1

        if year:
            query += f" AND s.year = ${param_idx}"
            params.append(year)
            param_idx += 1

        if driver_id:
            query += f" AND r.driver_id = ${param_idx}"
            params.append(driver_id.upper())
            param_idx += 1

        query += " ORDER BY r.position"

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting results: {e}")
        return [{"error": str(e)}]


@tool
async def get_available_sessions(
    year: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Get list of available sessions in the database.

    Args:
        year: Filter by season year
        limit: Maximum number of results

    Returns:
        List of sessions with metadata
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                session_id,
                year,
                round_number,
                event_name,
                session_type,
                circuit
            FROM sessions
            WHERE 1=1
        """
        params = []
        param_idx = 1

        if year:
            query += f" AND year = ${param_idx}"
            params.append(year)
            param_idx += 1

        query += f" ORDER BY year DESC, round_number DESC LIMIT ${param_idx}"
        params.append(limit)

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return [{"error": str(e)}]


# ============================================================
# FAST TOOLS (using materialized views)
# ============================================================

@tool
async def get_head_to_head(
    driver_1: str,
    driver_2: str,
    year: int | None = None,
    event_name: str | None = None,
) -> list[dict]:
    """
    Get pre-computed head-to-head comparison between two drivers.
    FAST: Uses materialized view + Redis cache for instant results.

    Args:
        driver_1: First driver abbreviation or name (e.g., "VER", "Verstappen")
        driver_2: Second driver abbreviation or name (e.g., "HAM", "Hamilton")
        year: Filter by season year (1950-2025)
        event_name: Filter by race name (partial match)

    Returns:
        List of race-by-race comparisons with pace delta, sector deltas.
        Returns error with suggestions if drivers not found or didn't race together.
    """
    if not _pool:
        return [{"error": "Database connection not initialized", "code": "DATABASE_CONNECTION_ERROR"}]

    # Validate inputs
    year_validation = validate_year(year)
    if not year_validation.is_valid:
        return [year_validation.to_dict()["error"]]

    driver1_validation = validate_driver(driver_1)
    if not driver1_validation.is_valid:
        return [driver1_validation.to_dict()["error"]]

    driver2_validation = validate_driver(driver_2)
    if not driver2_validation.is_valid:
        return [driver2_validation.to_dict()["error"]]

    # Normalize driver IDs
    d1_norm = normalize_driver_id(driver_1)
    d2_norm = normalize_driver_id(driver_2)

    # Check if comparing same driver
    if d1_norm == d2_norm:
        return [{
            "error": f"Cannot compare {d1_norm} to themselves",
            "code": "INVALID_COMPARISON",
            "suggestion": "Please provide two different drivers for comparison"
        }]

    # Normalize driver order (alphabetical in materialized view)
    d1, d2 = sorted([d1_norm, d2_norm])

    # Check cache first
    cache_key = _generate_cache_key("head_to_head", d1=d1, d2=d2, year=year, event=event_name)
    cached_result = await cache_get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache HIT: head_to_head {d1} vs {d2}")
        return cached_result

    try:
        query = """
            SELECT
                year,
                event_name,
                driver_1,
                driver_2,
                driver_1_pace,
                driver_2_pace,
                pace_delta,
                driver_1_fastest,
                driver_2_fastest,
                fastest_delta,
                s1_delta,
                s2_delta,
                s3_delta,
                comparable_laps
            FROM mv_head_to_head
            WHERE driver_1 = $1 AND driver_2 = $2
        """
        params = [d1, d2]
        param_idx = 3

        if year:
            query += f" AND year = ${param_idx}"
            params.append(year)
            param_idx += 1

        if event_name:
            norm_race = normalize_race_name(event_name)
            query += f" AND event_name ILIKE ${param_idx}"
            params.append(f"%{norm_race}%")
            param_idx += 1

        query += " ORDER BY year, event_name"

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            result = [dict(row) for row in rows]

        # Handle empty results with helpful message
        if not result:
            error_context = {
                "driver1": d1_norm,
                "driver2": d2_norm,
                "year": year,
                "race": event_name
            }

            # Check if either driver has any data in the specified year
            check_query = """
                SELECT DISTINCT driver_id, year FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                WHERE driver_id IN ($1, $2)
            """
            check_params = [d1, d2]
            if year:
                check_query += " AND s.year = $3"
                check_params.append(year)

            async with _pool.acquire() as conn:
                driver_data = await conn.fetch(check_query, *check_params)

            found_drivers = {row["driver_id"] for row in driver_data}
            found_years = {row["year"] for row in driver_data}

            suggestions = []

            if d1 not in found_drivers:
                suggestions.append(f"{d1} has no race data" + (f" for {year}" if year else ""))
            if d2 not in found_drivers:
                suggestions.append(f"{d2} has no race data" + (f" for {year}" if year else ""))

            if found_drivers and found_years:
                if year and year not in found_years:
                    available_years = sorted(found_years, reverse=True)[:5]
                    suggestions.append(f"Data available for: {', '.join(map(str, available_years))}")
                else:
                    suggestions.append(f"{d1} and {d2} may not have raced together in comparable sessions")

            return [{
                "error": f"No head-to-head data found for {d1_norm} vs {d2_norm}" + (f" in {year}" if year else ""),
                "code": "NO_COMPARISON_DATA",
                "suggestions": suggestions or ["Try different drivers or a different year"],
                "query_params": error_context
            }]

        # Cache the result
        await cache_set(cache_key, result, CACHE_TTL["head_to_head"])
        return result

    except Exception as e:
        logger.error(f"Error getting head-to-head: {e}")
        return [{"error": str(e), "code": "DATABASE_QUERY_ERROR"}]


@tool
async def get_driver_season_summary(
    driver_id: str,
    year: int,
) -> dict:
    """
    Get season summary for a driver including all race stats.
    FAST: Uses materialized views + Redis cache for instant results.

    Args:
        driver_id: Driver abbreviation (e.g., "VER")
        year: Season year

    Returns:
        Season statistics including wins, podiums, average pace by race
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    driver = driver_id.upper()

    # Check cache first
    cache_key = _generate_cache_key("driver_season", driver=driver, year=year)
    cached_result = await cache_get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache HIT: driver_season {driver} {year}")
        return cached_result

    try:
        # Get standings
        standings_query = """
            SELECT * FROM mv_season_standings
            WHERE year = $1 AND driver_id = $2
        """

        # Get race-by-race summary
        races_query = """
            SELECT
                event_name,
                circuit,
                total_laps,
                fastest_lap,
                avg_lap_time,
                consistency,
                total_stints,
                best_position
            FROM mv_driver_race_summary
            WHERE year = $1 AND driver_id = $2
            ORDER BY round_number
        """

        async with _pool.acquire() as conn:
            standings = await conn.fetchrow(standings_query, year, driver)
            races = await conn.fetch(races_query, year, driver)

            result = {
                "standings": dict(standings) if standings else None,
                "races": [dict(row) for row in races],
            }

        # Cache the result
        await cache_set(cache_key, result, CACHE_TTL["driver_season"])
        return result

    except Exception as e:
        logger.error(f"Error getting driver season summary: {e}")
        return {"error": str(e)}


@tool
async def get_race_summary(
    year: int,
    event_name: str | None = None,
    round_number: int | None = None,
) -> list[dict]:
    """
    Get race statistics summary.
    FAST: Uses materialized view + Redis cache for instant results.

    Args:
        year: Season year
        event_name: Race name (partial match)
        round_number: Round number

    Returns:
        Race statistics including winner, fastest lap, avg pace
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    # Check cache first
    cache_key = _generate_cache_key("race_summary", year=year, event=event_name, round=round_number)
    cached_result = await cache_get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache HIT: race_summary {year}")
        return cached_result

    try:
        query = """
            SELECT * FROM mv_race_statistics
            WHERE year = $1
        """
        params = [year]
        param_idx = 2

        if event_name:
            query += f" AND event_name ILIKE ${param_idx}"
            params.append(f"%{event_name}%")
            param_idx += 1

        if round_number:
            query += f" AND round_number = ${param_idx}"
            params.append(round_number)
            param_idx += 1

        query += " ORDER BY round_number"

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            result = [dict(row) for row in rows]

        # Cache the result
        await cache_set(cache_key, result, CACHE_TTL["race_summary"])
        return result

    except Exception as e:
        logger.error(f"Error getting race summary: {e}")
        return [{"error": str(e)}]


@tool
async def get_stint_analysis(
    year: int,
    event_name: str,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Get detailed stint analysis for a race.
    FAST: Uses materialized view + Redis cache for instant results.

    Args:
        year: Season year
        event_name: Race name (partial match)
        driver_id: Optional driver filter

    Returns:
        Stint data with compound, laps, pace, degradation
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = driver_id.upper() if driver_id else None

    # Check cache first
    cache_key = _generate_cache_key("stint_analysis", year=year, event=event_name, driver=driver)
    cached_result = await cache_get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache HIT: stint_analysis {year} {event_name}")
        return cached_result

    try:
        query = """
            SELECT
                driver_id,
                stint,
                compound,
                start_lap,
                end_lap,
                stint_laps,
                avg_pace,
                best_lap,
                max_tire_age,
                estimated_degradation
            FROM mv_stint_summary
            WHERE year = $1 AND event_name ILIKE $2
        """
        params = [year, f"%{event_name}%"]

        if driver:
            query += " AND driver_id = $3"
            params.append(driver)

        query += " ORDER BY driver_id, stint"

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            result = [dict(row) for row in rows]

        # Cache the result
        await cache_set(cache_key, result, CACHE_TTL["stint_analysis"])
        return result

    except Exception as e:
        logger.error(f"Error getting stint analysis: {e}")
        return [{"error": str(e)}]


@tool
async def get_season_standings(
    year: int,
    limit: int = 20,
) -> list[dict]:
    """
    Get championship standings for a season.
    FAST: Uses materialized view + Redis cache for instant results.

    Args:
        year: Season year
        limit: Number of drivers to return

    Returns:
        Championship standings with points, wins, podiums
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    # Check cache first
    cache_key = _generate_cache_key("season_standings", year=year, limit=limit)
    cached_result = await cache_get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache HIT: season_standings {year}")
        return cached_result

    try:
        query = """
            SELECT
                driver_id,
                driver_name,
                team,
                races,
                total_points,
                wins,
                podiums,
                points_finishes,
                avg_position,
                best_finish
            FROM mv_season_standings
            WHERE year = $1
            ORDER BY total_points DESC
            LIMIT $2
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, limit)
            result = [dict(row) for row in rows]

        # Cache the result
        await cache_set(cache_key, result, CACHE_TTL["season_standings"])
        return result

    except Exception as e:
        logger.error(f"Error getting standings: {e}")
        return [{"error": str(e)}]


# ============================================================
# TEXT-TO-SQL TOOL (Flexible Queries)
# ============================================================

# SQL validation patterns
ALLOWED_SQL_PATTERNS = [
    "SELECT",
]

BLOCKED_SQL_PATTERNS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "EXECUTE", "COPY", "VACUUM", "REINDEX",
    "--", ";--", "/*", "*/", "@@", "@",
]

# Database schema documentation for LLM
DATABASE_SCHEMA = """
Available Tables:

1. lap_times (time-series lap data)
   - session_id: VARCHAR (e.g., "2024_1_R" = 2024 Round 1 Race)
   - driver_id: VARCHAR (3-letter code, e.g., "VER", "HAM")
   - lap_number: INT
   - lap_time_seconds: FLOAT (total lap time)
   - sector_1_seconds: FLOAT
   - sector_2_seconds: FLOAT
   - sector_3_seconds: FLOAT
   - compound: VARCHAR (SOFT, MEDIUM, HARD, INTERMEDIATE, WET)
   - tire_life: INT (laps on current tire set)
   - stint: INT (pit stop number, 1 = first stint)
   - position: INT (track position at end of lap)
   - team: VARCHAR

2. sessions (race weekend sessions)
   - session_id: VARCHAR (primary key)
   - year: INT
   - round_number: INT
   - event_name: VARCHAR (e.g., "Bahrain Grand Prix")
   - session_type: VARCHAR (R=Race, Q=Quali, FP1/FP2/FP3=Practice, S=Sprint)
   - circuit: VARCHAR
   - session_date: TIMESTAMP

3. results (final race/quali results)
   - session_id: VARCHAR
   - driver_id: VARCHAR
   - driver_name: VARCHAR (full name)
   - team: VARCHAR
   - position: INT (finishing position)
   - grid_position: INT (starting position)
   - status: VARCHAR (Finished, +1 Lap, Retired, etc.)
   - points: FLOAT
   - fastest_lap_time: FLOAT

4. weather (track conditions)
   - session_id: VARCHAR
   - time: TIMESTAMP
   - air_temp: FLOAT (Celsius)
   - track_temp: FLOAT (Celsius)
   - humidity: FLOAT (percentage)
   - wind_speed: FLOAT (m/s)
   - wind_direction: INT (degrees)
   - rainfall: BOOLEAN

Materialized Views (pre-aggregated, fast):
- mv_driver_race_summary: Per-driver, per-race aggregated stats
- mv_race_statistics: Race summaries with winner, fastest lap
- mv_head_to_head: Pre-computed driver pair comparisons
- mv_stint_summary: Stint analysis with degradation estimates
- mv_season_standings: Championship standings by year
- mv_lap_percentiles: Lap time percentiles for outlier detection

Common Patterns:
- Filter races: WHERE session_id LIKE '2024%' AND session_type = 'R'
- Filter valid laps: WHERE lap_time_seconds > 60 AND lap_time_seconds < 200
- Join for race info: JOIN sessions s ON l.session_id = s.session_id
"""


def _validate_sql(sql: str) -> tuple[bool, str]:
    """Validate SQL query for safety."""
    sql_upper = sql.upper().strip()

    # Must start with SELECT
    if not sql_upper.startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    # Check for blocked patterns
    for pattern in BLOCKED_SQL_PATTERNS:
        if pattern.upper() in sql_upper:
            return False, f"Query contains blocked pattern: {pattern}"

    # Check for multiple statements
    if sql.count(";") > 1:
        return False, "Multiple statements not allowed"

    return True, "OK"


@tool
async def query_f1_database(
    sql_query: str,
    explanation: str = "",
) -> dict:
    """
    Execute a custom SQL query against the F1 database.
    Use this for complex queries that can't be answered by other tools.

    IMPORTANT: Only SELECT queries are allowed. Include LIMIT to avoid huge results.

    Args:
        sql_query: The SQL SELECT query to execute. Must include LIMIT clause.
        explanation: Brief explanation of what this query does (for logging).

    Database Schema:
    - lap_times: session_id, driver_id, lap_number, lap_time_seconds, sector_1/2/3_seconds, compound, tire_life, stint, position, team
    - sessions: session_id, year, round_number, event_name, session_type (R/Q/FP1/FP2/FP3/S), circuit, session_date
    - results: session_id, driver_id, driver_name, team, position, grid_position, status, points
    - weather: session_id, time, air_temp, track_temp, humidity, wind_speed, rainfall

    Session ID format: "{year}_{round}_{type}" e.g., "2024_1_R" = 2024 Bahrain Race

    Example queries:
    - "SELECT driver_id, COUNT(*) as wins FROM results WHERE position = 1 GROUP BY driver_id ORDER BY wins DESC LIMIT 10"
    - "SELECT driver_id, AVG(lap_time_seconds) as avg_pace FROM lap_times WHERE session_id = '2024_1_R' AND lap_time_seconds > 60 GROUP BY driver_id"

    Returns:
        Query results as list of dicts, or error message
    """
    if not _pool:
        return {"error": "Database connection not initialized", "rows": []}

    # Validate the query
    is_valid, message = _validate_sql(sql_query)
    if not is_valid:
        return {"error": message, "rows": []}

    # Ensure LIMIT is present (add default if missing)
    if "LIMIT" not in sql_query.upper():
        sql_query = sql_query.rstrip(";") + " LIMIT 100"

    try:
        logger.info(f"Text-to-SQL query: {explanation or 'No explanation'}")
        logger.debug(f"SQL: {sql_query}")

        async with _pool.acquire() as conn:
            # Set statement timeout (10 seconds max)
            await conn.execute("SET statement_timeout = '10s'")

            rows = await conn.fetch(sql_query)
            result = [dict(row) for row in rows]

            return {
                "success": True,
                "row_count": len(result),
                "rows": result,
                "query": sql_query,
            }

    except asyncpg.exceptions.QueryCanceledError:
        return {"error": "Query timed out (>10 seconds). Try adding more filters or LIMIT.", "rows": []}
    except Exception as e:
        logger.error(f"Text-to-SQL error: {e}")
        return {"error": str(e), "rows": []}


@tool
async def get_database_schema() -> str:
    """
    Get the F1 database schema documentation.
    Use this to understand available tables and columns before writing SQL queries.

    Returns:
        Detailed schema documentation with table structures and common patterns.
    """
    return DATABASE_SCHEMA


# ============================================================
# STRATEGY SIMULATOR (What-If Scenarios)
# ============================================================

@tool
async def simulate_pit_strategy(
    session_id: str,
    driver_id: str,
    actual_pit_laps: list[int] | None = None,
    alternative_pit_laps: list[int] = [],
    alternative_compounds: list[str] = [],
) -> dict:
    """
    Simulate alternative pit strategy and estimate the outcome.
    Answers "what if" questions like "What if Max pitted on lap 20 instead of 25?"

    Args:
        session_id: Race session ID (e.g., "2024_1_R")
        driver_id: Driver to simulate (e.g., "VER")
        actual_pit_laps: Override actual pit laps (auto-detected if None)
        alternative_pit_laps: New pit lap numbers to simulate
        alternative_compounds: Compounds for each stint (e.g., ["MEDIUM", "HARD", "SOFT"])

    Returns:
        Simulation results with estimated time delta and position impact
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    driver = driver_id.upper()

    try:
        async with _pool.acquire() as conn:
            # Get actual race data for the driver
            lap_data = await conn.fetch("""
                SELECT
                    lap_number, lap_time_seconds, compound, tire_life, stint, position
                FROM lap_times
                WHERE session_id = $1 AND driver_id = $2
                    AND lap_time_seconds > 60 AND lap_time_seconds < 200
                ORDER BY lap_number
            """, session_id, driver)

            if not lap_data:
                return {"error": f"No lap data found for {driver} in {session_id}"}

            laps = [dict(row) for row in lap_data]
            total_laps = max(l["lap_number"] for l in laps)

            # Detect actual pit stops
            if actual_pit_laps is None:
                actual_pit_laps = []
                for i in range(1, len(laps)):
                    if laps[i]["stint"] != laps[i-1]["stint"]:
                        actual_pit_laps.append(laps[i]["lap_number"])

            # Get tire degradation rates by compound
            deg_rates = await conn.fetch("""
                SELECT
                    compound,
                    AVG(lap_time_seconds) as avg_pace,
                    -- Estimate deg as difference between avg of last 5 vs first 5 laps per stint
                    STDDEV(lap_time_seconds) as pace_variance
                FROM lap_times
                WHERE session_id = $1
                    AND lap_time_seconds > 60 AND lap_time_seconds < 200
                GROUP BY compound
            """, session_id)

            compound_pace = {row["compound"]: row["avg_pace"] for row in deg_rates}

            # Estimate pit stop time loss
            PIT_STOP_LOSS = 23.0  # seconds (typical pit stop delta)

            # Calculate actual race time
            actual_time = sum(l["lap_time_seconds"] for l in laps if l["lap_time_seconds"])
            actual_pits = len(actual_pit_laps)

            # Simulate alternative strategy
            if not alternative_pit_laps:
                return {
                    "driver": driver,
                    "session_id": session_id,
                    "actual_pit_laps": actual_pit_laps,
                    "actual_pit_count": actual_pits,
                    "actual_total_time": actual_time,
                    "total_laps": total_laps,
                    "message": "Provide alternative_pit_laps to simulate a different strategy",
                    "compound_avg_pace": compound_pace,
                }

            # Build stint structure for alternative strategy
            alt_pit_laps = sorted(alternative_pit_laps)
            alt_stints = []
            prev_lap = 1

            for i, pit_lap in enumerate(alt_pit_laps + [total_laps + 1]):
                stint_start = prev_lap
                stint_end = pit_lap - 1 if pit_lap <= total_laps else total_laps
                stint_length = stint_end - stint_start + 1

                # Get compound for this stint
                compound = alternative_compounds[i] if i < len(alternative_compounds) else "MEDIUM"
                compound = compound.upper()

                # Estimate stint time using compound pace + degradation model
                base_pace = compound_pace.get(compound, 95.0)

                # Simple degradation model: pace degrades ~0.05s per lap on tires
                DEG_RATES = {"SOFT": 0.08, "MEDIUM": 0.05, "HARD": 0.03, "INTERMEDIATE": 0.04, "WET": 0.02}
                deg_rate = DEG_RATES.get(compound, 0.05)

                stint_time = 0
                for lap_in_stint in range(stint_length):
                    lap_time = base_pace + (lap_in_stint * deg_rate)
                    stint_time += lap_time

                alt_stints.append({
                    "stint": i + 1,
                    "start_lap": stint_start,
                    "end_lap": stint_end,
                    "length": stint_length,
                    "compound": compound,
                    "estimated_time": round(stint_time, 3),
                })

                prev_lap = pit_lap + 1

            # Calculate alternative total time
            alt_race_time = sum(s["estimated_time"] for s in alt_stints)
            alt_pit_time = len(alt_pit_laps) * PIT_STOP_LOSS
            alt_total_time = alt_race_time + alt_pit_time

            # Compare to actual
            time_delta = alt_total_time - actual_time

            # Estimate position change (~0.3s per position in midfield)
            SECONDS_PER_POSITION = 0.5
            estimated_position_change = -round(time_delta / SECONDS_PER_POSITION)

            return {
                "driver": driver,
                "session_id": session_id,
                "simulation": {
                    "alternative_pit_laps": alt_pit_laps,
                    "alternative_compounds": [s["compound"] for s in alt_stints],
                    "stints": alt_stints,
                    "estimated_race_time": round(alt_race_time, 3),
                    "pit_stop_time_loss": round(alt_pit_time, 3),
                    "estimated_total_time": round(alt_total_time, 3),
                },
                "comparison": {
                    "actual_pit_laps": actual_pit_laps,
                    "actual_total_time": round(actual_time, 3),
                    "time_delta": round(time_delta, 3),
                    "delta_description": f"{'+' if time_delta > 0 else ''}{time_delta:.3f}s vs actual",
                    "estimated_position_change": estimated_position_change,
                    "position_description": f"{'Gain' if estimated_position_change > 0 else 'Lose'} ~{abs(estimated_position_change)} position(s)" if estimated_position_change != 0 else "Similar position",
                },
                "assumptions": {
                    "pit_stop_loss": PIT_STOP_LOSS,
                    "degradation_model": "Linear approximation based on compound",
                    "note": "This is a simplified simulation. Real outcomes depend on traffic, safety cars, and competitor strategies.",
                },
            }

    except Exception as e:
        logger.error(f"Strategy simulation error: {e}")
        return {"error": str(e)}


@tool
async def find_similar_race_scenarios(
    scenario_description: str,
    year: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Find historical races with similar scenarios for what-if analysis.
    Use this to find precedents for strategy questions.

    Args:
        scenario_description: Description of the scenario (e.g., "early pit stop undercut", "wet to dry transition", "safety car restart")
        year: Optional year filter
        limit: Maximum results to return

    Returns:
        List of similar historical scenarios with outcomes
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    # Map common scenarios to SQL patterns
    scenario_lower = scenario_description.lower()

    try:
        async with _pool.acquire() as conn:
            results = []

            # Scenario: Undercut (driver pits early and gains position)
            if "undercut" in scenario_lower or "early pit" in scenario_lower:
                query = """
                    WITH stint_changes AS (
                        SELECT
                            l1.session_id,
                            l1.driver_id,
                            l1.lap_number as pit_lap,
                            l1.position as pos_before,
                            l2.position as pos_after,
                            s.year,
                            s.event_name
                        FROM lap_times l1
                        JOIN lap_times l2 ON l1.session_id = l2.session_id
                            AND l1.driver_id = l2.driver_id
                            AND l2.lap_number = l1.lap_number + 3
                        JOIN sessions s ON l1.session_id = s.session_id
                        WHERE l1.stint != (SELECT stint FROM lap_times WHERE session_id = l1.session_id AND driver_id = l1.driver_id AND lap_number = l1.lap_number + 1 LIMIT 1)
                            AND l2.position < l1.position
                            AND s.session_type = 'R'
                    )
                    SELECT * FROM stint_changes
                    WHERE ($1::int IS NULL OR year = $1)
                    ORDER BY pos_before - pos_after DESC
                    LIMIT $2
                """
                rows = await conn.fetch(query, year, limit)
                results = [{
                    "scenario": "Undercut success",
                    "session": f"{row['year']} {row['event_name']}",
                    "driver": row["driver_id"],
                    "pit_lap": row["pit_lap"],
                    "positions_gained": row["pos_before"] - row["pos_after"],
                } for row in rows]

            # Scenario: One-stop vs two-stop
            elif "one stop" in scenario_lower or "two stop" in scenario_lower:
                query = """
                    SELECT
                        s.year,
                        s.event_name,
                        l.driver_id,
                        MAX(l.stint) as num_stops,
                        r.position as finish_position
                    FROM lap_times l
                    JOIN sessions s ON l.session_id = s.session_id
                    JOIN results r ON l.session_id = r.session_id AND l.driver_id = r.driver_id
                    WHERE s.session_type = 'R'
                        AND ($1::int IS NULL OR s.year = $1)
                    GROUP BY s.year, s.event_name, l.driver_id, l.session_id, r.position
                    HAVING MAX(l.stint) IN (1, 2)
                    ORDER BY r.position
                    LIMIT $2
                """
                rows = await conn.fetch(query, year, limit)
                results = [{
                    "scenario": f"{'One-stop' if row['num_stops'] == 1 else 'Two-stop'} strategy",
                    "session": f"{row['year']} {row['event_name']}",
                    "driver": row["driver_id"],
                    "pit_stops": row["num_stops"] - 1,
                    "finish_position": row["finish_position"],
                } for row in rows]

            # Scenario: Position gains from start
            elif "gained" in scenario_lower or "positions" in scenario_lower or "overtake" in scenario_lower:
                query = """
                    SELECT
                        s.year,
                        s.event_name,
                        r.driver_id,
                        r.grid_position,
                        r.position as finish_position,
                        r.grid_position - r.position as positions_gained
                    FROM results r
                    JOIN sessions s ON r.session_id = s.session_id
                    WHERE s.session_type = 'R'
                        AND r.grid_position > r.position
                        AND ($1::int IS NULL OR s.year = $1)
                    ORDER BY positions_gained DESC
                    LIMIT $2
                """
                rows = await conn.fetch(query, year, limit)
                results = [{
                    "scenario": "Positions gained",
                    "session": f"{row['year']} {row['event_name']}",
                    "driver": row["driver_id"],
                    "started": f"P{row['grid_position']}",
                    "finished": f"P{row['finish_position']}",
                    "positions_gained": row["positions_gained"],
                } for row in rows]

            # Default: Return top race results
            else:
                query = """
                    SELECT
                        s.year,
                        s.event_name,
                        r.driver_id,
                        r.position,
                        r.points
                    FROM results r
                    JOIN sessions s ON r.session_id = s.session_id
                    WHERE s.session_type = 'R'
                        AND r.position <= 3
                        AND ($1::int IS NULL OR s.year = $1)
                    ORDER BY s.year DESC, s.round_number DESC
                    LIMIT $2
                """
                rows = await conn.fetch(query, year, limit)
                results = [{
                    "scenario": "Podium finish",
                    "session": f"{row['year']} {row['event_name']}",
                    "driver": row["driver_id"],
                    "position": row["position"],
                    "points": row["points"],
                } for row in rows]

            if not results:
                return [{"message": f"No matching scenarios found for: {scenario_description}"}]

            return results

    except Exception as e:
        logger.error(f"Similar scenarios search error: {e}")
        return [{"error": str(e)}]


# Export all tools
TIMESCALE_TOOLS = [
    # Original tools (for detailed queries)
    get_lap_times,
    get_driver_stint_summary,
    compare_driver_pace,
    get_tire_degradation,
    get_weather_conditions,
    get_session_results,
    get_available_sessions,
    # Fast tools (materialized views)
    get_head_to_head,
    get_driver_season_summary,
    get_race_summary,
    get_stint_analysis,
    get_season_standings,
    # Advanced query tools
    query_f1_database,
    get_database_schema,
    simulate_pit_strategy,
    find_similar_race_scenarios,
]
