"""
TimescaleDB Tools

Tools for querying F1 telemetry, lap times, and weather data from TimescaleDB.
Includes Redis caching for fast repeated queries.
Includes validation for year ranges, driver participation, and data availability.
"""

import logging

import asyncpg
from langchain_core.tools import tool

from db.cache import cache_get, cache_set, _generate_cache_key, CACHE_TTL
from agent.validation import (
    validate_year,
    validate_driver,
    validate_race_name,
    normalize_driver_id,
    normalize_race_name,
    check_driver_in_result,
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
async def get_pit_stops(
    year: int | None = None,
    event_name: str | None = None,
    driver_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Get pit stop times for races. Calculates actual pit stop duration from lap data.

    PERFECT FOR: "Fastest pit stops", "pit stop times", "who had the best pit stop"

    Args:
        year: Filter by season year (e.g., 2024)
        event_name: Filter by race name (partial match, e.g., "Monaco", "Bahrain")
        driver_id: Filter by driver abbreviation (e.g., "VER", "HAM")
        limit: Maximum results (default 50)

    Returns:
        List of pit stops with duration, lap number, tire compounds, and ranking.
        Pit stop time is calculated as the difference from the average lap time.
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
        # Query to find pit stop laps and calculate pit stop time
        # A pit stop is identified by a stint change
        # Pit stop time = pit lap time - average normal lap time for that driver
        query = """
            WITH normal_laps AS (
                -- Get average lap time per driver per session (excluding pit laps and outliers)
                SELECT
                    lt.session_id,
                    lt.driver_id,
                    AVG(lt.lap_time_seconds) as avg_lap_time
                FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                WHERE lt.lap_time_seconds > 60
                    AND lt.lap_time_seconds < 200
                    AND s.session_type = 'R'
                GROUP BY lt.session_id, lt.driver_id
            ),
            pit_laps AS (
                -- Find laps where stint changes (pit stop occurred)
                SELECT
                    lt.session_id,
                    lt.driver_id,
                    lt.team,
                    lt.lap_number as pit_lap,
                    lt.lap_time_seconds as pit_lap_time,
                    lt.stint as new_stint,
                    LAG(lt.stint) OVER (PARTITION BY lt.session_id, lt.driver_id ORDER BY lt.lap_number) as prev_stint,
                    LAG(lt.compound) OVER (PARTITION BY lt.session_id, lt.driver_id ORDER BY lt.lap_number) as from_compound,
                    lt.compound as to_compound,
                    s.year,
                    s.event_name,
                    s.circuit
                FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND lt.lap_time_seconds IS NOT NULL
        """
        params = []
        param_idx = 1

        if year:
            query += f" AND s.year = ${param_idx}"
            params.append(year)
            param_idx += 1

        if norm_race:
            query += f" AND s.event_name ILIKE ${param_idx}"
            params.append(f"%{norm_race}%")
            param_idx += 1

        if norm_driver:
            query += f" AND lt.driver_id = ${param_idx}"
            params.append(norm_driver)
            param_idx += 1

        query += """
            )
            SELECT
                pl.year,
                pl.event_name as race,
                pl.circuit,
                pl.driver_id,
                pl.team,
                pl.pit_lap,
                pl.from_compound,
                pl.to_compound,
                pl.pit_lap_time,
                nl.avg_lap_time,
                ROUND((pl.pit_lap_time - nl.avg_lap_time)::numeric, 3) as pit_stop_time,
                pl.new_stint as stint_number
            FROM pit_laps pl
            JOIN normal_laps nl ON pl.session_id = nl.session_id AND pl.driver_id = nl.driver_id
            WHERE pl.new_stint != pl.prev_stint
                AND pl.prev_stint IS NOT NULL
                AND pl.pit_lap_time > nl.avg_lap_time  -- Pit lap should be slower
            ORDER BY pit_stop_time ASC
        """

        query += f" LIMIT ${param_idx}"
        params.append(limit)

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "year": row["year"],
                    "race": row["race"],
                    "circuit": row["circuit"],
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "pit_lap": row["pit_lap"],
                    "pit_stop_time_seconds": float(row["pit_stop_time"]) if row["pit_stop_time"] else None,
                    "from_compound": row["from_compound"],
                    "to_compound": row["to_compound"],
                    "stint": row["stint_number"],
                })

        if not results:
            suggestions = ["Try a different year or race", "Check if the race has been loaded into the database"]
            return [{
                "error": "No pit stop data found for the specified criteria",
                "code": "NO_PIT_STOP_DATA",
                "suggestions": suggestions,
                "query_params": {
                    "year": year,
                    "race": norm_race,
                    "driver": norm_driver,
                }
            }]

        return results

    except Exception as e:
        logger.error(f"Error getting pit stops: {e}")
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
            total_laps = max(lap["lap_number"] for lap in laps)

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
            actual_time = sum(lap["lap_time_seconds"] for lap in laps if lap["lap_time_seconds"])
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


# ============================================================
# ADVANCED ANALYTICAL TOOLS (Season-Wide & Field Comparisons)
# ============================================================

@tool
async def get_driver_vs_field(
    driver_ids: list[str],
    year: int,
    metric: str = "pace",
) -> dict:
    """
    Compare specific driver(s) against the rest of the field for a full season.

    PERFECT FOR: "How dominant was X", "X vs the field", "X compared to everyone else"

    Args:
        driver_ids: List of drivers to compare (e.g., ["VER", "HAM"])
        year: Season year
        metric: What to compare - "pace" (avg lap time), "consistency" (std dev),
                "positions" (avg finish), "points_per_race"

    Returns:
        Dict with driver stats, field average, and dominance metrics.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    # Normalize driver IDs
    drivers = [normalize_driver_id(d) for d in driver_ids]

    try:
        async with _pool.acquire() as conn:
            # Get all race sessions for the year
            sessions = await conn.fetch("""
                SELECT session_id, event_name, round_number
                FROM sessions
                WHERE year = $1 AND session_type = 'R'
                ORDER BY round_number
            """, year)

            if not sessions:
                return {"error": f"No race data found for {year}"}

            # Calculate metrics for each driver and the field
            if metric == "pace":
                # Average lap time (excluding pit laps and outliers)
                query = """
                    SELECT
                        driver_id,
                        AVG(lap_time_seconds) as avg_pace,
                        STDDEV(lap_time_seconds) as consistency,
                        COUNT(*) as total_laps,
                        MIN(lap_time_seconds) as best_lap
                    FROM lap_times lt
                    JOIN sessions s ON lt.session_id = s.session_id
                    WHERE s.year = $1
                        AND s.session_type = 'R'
                        AND lt.lap_time_seconds > 60
                        AND lt.lap_time_seconds < 200
                    GROUP BY driver_id
                """
                rows = await conn.fetch(query, year)

            elif metric == "positions":
                query = """
                    SELECT
                        driver_id,
                        AVG(position) as avg_position,
                        MIN(position) as best_finish,
                        COUNT(*) as races,
                        SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) as podiums
                    FROM results r
                    JOIN sessions s ON r.session_id = s.session_id
                    WHERE s.year = $1 AND s.session_type = 'R'
                    GROUP BY driver_id
                """
                rows = await conn.fetch(query, year)

            elif metric == "points_per_race":
                query = """
                    SELECT
                        driver_id,
                        SUM(points) as total_points,
                        COUNT(*) as races,
                        SUM(points) / COUNT(*)::float as points_per_race,
                        SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as wins
                    FROM results r
                    JOIN sessions s ON r.session_id = s.session_id
                    WHERE s.year = $1 AND s.session_type = 'R'
                    GROUP BY driver_id
                """
                rows = await conn.fetch(query, year)
            else:
                return {"error": f"Unknown metric: {metric}. Use 'pace', 'positions', or 'points_per_race'"}

            if not rows:
                return {"error": f"No data found for {year}"}

            # Separate target drivers from field
            all_drivers = {row["driver_id"]: dict(row) for row in rows}

            target_stats = {}
            field_stats = []

            for driver_id, stats in all_drivers.items():
                if driver_id in drivers:
                    target_stats[driver_id] = stats
                else:
                    field_stats.append(stats)

            # Calculate field averages
            if metric == "pace":
                field_avg_pace = sum(d["avg_pace"] for d in field_stats if d["avg_pace"]) / len(field_stats)
                field_avg_consistency = sum(d["consistency"] for d in field_stats if d["consistency"]) / len(field_stats)

                result = {
                    "year": year,
                    "metric": metric,
                    "total_races": len(sessions),
                    "field_average": {
                        "avg_pace": round(field_avg_pace, 3),
                        "avg_consistency": round(field_avg_consistency, 3),
                        "driver_count": len(field_stats),
                    },
                    "target_drivers": {},
                }

                for driver, stats in target_stats.items():
                    pace_gap = stats["avg_pace"] - field_avg_pace if stats["avg_pace"] else None
                    result["target_drivers"][driver] = {
                        "avg_pace": round(stats["avg_pace"], 3) if stats["avg_pace"] else None,
                        "consistency": round(stats["consistency"], 3) if stats["consistency"] else None,
                        "total_laps": stats["total_laps"],
                        "best_lap": round(stats["best_lap"], 3) if stats["best_lap"] else None,
                        "gap_to_field": round(pace_gap, 3) if pace_gap else None,
                        "dominance": "FASTER" if pace_gap and pace_gap < 0 else "SLOWER",
                    }

            elif metric == "positions":
                field_avg_pos = sum(d["avg_position"] for d in field_stats if d["avg_position"]) / len(field_stats)

                result = {
                    "year": year,
                    "metric": metric,
                    "total_races": len(sessions),
                    "field_average": {
                        "avg_position": round(field_avg_pos, 2),
                        "driver_count": len(field_stats),
                    },
                    "target_drivers": {},
                }

                for driver, stats in target_stats.items():
                    pos_gap = stats["avg_position"] - field_avg_pos if stats["avg_position"] else None
                    result["target_drivers"][driver] = {
                        "avg_position": round(stats["avg_position"], 2) if stats["avg_position"] else None,
                        "best_finish": stats["best_finish"],
                        "races": stats["races"],
                        "podiums": stats["podiums"],
                        "gap_to_field": round(pos_gap, 2) if pos_gap else None,
                        "dominance": "BETTER" if pos_gap and pos_gap < 0 else "WORSE",
                    }

            elif metric == "points_per_race":
                field_avg_ppr = sum(d["points_per_race"] for d in field_stats if d["points_per_race"]) / len(field_stats)

                result = {
                    "year": year,
                    "metric": metric,
                    "total_races": len(sessions),
                    "field_average": {
                        "points_per_race": round(field_avg_ppr, 2),
                        "driver_count": len(field_stats),
                    },
                    "target_drivers": {},
                }

                for driver, stats in target_stats.items():
                    ppr_gap = stats["points_per_race"] - field_avg_ppr if stats["points_per_race"] else None
                    result["target_drivers"][driver] = {
                        "total_points": stats["total_points"],
                        "races": stats["races"],
                        "points_per_race": round(stats["points_per_race"], 2) if stats["points_per_race"] else None,
                        "wins": stats["wins"],
                        "gap_to_field": round(ppr_gap, 2) if ppr_gap else None,
                        "dominance": "ABOVE AVERAGE" if ppr_gap and ppr_gap > 0 else "BELOW AVERAGE",
                    }

            return result

    except Exception as e:
        logger.error(f"Error in driver vs field comparison: {e}")
        return {"error": str(e)}


@tool
async def get_season_pace_ranking(
    year: int,
    top_n: int = 20,
) -> list[dict]:
    """
    Get season-wide pace ranking for all drivers in a year.

    PERFECT FOR: "Fastest drivers of 2024", "pace rankings", "who was quickest"

    Args:
        year: Season year
        top_n: Number of drivers to return

    Returns:
        List of drivers ranked by average race pace with stats.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            WITH driver_pace AS (
                SELECT
                    lt.driver_id,
                    r.team,
                    COUNT(DISTINCT lt.session_id) as races,
                    COUNT(*) as total_laps,
                    AVG(lt.lap_time_seconds) as avg_pace,
                    MIN(lt.lap_time_seconds) as best_lap,
                    STDDEV(lt.lap_time_seconds) as consistency,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lt.lap_time_seconds) as median_pace
                FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND lt.lap_time_seconds > 60
                    AND lt.lap_time_seconds < 200
                GROUP BY lt.driver_id, r.team
                HAVING COUNT(DISTINCT lt.session_id) >= 5  -- At least 5 races
            )
            SELECT
                driver_id,
                team,
                races,
                total_laps,
                avg_pace,
                best_lap,
                consistency,
                median_pace,
                RANK() OVER (ORDER BY avg_pace) as pace_rank
            FROM driver_pace
            ORDER BY avg_pace
            LIMIT $2
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, top_n)

            if not rows:
                return [{"error": f"No pace data found for {year}"}]

            # Calculate field average for comparison
            all_paces = [row["avg_pace"] for row in rows if row["avg_pace"]]
            field_avg = sum(all_paces) / len(all_paces) if all_paces else 0

            results = []
            for row in rows:
                gap_to_avg = row["avg_pace"] - field_avg if row["avg_pace"] else None
                results.append({
                    "rank": row["pace_rank"],
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "total_laps": row["total_laps"],
                    "avg_pace_seconds": round(row["avg_pace"], 3) if row["avg_pace"] else None,
                    "best_lap_seconds": round(row["best_lap"], 3) if row["best_lap"] else None,
                    "consistency": round(row["consistency"], 3) if row["consistency"] else None,
                    "median_pace": round(row["median_pace"], 3) if row["median_pace"] else None,
                    "gap_to_field_avg": round(gap_to_avg, 3) if gap_to_avg else None,
                })

            return results

    except Exception as e:
        logger.error(f"Error getting season pace ranking: {e}")
        return [{"error": str(e)}]


@tool
async def get_performance_trend(
    driver_id: str,
    year: int,
    window_size: int = 3,
) -> list[dict]:
    """
    Analyze a driver's performance trend throughout a season.

    PERFECT FOR: "Was X improving?", "performance trend", "getting better or worse"

    Args:
        driver_id: Driver abbreviation (e.g., "VER")
        year: Season year
        window_size: Rolling average window (default 3 races)

    Returns:
        Race-by-race performance with rolling averages and trend indicators.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id)

    try:
        query = """
            SELECT
                s.round_number,
                s.event_name,
                r.position,
                r.grid_position,
                r.points,
                AVG(lt.lap_time_seconds) as avg_pace,
                MIN(lt.lap_time_seconds) as best_lap,
                STDDEV(lt.lap_time_seconds) as consistency
            FROM sessions s
            JOIN results r ON s.session_id = r.session_id
            LEFT JOIN lap_times lt ON s.session_id = lt.session_id AND r.driver_id = lt.driver_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND r.driver_id = $2
                AND (lt.lap_time_seconds IS NULL OR (lt.lap_time_seconds > 60 AND lt.lap_time_seconds < 200))
            GROUP BY s.round_number, s.event_name, r.position, r.grid_position, r.points
            ORDER BY s.round_number
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No data found for {driver} in {year}"}]

            results = []
            positions = []
            paces = []

            for row in rows:
                positions.append(row["position"] if row["position"] else 20)
                if row["avg_pace"]:
                    paces.append(row["avg_pace"])

                # Calculate rolling averages
                rolling_position = None
                rolling_pace = None
                trend = "STABLE"

                if len(positions) >= window_size:
                    recent_positions = positions[-window_size:]
                    rolling_position = sum(recent_positions) / len(recent_positions)

                    # Trend based on comparing first half vs second half of window
                    if len(positions) >= window_size * 2:
                        early = sum(positions[-window_size*2:-window_size]) / window_size
                        late = sum(positions[-window_size:]) / window_size
                        if late < early - 0.5:
                            trend = "IMPROVING"
                        elif late > early + 0.5:
                            trend = "DECLINING"

                if len(paces) >= window_size:
                    recent_paces = paces[-window_size:]
                    rolling_pace = sum(recent_paces) / len(recent_paces)

                results.append({
                    "round": row["round_number"],
                    "race": row["event_name"],
                    "grid": row["grid_position"],
                    "position": row["position"],
                    "points": row["points"],
                    "avg_pace": round(row["avg_pace"], 3) if row["avg_pace"] else None,
                    "best_lap": round(row["best_lap"], 3) if row["best_lap"] else None,
                    "consistency": round(row["consistency"], 3) if row["consistency"] else None,
                    "rolling_avg_position": round(rolling_position, 2) if rolling_position else None,
                    "rolling_avg_pace": round(rolling_pace, 3) if rolling_pace else None,
                    "trend": trend,
                })

            return results

    except Exception as e:
        logger.error(f"Error getting performance trend: {e}")
        return [{"error": str(e)}]


@tool
async def compare_teams(
    team_1: str,
    team_2: str,
    year: int,
) -> dict:
    """
    Compare two teams' performance across a season.

    PERFECT FOR: "Mercedes vs Red Bull", "team comparison", "constructor battle"

    Args:
        team_1: First team name (partial match, e.g., "Red Bull", "Mercedes")
        team_2: Second team name
        year: Season year

    Returns:
        Head-to-head team comparison with pace, points, positions.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    try:
        query = """
            WITH team_stats AS (
                SELECT
                    r.team,
                    COUNT(DISTINCT s.round_number) as races,
                    SUM(r.points) as total_points,
                    AVG(r.position) as avg_position,
                    SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) as podiums,
                    MIN(r.position) as best_finish
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND (r.team ILIKE $2 OR r.team ILIKE $3)
                GROUP BY r.team
            ),
            team_pace AS (
                SELECT
                    r.team,
                    AVG(lt.lap_time_seconds) as avg_pace,
                    MIN(lt.lap_time_seconds) as best_lap,
                    STDDEV(lt.lap_time_seconds) as consistency
                FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND (r.team ILIKE $2 OR r.team ILIKE $3)
                    AND lt.lap_time_seconds > 60
                    AND lt.lap_time_seconds < 200
                GROUP BY r.team
            )
            SELECT
                ts.team,
                ts.races,
                ts.total_points,
                ts.avg_position,
                ts.wins,
                ts.podiums,
                ts.best_finish,
                tp.avg_pace,
                tp.best_lap,
                tp.consistency
            FROM team_stats ts
            LEFT JOIN team_pace tp ON ts.team = tp.team
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, f"%{team_1}%", f"%{team_2}%")

            if len(rows) < 2:
                return {"error": f"Could not find both teams. Found: {[r['team'] for r in rows]}"}

            teams = {}
            for row in rows:
                teams[row["team"]] = {
                    "races": row["races"],
                    "total_points": row["total_points"],
                    "avg_position": round(row["avg_position"], 2) if row["avg_position"] else None,
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "best_finish": row["best_finish"],
                    "avg_pace": round(row["avg_pace"], 3) if row["avg_pace"] else None,
                    "best_lap": round(row["best_lap"], 3) if row["best_lap"] else None,
                    "consistency": round(row["consistency"], 3) if row["consistency"] else None,
                }

            # Calculate deltas
            team_names = list(teams.keys())
            t1, t2 = teams[team_names[0]], teams[team_names[1]]

            return {
                "year": year,
                "teams": teams,
                "comparison": {
                    "points_leader": team_names[0] if (t1["total_points"] or 0) > (t2["total_points"] or 0) else team_names[1],
                    "points_gap": abs((t1["total_points"] or 0) - (t2["total_points"] or 0)),
                    "pace_leader": team_names[0] if (t1["avg_pace"] or 999) < (t2["avg_pace"] or 999) else team_names[1],
                    "pace_gap_seconds": round(abs((t1["avg_pace"] or 0) - (t2["avg_pace"] or 0)), 3) if t1["avg_pace"] and t2["avg_pace"] else None,
                    "more_wins": team_names[0] if (t1["wins"] or 0) > (t2["wins"] or 0) else team_names[1],
                },
            }

    except Exception as e:
        logger.error(f"Error comparing teams: {e}")
        return {"error": str(e)}


@tool
async def get_qualifying_race_delta(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Compare qualifying positions to race finish positions.

    PERFECT FOR: "Who gains most positions", "qualifying vs race", "race craft"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Position delta analysis showing who gains/loses most from grid to finish.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            SELECT
                r.driver_id,
                r.team,
                COUNT(*) as races,
                AVG(r.grid_position) as avg_grid,
                AVG(r.position) as avg_finish,
                AVG(r.grid_position - r.position) as avg_positions_gained,
                SUM(CASE WHEN r.position < r.grid_position THEN 1 ELSE 0 END) as races_gained,
                SUM(CASE WHEN r.position > r.grid_position THEN 1 ELSE 0 END) as races_lost,
                MAX(r.grid_position - r.position) as best_gain,
                MIN(r.grid_position - r.position) as worst_loss
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND r.grid_position IS NOT NULL
                AND r.position IS NOT NULL
                AND ($2::text IS NULL OR r.driver_id = $2)
            GROUP BY r.driver_id, r.team
            HAVING COUNT(*) >= 5  -- At least 5 races
            ORDER BY avg_positions_gained DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No qualifying/race data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "avg_grid_position": round(row["avg_grid"], 1),
                    "avg_finish_position": round(row["avg_finish"], 1),
                    "avg_positions_gained": round(row["avg_positions_gained"], 2),
                    "races_where_gained": row["races_gained"],
                    "races_where_lost": row["races_lost"],
                    "best_single_race_gain": row["best_gain"],
                    "worst_single_race_loss": row["worst_loss"],
                    "race_craft_rating": "EXCELLENT" if row["avg_positions_gained"] > 2 else "GOOD" if row["avg_positions_gained"] > 0 else "POOR",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting qualifying/race delta: {e}")
        return [{"error": str(e)}]


# ============================================================
# MORE ANALYTICAL TOOLS (Specialized Analysis)
# ============================================================

@tool
async def get_overtaking_analysis(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze overtaking and position changes during races.

    PERFECT FOR: "Most overtakes", "who passes the most", "best overtaker"

    Args:
        year: Season year
        event_name: Optional race filter
        driver_id: Optional driver filter

    Returns:
        Overtaking statistics including positions gained, overtakes per race.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Calculate position changes lap-by-lap
        query = """
            WITH lap_positions AS (
                SELECT
                    lt.session_id,
                    lt.driver_id,
                    r.team,
                    lt.lap_number,
                    lt.position,
                    LAG(lt.position) OVER (
                        PARTITION BY lt.session_id, lt.driver_id
                        ORDER BY lt.lap_number
                    ) as prev_position,
                    s.event_name
                FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND lt.position IS NOT NULL
                    AND ($2::text IS NULL OR s.event_name ILIKE $2)
                    AND ($3::text IS NULL OR lt.driver_id = $3)
            ),
            overtakes AS (
                SELECT
                    driver_id,
                    team,
                    session_id,
                    event_name,
                    SUM(CASE WHEN prev_position > position THEN prev_position - position ELSE 0 END) as positions_gained,
                    SUM(CASE WHEN prev_position < position THEN position - prev_position ELSE 0 END) as positions_lost,
                    COUNT(CASE WHEN prev_position > position THEN 1 END) as overtakes_made,
                    COUNT(CASE WHEN prev_position < position THEN 1 END) as times_overtaken
                FROM lap_positions
                WHERE prev_position IS NOT NULL
                GROUP BY driver_id, team, session_id, event_name
            )
            SELECT
                driver_id,
                team,
                COUNT(DISTINCT session_id) as races,
                SUM(positions_gained) as total_positions_gained,
                SUM(positions_lost) as total_positions_lost,
                SUM(positions_gained) - SUM(positions_lost) as net_positions,
                SUM(overtakes_made) as total_overtakes,
                SUM(times_overtaken) as total_times_overtaken,
                ROUND(SUM(overtakes_made)::numeric / COUNT(DISTINCT session_id), 2) as overtakes_per_race
            FROM overtakes
            GROUP BY driver_id, team
            ORDER BY total_overtakes DESC
        """

        async with _pool.acquire() as conn:
            event_filter = f"%{event_name}%" if event_name else None
            rows = await conn.fetch(query, year, event_filter, driver)

            if not rows:
                return [{"error": f"No overtaking data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "total_overtakes": row["total_overtakes"],
                    "times_overtaken": row["total_times_overtaken"],
                    "net_positions_gained": row["net_positions"],
                    "overtakes_per_race": float(row["overtakes_per_race"]) if row["overtakes_per_race"] else 0,
                    "aggression_rating": "AGGRESSIVE" if row["total_overtakes"] > row["total_times_overtaken"] * 1.5 else "BALANCED" if row["total_overtakes"] > row["total_times_overtaken"] else "DEFENSIVE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting overtaking analysis: {e}")
        return [{"error": str(e)}]


@tool
async def get_sector_performance(
    year: int,
    event_name: str | None = None,
    sector: int | None = None,
) -> list[dict]:
    """
    Analyze sector-by-sector performance to find who dominates each sector.

    PERFECT FOR: "Who is fastest in sector 3", "sector dominance", "best sectors"

    Args:
        year: Season year
        event_name: Optional race filter
        sector: Specific sector (1, 2, or 3) or None for all

    Returns:
        Sector performance rankings with best times and consistency.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                lt.driver_id,
                r.team,
                COUNT(DISTINCT lt.session_id) as races,
                AVG(lt.sector_1_seconds) as avg_s1,
                MIN(lt.sector_1_seconds) as best_s1,
                AVG(lt.sector_2_seconds) as avg_s2,
                MIN(lt.sector_2_seconds) as best_s2,
                AVG(lt.sector_3_seconds) as avg_s3,
                MIN(lt.sector_3_seconds) as best_s3,
                RANK() OVER (ORDER BY AVG(lt.sector_1_seconds)) as s1_rank,
                RANK() OVER (ORDER BY AVG(lt.sector_2_seconds)) as s2_rank,
                RANK() OVER (ORDER BY AVG(lt.sector_3_seconds)) as s3_rank
            FROM lap_times lt
            JOIN sessions s ON lt.session_id = s.session_id
            JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND lt.sector_1_seconds > 10 AND lt.sector_1_seconds < 60
                AND lt.sector_2_seconds > 10 AND lt.sector_2_seconds < 60
                AND lt.sector_3_seconds > 10 AND lt.sector_3_seconds < 60
                AND ($2::text IS NULL OR s.event_name ILIKE $2)
            GROUP BY lt.driver_id, r.team
            HAVING COUNT(DISTINCT lt.session_id) >= 3
            ORDER BY (AVG(lt.sector_1_seconds) + AVG(lt.sector_2_seconds) + AVG(lt.sector_3_seconds))
        """

        async with _pool.acquire() as conn:
            event_filter = f"%{event_name}%" if event_name else None
            rows = await conn.fetch(query, year, event_filter)

            if not rows:
                return [{"error": f"No sector data found for {year}"}]

            results = []
            for row in rows:
                result = {
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                }

                if sector is None or sector == 1:
                    result["sector_1"] = {
                        "avg_time": round(row["avg_s1"], 3) if row["avg_s1"] else None,
                        "best_time": round(row["best_s1"], 3) if row["best_s1"] else None,
                        "rank": row["s1_rank"],
                    }
                if sector is None or sector == 2:
                    result["sector_2"] = {
                        "avg_time": round(row["avg_s2"], 3) if row["avg_s2"] else None,
                        "best_time": round(row["best_s2"], 3) if row["best_s2"] else None,
                        "rank": row["s2_rank"],
                    }
                if sector is None or sector == 3:
                    result["sector_3"] = {
                        "avg_time": round(row["avg_s3"], 3) if row["avg_s3"] else None,
                        "best_time": round(row["best_s3"], 3) if row["best_s3"] else None,
                        "rank": row["s3_rank"],
                    }

                # Find best sector for this driver
                ranks = [row["s1_rank"], row["s2_rank"], row["s3_rank"]]
                best_sector = ranks.index(min(ranks)) + 1
                result["strongest_sector"] = f"S{best_sector}"

                results.append(result)

            return results

    except Exception as e:
        logger.error(f"Error getting sector performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_consistency_ranking(
    year: int,
    min_races: int = 10,
) -> list[dict]:
    """
    Rank drivers by consistency (lowest lap time variance).

    PERFECT FOR: "Most consistent driver", "who is most reliable", "least variance"

    Args:
        year: Season year
        min_races: Minimum races to qualify

    Returns:
        Drivers ranked by consistency with variance metrics.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                lt.driver_id,
                r.team,
                COUNT(DISTINCT lt.session_id) as races,
                COUNT(*) as total_laps,
                AVG(lt.lap_time_seconds) as avg_pace,
                STDDEV(lt.lap_time_seconds) as lap_time_stddev,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lt.lap_time_seconds) as median_pace,
                MAX(lt.lap_time_seconds) - MIN(lt.lap_time_seconds) as pace_range,
                -- Coefficient of variation (lower = more consistent)
                STDDEV(lt.lap_time_seconds) / AVG(lt.lap_time_seconds) * 100 as cv_percent
            FROM lap_times lt
            JOIN sessions s ON lt.session_id = s.session_id
            JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND lt.lap_time_seconds > 60
                AND lt.lap_time_seconds < 200
            GROUP BY lt.driver_id, r.team
            HAVING COUNT(DISTINCT lt.session_id) >= $2
            ORDER BY STDDEV(lt.lap_time_seconds)
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, min_races)

            if not rows:
                return [{"error": f"No consistency data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "total_laps": row["total_laps"],
                    "avg_pace": round(row["avg_pace"], 3) if row["avg_pace"] else None,
                    "lap_time_stddev": round(row["lap_time_stddev"], 3) if row["lap_time_stddev"] else None,
                    "coefficient_of_variation": round(row["cv_percent"], 2) if row["cv_percent"] else None,
                    "consistency_rating": "EXCELLENT" if row["lap_time_stddev"] and row["lap_time_stddev"] < 2 else "GOOD" if row["lap_time_stddev"] and row["lap_time_stddev"] < 3 else "AVERAGE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting consistency ranking: {e}")
        return [{"error": str(e)}]


@tool
async def get_reliability_stats(
    year: int,
    by_team: bool = False,
) -> list[dict]:
    """
    Analyze reliability - DNFs, mechanical failures, and finish rate.

    PERFECT FOR: "Most reliable team", "DNF stats", "who retires most", "reliability"

    Args:
        year: Season year
        by_team: If True, group by team instead of driver

    Returns:
        Reliability statistics with DNF counts and finish rates.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        if by_team:
            query = """
                SELECT
                    r.team,
                    COUNT(*) as race_entries,
                    SUM(CASE WHEN r.status = 'Finished' OR r.status LIKE '+%' THEN 1 ELSE 0 END) as finishes,
                    SUM(CASE WHEN r.status NOT IN ('Finished') AND r.status NOT LIKE '+%' THEN 1 ELSE 0 END) as dnfs,
                    SUM(CASE WHEN r.status ILIKE '%engine%' OR r.status ILIKE '%mechanical%' OR r.status ILIKE '%gearbox%' OR r.status ILIKE '%hydraulic%' OR r.status ILIKE '%power%' THEN 1 ELSE 0 END) as mechanical_dnfs,
                    SUM(CASE WHEN r.status ILIKE '%collision%' OR r.status ILIKE '%accident%' OR r.status ILIKE '%crash%' OR r.status ILIKE '%spun%' THEN 1 ELSE 0 END) as crash_dnfs,
                    ROUND(SUM(CASE WHEN r.status = 'Finished' OR r.status LIKE '+%' THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 1) as finish_rate
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
                GROUP BY r.team
                ORDER BY finish_rate DESC
            """
        else:
            query = """
                SELECT
                    r.driver_id,
                    r.team,
                    COUNT(*) as races,
                    SUM(CASE WHEN r.status = 'Finished' OR r.status LIKE '+%' THEN 1 ELSE 0 END) as finishes,
                    SUM(CASE WHEN r.status NOT IN ('Finished') AND r.status NOT LIKE '+%' THEN 1 ELSE 0 END) as dnfs,
                    SUM(CASE WHEN r.status ILIKE '%engine%' OR r.status ILIKE '%mechanical%' OR r.status ILIKE '%gearbox%' OR r.status ILIKE '%hydraulic%' OR r.status ILIKE '%power%' THEN 1 ELSE 0 END) as mechanical_dnfs,
                    SUM(CASE WHEN r.status ILIKE '%collision%' OR r.status ILIKE '%accident%' OR r.status ILIKE '%crash%' OR r.status ILIKE '%spun%' THEN 1 ELSE 0 END) as crash_dnfs,
                    ROUND(SUM(CASE WHEN r.status = 'Finished' OR r.status LIKE '+%' THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 1) as finish_rate
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
                GROUP BY r.driver_id, r.team
                ORDER BY finish_rate DESC, dnfs ASC
            """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year)

            if not rows:
                return [{"error": f"No reliability data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                result = {
                    "rank": i + 1,
                    "races" if not by_team else "race_entries": row["races"] if "races" in row.keys() else row["race_entries"],
                    "finishes": row["finishes"],
                    "dnfs": row["dnfs"],
                    "mechanical_dnfs": row["mechanical_dnfs"],
                    "crash_dnfs": row["crash_dnfs"],
                    "finish_rate_percent": float(row["finish_rate"]) if row["finish_rate"] else 0,
                    "reliability_rating": "EXCELLENT" if row["finish_rate"] and row["finish_rate"] >= 95 else "GOOD" if row["finish_rate"] and row["finish_rate"] >= 85 else "POOR",
                }

                if by_team:
                    result["team"] = row["team"]
                else:
                    result["driver"] = row["driver_id"]
                    result["team"] = row["team"]

                results.append(result)

            return results

    except Exception as e:
        logger.error(f"Error getting reliability stats: {e}")
        return [{"error": str(e)}]


@tool
async def get_wet_weather_performance(
    year: int | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze driver performance in wet/changing conditions.

    PERFECT FOR: "Best in the rain", "wet weather specialist", "rain master"

    Args:
        year: Optional season filter
        driver_id: Optional driver filter

    Returns:
        Wet weather performance with position gains vs dry races.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Find races with rainfall/wet conditions
        query = """
            WITH wet_races AS (
                SELECT DISTINCT s.session_id, s.event_name, s.year
                FROM sessions s
                JOIN weather w ON s.session_id = w.session_id
                WHERE w.rainfall = true
                    AND s.session_type = 'R'
                    AND ($1::int IS NULL OR s.year = $1)
            ),
            wet_performance AS (
                SELECT
                    r.driver_id,
                    r.team,
                    wr.year,
                    wr.event_name,
                    r.grid_position,
                    r.position as finish_position,
                    r.grid_position - r.position as positions_gained
                FROM results r
                JOIN wet_races wr ON r.session_id = wr.session_id
                WHERE r.position IS NOT NULL AND r.grid_position IS NOT NULL
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            dry_performance AS (
                SELECT
                    r.driver_id,
                    AVG(r.grid_position - r.position) as avg_dry_gain
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND r.session_id NOT IN (SELECT session_id FROM wet_races)
                    AND r.position IS NOT NULL AND r.grid_position IS NOT NULL
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
                GROUP BY r.driver_id
            )
            SELECT
                wp.driver_id,
                wp.team,
                COUNT(*) as wet_races,
                AVG(wp.positions_gained) as avg_wet_gain,
                MAX(wp.positions_gained) as best_wet_gain,
                dp.avg_dry_gain,
                AVG(wp.positions_gained) - COALESCE(dp.avg_dry_gain, 0) as wet_advantage,
                AVG(wp.finish_position) as avg_wet_finish
            FROM wet_performance wp
            LEFT JOIN dry_performance dp ON wp.driver_id = dp.driver_id
            GROUP BY wp.driver_id, wp.team, dp.avg_dry_gain
            HAVING COUNT(*) >= 2
            ORDER BY avg_wet_gain DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": "No wet weather race data found", "note": "This requires races with rainfall=true in weather data"}]

            results = []
            for i, row in enumerate(rows):
                wet_advantage = row["wet_advantage"] if row["wet_advantage"] else 0
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "wet_races": row["wet_races"],
                    "avg_positions_gained_wet": round(row["avg_wet_gain"], 2) if row["avg_wet_gain"] else 0,
                    "best_wet_race_gain": row["best_wet_gain"],
                    "avg_positions_gained_dry": round(row["avg_dry_gain"], 2) if row["avg_dry_gain"] else 0,
                    "wet_vs_dry_advantage": round(wet_advantage, 2),
                    "avg_wet_finish_position": round(row["avg_wet_finish"], 1) if row["avg_wet_finish"] else None,
                    "rain_master_rating": "RAIN MASTER" if wet_advantage > 2 else "WET SPECIALIST" if wet_advantage > 0.5 else "NEUTRAL" if wet_advantage > -0.5 else "STRUGGLES IN WET",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting wet weather performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_lap1_performance(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze first lap performance - positions gained/lost on lap 1.

    PERFECT FOR: "Best starter", "lap 1 gains", "first lap performance"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Lap 1 performance with positions gained and start analysis.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH lap1_positions AS (
                SELECT
                    lt.session_id,
                    lt.driver_id,
                    r.team,
                    r.grid_position,
                    lt.position as lap1_position,
                    r.grid_position - lt.position as lap1_gain
                FROM lap_times lt
                JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
                JOIN sessions s ON lt.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND lt.lap_number = 1
                    AND lt.position IS NOT NULL
                    AND r.grid_position IS NOT NULL
                    AND ($2::text IS NULL OR lt.driver_id = $2)
            )
            SELECT
                driver_id,
                team,
                COUNT(*) as races,
                AVG(lap1_gain) as avg_lap1_gain,
                SUM(CASE WHEN lap1_gain > 0 THEN 1 ELSE 0 END) as races_gained,
                SUM(CASE WHEN lap1_gain < 0 THEN 1 ELSE 0 END) as races_lost,
                SUM(CASE WHEN lap1_gain = 0 THEN 1 ELSE 0 END) as races_held,
                MAX(lap1_gain) as best_lap1_gain,
                MIN(lap1_gain) as worst_lap1_loss,
                SUM(lap1_gain) as total_positions_lap1
            FROM lap1_positions
            GROUP BY driver_id, team
            ORDER BY avg_lap1_gain DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No lap 1 data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                avg_gain = row["avg_lap1_gain"] if row["avg_lap1_gain"] else 0
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "avg_lap1_positions_gained": round(avg_gain, 2),
                    "total_positions_gained_lap1": row["total_positions_lap1"],
                    "races_where_gained": row["races_gained"],
                    "races_where_lost": row["races_lost"],
                    "races_held_position": row["races_held"],
                    "best_lap1_gain": row["best_lap1_gain"],
                    "worst_lap1_loss": row["worst_lap1_loss"],
                    "start_rating": "ROCKET START" if avg_gain > 1 else "GOOD STARTER" if avg_gain > 0.3 else "AVERAGE" if avg_gain > -0.3 else "SLOW STARTER",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting lap 1 performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_fastest_lap_stats(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze fastest lap frequency and race pace excellence.

    PERFECT FOR: "Most fastest laps", "who sets fastest laps", "pace kings"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Fastest lap statistics with frequency and context.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH race_fastest AS (
                SELECT
                    lt.session_id,
                    lt.driver_id,
                    r.team,
                    MIN(lt.lap_time_seconds) as fastest_lap,
                    s.event_name
                FROM lap_times lt
                JOIN sessions s ON lt.session_id = s.session_id
                JOIN results r ON lt.session_id = r.session_id AND lt.driver_id = r.driver_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND lt.lap_time_seconds > 60
                    AND lt.lap_time_seconds < 200
                    AND ($2::text IS NULL OR lt.driver_id = $2)
                GROUP BY lt.session_id, lt.driver_id, r.team, s.event_name
            ),
            session_fastest AS (
                SELECT
                    session_id,
                    MIN(fastest_lap) as race_fastest_lap
                FROM race_fastest
                GROUP BY session_id
            )
            SELECT
                rf.driver_id,
                rf.team,
                COUNT(DISTINCT rf.session_id) as races,
                SUM(CASE WHEN rf.fastest_lap = sf.race_fastest_lap THEN 1 ELSE 0 END) as fastest_laps_count,
                ROUND(SUM(CASE WHEN rf.fastest_lap = sf.race_fastest_lap THEN 1 ELSE 0 END)::numeric / COUNT(DISTINCT rf.session_id) * 100, 1) as fastest_lap_rate,
                MIN(rf.fastest_lap) as absolute_best_lap,
                AVG(rf.fastest_lap) as avg_best_lap
            FROM race_fastest rf
            JOIN session_fastest sf ON rf.session_id = sf.session_id
            GROUP BY rf.driver_id, rf.team
            ORDER BY fastest_laps_count DESC, avg_best_lap ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No fastest lap data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "fastest_laps_achieved": row["fastest_laps_count"],
                    "fastest_lap_rate_percent": float(row["fastest_lap_rate"]) if row["fastest_lap_rate"] else 0,
                    "absolute_best_lap_seconds": round(row["absolute_best_lap"], 3) if row["absolute_best_lap"] else None,
                    "avg_personal_best_seconds": round(row["avg_best_lap"], 3) if row["avg_best_lap"] else None,
                    "pace_rating": "PACE KING" if row["fastest_laps_count"] >= 5 else "FAST" if row["fastest_laps_count"] >= 2 else "OCCASIONAL" if row["fastest_laps_count"] >= 1 else "NONE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting fastest lap stats: {e}")
        return [{"error": str(e)}]


@tool
async def get_teammate_battle(
    year: int,
    team: str | None = None,
) -> list[dict]:
    """
    Comprehensive season-long teammate comparison.

    PERFECT FOR: "Teammate battle", "intra-team comparison", "who beat their teammate"

    Args:
        year: Season year
        team: Optional team filter

    Returns:
        Detailed teammate head-to-head with quali, race, and points battles.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            WITH team_drivers AS (
                SELECT DISTINCT
                    r.team,
                    r.driver_id,
                    r.driver_name
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
                    AND ($2::text IS NULL OR r.team ILIKE $2)
            ),
            race_results AS (
                SELECT
                    r.session_id,
                    r.team,
                    r.driver_id,
                    r.position,
                    r.grid_position,
                    r.points,
                    s.event_name
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
                    AND ($2::text IS NULL OR r.team ILIKE $2)
            ),
            head_to_head AS (
                SELECT
                    r1.team,
                    r1.driver_id as driver_1,
                    r2.driver_id as driver_2,
                    COUNT(*) as races_together,
                    SUM(CASE WHEN r1.position < r2.position THEN 1 ELSE 0 END) as d1_race_wins,
                    SUM(CASE WHEN r2.position < r1.position THEN 1 ELSE 0 END) as d2_race_wins,
                    SUM(CASE WHEN r1.grid_position < r2.grid_position THEN 1 ELSE 0 END) as d1_quali_wins,
                    SUM(CASE WHEN r2.grid_position < r1.grid_position THEN 1 ELSE 0 END) as d2_quali_wins,
                    SUM(r1.points) as d1_points,
                    SUM(r2.points) as d2_points,
                    AVG(r1.position) as d1_avg_pos,
                    AVG(r2.position) as d2_avg_pos
                FROM race_results r1
                JOIN race_results r2 ON r1.session_id = r2.session_id
                    AND r1.team = r2.team
                    AND r1.driver_id < r2.driver_id
                GROUP BY r1.team, r1.driver_id, r2.driver_id
            )
            SELECT * FROM head_to_head
            ORDER BY races_together DESC
        """

        async with _pool.acquire() as conn:
            team_filter = f"%{team}%" if team else None
            rows = await conn.fetch(query, year, team_filter)

            if not rows:
                return [{"error": f"No teammate battle data found for {year}"}]

            results = []
            for row in rows:
                d1_wins = row["d1_race_wins"] or 0
                d2_wins = row["d2_race_wins"] or 0
                d1_quali = row["d1_quali_wins"] or 0
                d2_quali = row["d2_quali_wins"] or 0

                race_winner = row["driver_1"] if d1_wins > d2_wins else row["driver_2"] if d2_wins > d1_wins else "TIE"
                quali_winner = row["driver_1"] if d1_quali > d2_quali else row["driver_2"] if d2_quali > d1_quali else "TIE"
                points_winner = row["driver_1"] if (row["d1_points"] or 0) > (row["d2_points"] or 0) else row["driver_2"]

                results.append({
                    "team": row["team"],
                    "driver_1": row["driver_1"],
                    "driver_2": row["driver_2"],
                    "races_together": row["races_together"],
                    "qualifying_battle": {
                        row["driver_1"]: d1_quali,
                        row["driver_2"]: d2_quali,
                        "winner": quali_winner,
                    },
                    "race_battle": {
                        row["driver_1"]: d1_wins,
                        row["driver_2"]: d2_wins,
                        "winner": race_winner,
                    },
                    "points": {
                        row["driver_1"]: row["d1_points"] or 0,
                        row["driver_2"]: row["d2_points"] or 0,
                        "winner": points_winner,
                        "gap": abs((row["d1_points"] or 0) - (row["d2_points"] or 0)),
                    },
                    "avg_finish": {
                        row["driver_1"]: round(row["d1_avg_pos"], 1) if row["d1_avg_pos"] else None,
                        row["driver_2"]: round(row["d2_avg_pos"], 1) if row["d2_avg_pos"] else None,
                    },
                    "overall_winner": race_winner if race_winner != "TIE" else points_winner,
                    "dominance": "DOMINANT" if abs(d1_wins - d2_wins) > row["races_together"] * 0.3 else "CLOSE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting teammate battle: {e}")
        return [{"error": str(e)}]


@tool
async def get_points_finish_rate(
    year: int,
) -> list[dict]:
    """
    Analyze what percentage of races each driver scores points.

    PERFECT FOR: "Points percentage", "scoring rate", "most consistent scorer"

    Args:
        year: Season year

    Returns:
        Points finish rate with podium and win percentages.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                r.driver_id,
                r.team,
                COUNT(*) as races,
                SUM(CASE WHEN r.points > 0 THEN 1 ELSE 0 END) as points_finishes,
                SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) as podiums,
                SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) as wins,
                SUM(r.points) as total_points,
                ROUND(SUM(CASE WHEN r.points > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 1) as points_rate,
                ROUND(SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 1) as podium_rate,
                ROUND(SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 1) as win_rate,
                AVG(r.points) as avg_points_per_race
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.year = $1 AND s.session_type = 'R'
            GROUP BY r.driver_id, r.team
            HAVING COUNT(*) >= 5
            ORDER BY points_rate DESC, total_points DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year)

            if not rows:
                return [{"error": f"No points data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "points_finishes": row["points_finishes"],
                    "points_rate_percent": float(row["points_rate"]) if row["points_rate"] else 0,
                    "podiums": row["podiums"],
                    "podium_rate_percent": float(row["podium_rate"]) if row["podium_rate"] else 0,
                    "wins": row["wins"],
                    "win_rate_percent": float(row["win_rate"]) if row["win_rate"] else 0,
                    "total_points": row["total_points"],
                    "avg_points_per_race": round(row["avg_points_per_race"], 1) if row["avg_points_per_race"] else 0,
                    "scoring_tier": "ELITE" if row["points_rate"] and row["points_rate"] >= 80 else "CONSISTENT" if row["points_rate"] and row["points_rate"] >= 50 else "OCCASIONAL" if row["points_rate"] and row["points_rate"] >= 25 else "RARE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting points finish rate: {e}")
        return [{"error": str(e)}]


# ============================================================
# CIRCUIT & HISTORICAL TOOLS
# ============================================================

@tool
async def get_track_specialist(
    event_name: str,
    year: int | None = None,
    top_n: int = 10,
) -> list[dict]:
    """
    Find which drivers perform best at a specific circuit.

    PERFECT FOR: "Who is best at Monaco?", "Silverstone specialist", "track record"

    Args:
        event_name: Circuit/race name (e.g., "Monaco", "Silverstone", "Spa")
        year: Optional year filter (if None, looks at all available years)
        top_n: Number of drivers to return

    Returns:
        Drivers ranked by performance at this circuit.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name)

    try:
        query = """
            WITH circuit_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.year,
                    r.position,
                    r.points,
                    r.grid_position,
                    r.grid_position - r.position as positions_gained
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND LOWER(s.event_name) LIKE LOWER($1)
                    AND ($2::int IS NULL OR s.year = $2)
                    AND r.position IS NOT NULL
            ),
            driver_stats AS (
                SELECT
                    driver_id,
                    COUNT(*) as races,
                    SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) as podiums,
                    AVG(position) as avg_finish,
                    AVG(grid_position) as avg_grid,
                    AVG(positions_gained) as avg_gained,
                    SUM(points) as total_points,
                    MIN(position) as best_finish,
                    array_agg(DISTINCT team ORDER BY team) as teams
                FROM circuit_results
                GROUP BY driver_id
                HAVING COUNT(*) >= 1
            )
            SELECT *,
                   RANK() OVER (ORDER BY avg_finish ASC) as performance_rank
            FROM driver_stats
            ORDER BY avg_finish ASC
            LIMIT $3
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, f"%{event}%", year, top_n)

            if not rows:
                return [{"error": f"No data found for {event_name}"}]

            results = []
            for row in rows:
                win_pct = (row["wins"] / row["races"] * 100) if row["races"] > 0 else 0
                podium_pct = (row["podiums"] / row["races"] * 100) if row["races"] > 0 else 0

                results.append({
                    "rank": row["performance_rank"],
                    "driver": row["driver_id"],
                    "teams": row["teams"],
                    "races_at_circuit": row["races"],
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "best_finish": f"P{row['best_finish']}",
                    "avg_finish": round(row["avg_finish"], 2),
                    "avg_grid": round(row["avg_grid"], 2) if row["avg_grid"] else None,
                    "avg_positions_gained": round(row["avg_gained"], 2) if row["avg_gained"] else 0,
                    "total_points": row["total_points"] or 0,
                    "win_rate_percent": round(win_pct, 1),
                    "podium_rate_percent": round(podium_pct, 1),
                    "specialist_rating": "KING" if win_pct >= 40 else "SPECIALIST" if podium_pct >= 50 else "STRONG" if row["avg_finish"] <= 5 else "AVERAGE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting track specialist: {e}")
        return [{"error": str(e)}]


@tool
async def get_championship_evolution(
    year: int,
    driver_ids: list[str] | None = None,
) -> dict:
    """
    Track championship points evolution throughout a season.

    PERFECT FOR: "Points gap over season", "championship battle", "when did X clinch title"

    Args:
        year: Season year
        driver_ids: Optional list of drivers to focus on (otherwise top 5)

    Returns:
        Race-by-race cumulative points and gaps.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    drivers = [normalize_driver_id(d) for d in driver_ids] if driver_ids else None

    try:
        query = """
            WITH race_points AS (
                SELECT
                    r.driver_id,
                    s.round_number,
                    s.event_name,
                    r.points,
                    SUM(r.points) OVER (
                        PARTITION BY r.driver_id
                        ORDER BY s.round_number
                    ) as cumulative_points
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
            ),
            top_drivers AS (
                SELECT driver_id
                FROM race_points
                GROUP BY driver_id
                ORDER BY MAX(cumulative_points) DESC
                LIMIT 5
            ),
            filtered_points AS (
                SELECT rp.*
                FROM race_points rp
                WHERE ($2::text[] IS NULL AND rp.driver_id IN (SELECT driver_id FROM top_drivers))
                   OR (rp.driver_id = ANY($2::text[]))
            )
            SELECT *
            FROM filtered_points
            ORDER BY round_number, cumulative_points DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, drivers)

            if not rows:
                return {"error": f"No championship data found for {year}"}

            # Organize by round
            rounds = {}
            all_drivers = set()
            for row in rows:
                rnd = row["round_number"]
                if rnd not in rounds:
                    rounds[rnd] = {"round": rnd, "event": row["event_name"], "standings": {}}
                rounds[rnd]["standings"][row["driver_id"]] = {
                    "points": row["cumulative_points"],
                    "race_points": row["points"],
                }
                all_drivers.add(row["driver_id"])

            # Calculate gaps and leader
            evolution = []
            for rnd in sorted(rounds.keys()):
                round_data = rounds[rnd]
                standings = round_data["standings"]

                # Find leader
                leader = max(standings.items(), key=lambda x: x[1]["points"])
                leader_driver, leader_data = leader

                round_entry = {
                    "round": rnd,
                    "event": round_data["event"],
                    "leader": leader_driver,
                    "leader_points": leader_data["points"],
                    "drivers": {},
                }

                for driver, data in sorted(standings.items(), key=lambda x: -x[1]["points"]):
                    gap_to_leader = leader_data["points"] - data["points"]
                    round_entry["drivers"][driver] = {
                        "cumulative_points": data["points"],
                        "race_points": data["race_points"],
                        "gap_to_leader": gap_to_leader,
                    }

                evolution.append(round_entry)

            # Find title clinch point if applicable
            final_round = evolution[-1] if evolution else None
            title_clinched = None
            if final_round:
                final_standings = sorted(
                    final_round["drivers"].items(),
                    key=lambda x: -x[1]["cumulative_points"]
                )
                if len(final_standings) >= 2:
                    champion = final_standings[0][0]
                    runner_up_points = final_standings[1][1]["cumulative_points"]
                    remaining_races = 24 - final_round["round"]
                    max_remaining = remaining_races * 26  # Max points per race

                    # Find when title was mathematically secured
                    for entry in evolution:
                        champ_data = entry["drivers"].get(champion)
                        if champ_data:
                            gap = champ_data["cumulative_points"] - max(
                                d["cumulative_points"] for drv, d in entry["drivers"].items() if drv != champion
                            )
                            remaining = (24 - entry["round"]) * 26
                            if gap > remaining:
                                title_clinched = {
                                    "round": entry["round"],
                                    "event": entry["event"],
                                    "champion": champion,
                                    "gap": gap,
                                }
                                break

            return {
                "year": year,
                "evolution": evolution,
                "total_rounds": len(evolution),
                "drivers_tracked": list(all_drivers),
                "title_clinched": title_clinched,
                "final_champion": evolution[-1]["leader"] if evolution else None,
            }

    except Exception as e:
        logger.error(f"Error getting championship evolution: {e}")
        return {"error": str(e)}


@tool
async def get_career_stats(
    driver_id: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict:
    """
    Get comprehensive career statistics for a driver across multiple seasons.

    PERFECT FOR: "All-time wins", "career poles", "total points", "championship titles"

    Args:
        driver_id: Driver code (e.g., "VER", "HAM")
        start_year: Optional start year filter
        end_year: Optional end year filter

    Returns:
        Career aggregates: wins, poles, podiums, points, championships.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    driver = normalize_driver_id(driver_id)

    try:
        query = """
            WITH career AS (
                SELECT
                    r.driver_id,
                    s.year,
                    r.position,
                    r.points,
                    r.grid_position,
                    r.fastest_lap,
                    s.session_type,
                    r.team
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE r.driver_id = $1
                    AND ($2::int IS NULL OR s.year >= $2)
                    AND ($3::int IS NULL OR s.year <= $3)
            ),
            race_stats AS (
                SELECT
                    COUNT(*) as races,
                    SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) as podiums,
                    SUM(CASE WHEN position <= 10 THEN 1 ELSE 0 END) as points_finishes,
                    SUM(points) as total_points,
                    SUM(CASE WHEN fastest_lap = true THEN 1 ELSE 0 END) as fastest_laps,
                    AVG(position) as avg_finish,
                    MIN(position) as best_finish,
                    COUNT(DISTINCT year) as seasons,
                    MIN(year) as first_season,
                    MAX(year) as latest_season,
                    array_agg(DISTINCT team ORDER BY team) as teams
                FROM career
                WHERE session_type = 'R'
            ),
            quali_stats AS (
                SELECT
                    SUM(CASE WHEN grid_position = 1 THEN 1 ELSE 0 END) as poles,
                    AVG(grid_position) as avg_grid,
                    SUM(CASE WHEN grid_position <= 3 THEN 1 ELSE 0 END) as front_row_starts
                FROM career
                WHERE session_type = 'R' AND grid_position IS NOT NULL
            ),
            season_results AS (
                SELECT
                    year,
                    SUM(points) as season_points,
                    RANK() OVER (ORDER BY SUM(points) DESC) as best_season_rank
                FROM career
                WHERE session_type = 'R'
                GROUP BY year
            )
            SELECT
                rs.*,
                qs.poles,
                qs.avg_grid,
                qs.front_row_starts,
                (SELECT COUNT(*) FROM season_results WHERE best_season_rank = 1) as championship_worthy_seasons
            FROM race_stats rs, quali_stats qs
        """

        async with _pool.acquire() as conn:
            row = await conn.fetchrow(query, driver, start_year, end_year)

            if not row or row["races"] == 0:
                return {"error": f"No career data found for {driver_id}"}

            # Get season-by-season breakdown
            season_query = """
                SELECT
                    s.year,
                    COUNT(*) as races,
                    SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) as podiums,
                    SUM(r.points) as points,
                    r.team
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE r.driver_id = $1
                    AND s.session_type = 'R'
                    AND ($2::int IS NULL OR s.year >= $2)
                    AND ($3::int IS NULL OR s.year <= $3)
                GROUP BY s.year, r.team
                ORDER BY s.year DESC
            """
            seasons = await conn.fetch(season_query, driver, start_year, end_year)

            return {
                "driver": driver,
                "career_summary": {
                    "seasons": row["seasons"],
                    "first_season": row["first_season"],
                    "latest_season": row["latest_season"],
                    "teams": row["teams"],
                    "races": row["races"],
                },
                "race_stats": {
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "points_finishes": row["points_finishes"],
                    "total_points": row["total_points"] or 0,
                    "fastest_laps": row["fastest_laps"],
                    "avg_finish": round(row["avg_finish"], 2) if row["avg_finish"] else None,
                    "best_finish": f"P{row['best_finish']}" if row["best_finish"] else None,
                    "win_rate_percent": round(row["wins"] / row["races"] * 100, 1) if row["races"] > 0 else 0,
                    "podium_rate_percent": round(row["podiums"] / row["races"] * 100, 1) if row["races"] > 0 else 0,
                },
                "qualifying_stats": {
                    "poles": row["poles"] or 0,
                    "front_row_starts": row["front_row_starts"] or 0,
                    "avg_grid": round(row["avg_grid"], 2) if row["avg_grid"] else None,
                    "pole_rate_percent": round((row["poles"] or 0) / row["races"] * 100, 1) if row["races"] > 0 else 0,
                },
                "seasons": [{
                    "year": s["year"],
                    "team": s["team"],
                    "races": s["races"],
                    "wins": s["wins"],
                    "podiums": s["podiums"],
                    "points": s["points"] or 0,
                } for s in seasons],
                "legacy_tier": "LEGEND" if row["wins"] >= 50 else "ELITE" if row["wins"] >= 20 else "RACE_WINNER" if row["wins"] >= 1 else "COMPETITOR",
            }

    except Exception as e:
        logger.error(f"Error getting career stats: {e}")
        return {"error": str(e)}


@tool
async def get_qualifying_stats(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze qualifying performance - poles, front row starts, average grid.

    PERFECT FOR: "Most poles", "qualifying specialist", "average grid position"

    Args:
        year: Season year
        driver_id: Optional specific driver filter

    Returns:
        Qualifying statistics ranked by average grid position.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            SELECT
                r.driver_id,
                r.team,
                COUNT(*) as sessions,
                SUM(CASE WHEN r.grid_position = 1 THEN 1 ELSE 0 END) as poles,
                SUM(CASE WHEN r.grid_position <= 3 THEN 1 ELSE 0 END) as front_row,
                SUM(CASE WHEN r.grid_position <= 10 THEN 1 ELSE 0 END) as top_10,
                AVG(r.grid_position) as avg_grid,
                MIN(r.grid_position) as best_grid,
                MAX(r.grid_position) as worst_grid,
                STDDEV(r.grid_position) as grid_consistency
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND r.grid_position IS NOT NULL
                AND ($2::text IS NULL OR r.driver_id = $2)
            GROUP BY r.driver_id, r.team
            HAVING COUNT(*) >= 3
            ORDER BY AVG(r.grid_position) ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No qualifying data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                pole_pct = (row["poles"] / row["sessions"] * 100) if row["sessions"] > 0 else 0
                front_row_pct = (row["front_row"] / row["sessions"] * 100) if row["sessions"] > 0 else 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "sessions": row["sessions"],
                    "poles": row["poles"],
                    "front_row_starts": row["front_row"],
                    "top_10_starts": row["top_10"],
                    "avg_grid": round(row["avg_grid"], 2),
                    "best_grid": f"P{row['best_grid']}",
                    "worst_grid": f"P{row['worst_grid']}",
                    "consistency": round(row["grid_consistency"], 2) if row["grid_consistency"] else 0,
                    "pole_rate_percent": round(pole_pct, 1),
                    "front_row_rate_percent": round(front_row_pct, 1),
                    "quali_tier": "ELITE" if row["avg_grid"] <= 3 else "STRONG" if row["avg_grid"] <= 6 else "MIDFIELD" if row["avg_grid"] <= 12 else "BACKMARKER",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting qualifying stats: {e}")
        return [{"error": str(e)}]


@tool
async def get_podium_stats(
    year: int | None = None,
    driver_id: str | None = None,
    top_n: int = 20,
) -> list[dict]:
    """
    Analyze podium statistics - counts, percentages, streaks.

    PERFECT FOR: "Most podiums", "podium percentage", "podium streak"

    Args:
        year: Optional year filter (if None, career stats)
        driver_id: Optional specific driver filter
        top_n: Number of results to return

    Returns:
        Podium statistics ranked by count or percentage.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH podium_data AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.year,
                    s.event_name,
                    r.position,
                    CASE WHEN r.position <= 3 THEN 1 ELSE 0 END as is_podium,
                    CASE WHEN r.position = 1 THEN 1 ELSE 0 END as is_win,
                    CASE WHEN r.position = 2 THEN 1 ELSE 0 END as is_p2,
                    CASE WHEN r.position = 3 THEN 1 ELSE 0 END as is_p3
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND r.position IS NOT NULL
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
            )
            SELECT
                driver_id,
                array_agg(DISTINCT team ORDER BY team) as teams,
                COUNT(*) as races,
                SUM(is_podium) as podiums,
                SUM(is_win) as wins,
                SUM(is_p2) as p2s,
                SUM(is_p3) as p3s,
                ROUND(SUM(is_podium)::numeric / COUNT(*) * 100, 1) as podium_rate,
                ROUND(SUM(is_win)::numeric / COUNT(*) * 100, 1) as win_rate,
                MIN(year) as first_year,
                MAX(year) as last_year
            FROM podium_data
            GROUP BY driver_id
            HAVING SUM(is_podium) > 0
            ORDER BY SUM(is_podium) DESC, podium_rate DESC
            LIMIT $3
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver, top_n)

            if not rows:
                return [{"error": "No podium data found"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "teams": row["teams"],
                    "period": f"{row['first_year']}-{row['last_year']}" if row["first_year"] != row["last_year"] else str(row["first_year"]),
                    "races": row["races"],
                    "podiums": row["podiums"],
                    "wins": row["wins"],
                    "p2_finishes": row["p2s"],
                    "p3_finishes": row["p3s"],
                    "podium_rate_percent": float(row["podium_rate"]) if row["podium_rate"] else 0,
                    "win_rate_percent": float(row["win_rate"]) if row["win_rate"] else 0,
                    "win_to_podium_ratio": round(row["wins"] / row["podiums"], 2) if row["podiums"] > 0 else 0,
                    "podium_tier": "DOMINANT" if row["podium_rate"] and row["podium_rate"] >= 50 else "ELITE" if row["podium_rate"] and row["podium_rate"] >= 25 else "REGULAR" if row["podiums"] >= 10 else "OCCASIONAL",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting podium stats: {e}")
        return [{"error": str(e)}]


@tool
async def get_race_dominance(
    year: int,
    event_name: str | None = None,
) -> list[dict]:
    """
    Analyze race dominance - winning margins, laps led, dominant victories.

    PERFECT FOR: "Biggest winning margin", "laps led", "dominant victories"

    Args:
        year: Season year
        event_name: Optional specific race filter

    Returns:
        Race dominance statistics showing margins and control.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name) if event_name else None

    try:
        # Query for race results with gaps
        query = """
            WITH race_results AS (
                SELECT
                    s.event_name,
                    s.round_number,
                    r.driver_id,
                    r.team,
                    r.position,
                    r.time_or_gap,
                    r.laps_completed,
                    r.grid_position,
                    LAG(r.time_or_gap) OVER (PARTITION BY s.session_id ORDER BY r.position) as prev_time
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR LOWER(s.event_name) LIKE LOWER('%' || $2 || '%'))
                ORDER BY s.round_number, r.position
            ),
            winners AS (
                SELECT
                    event_name,
                    round_number,
                    driver_id as winner,
                    team,
                    grid_position,
                    laps_completed
                FROM race_results
                WHERE position = 1
            ),
            runner_ups AS (
                SELECT
                    event_name,
                    time_or_gap as gap_to_winner
                FROM race_results
                WHERE position = 2
            )
            SELECT
                w.round_number,
                w.event_name,
                w.winner,
                w.team,
                w.grid_position as start_position,
                w.laps_completed,
                r.gap_to_winner
            FROM winners w
            LEFT JOIN runner_ups r ON w.event_name = r.event_name
            ORDER BY w.round_number
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event)

            if not rows:
                return [{"error": f"No race data found for {year}"}]

            results = []
            for row in rows:
                # Parse gap if available
                gap_str = row["gap_to_winner"] or "Unknown"
                gap_seconds = None
                if gap_str and "+" in str(gap_str):
                    try:
                        gap_seconds = float(str(gap_str).replace("+", "").replace("s", ""))
                    except ValueError:
                        pass

                dominance_rating = "UNKNOWN"
                if gap_seconds:
                    if gap_seconds >= 20:
                        dominance_rating = "CRUSHING"
                    elif gap_seconds >= 10:
                        dominance_rating = "DOMINANT"
                    elif gap_seconds >= 5:
                        dominance_rating = "COMFORTABLE"
                    else:
                        dominance_rating = "CLOSE"

                results.append({
                    "round": row["round_number"],
                    "race": row["event_name"],
                    "winner": row["winner"],
                    "team": row["team"],
                    "started": f"P{row['start_position']}" if row["start_position"] else "?",
                    "laps": row["laps_completed"],
                    "winning_margin": gap_str,
                    "margin_seconds": gap_seconds,
                    "dominance_rating": dominance_rating,
                    "led_from_start": row["start_position"] == 1 if row["start_position"] else False,
                })

            # Summary stats
            total_races = len(results)
            crushing_wins = sum(1 for r in results if r["dominance_rating"] == "CRUSHING")
            dominant_wins = sum(1 for r in results if r["dominance_rating"] == "DOMINANT")
            led_from_start = sum(1 for r in results if r["led_from_start"])

            return {
                "year": year,
                "races": results,
                "summary": {
                    "total_races": total_races,
                    "crushing_victories": crushing_wins,
                    "dominant_victories": dominant_wins,
                    "led_from_start": led_from_start,
                    "avg_margin_seconds": round(sum(r["margin_seconds"] for r in results if r["margin_seconds"]) / max(1, sum(1 for r in results if r["margin_seconds"])), 2),
                },
            }

    except Exception as e:
        logger.error(f"Error getting race dominance: {e}")
        return [{"error": str(e)}]


@tool
async def get_compound_performance(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze performance by tire compound - pace differences between soft/medium/hard.

    PERFECT FOR: "Soft vs Medium pace", "best on hards", "tire performance"

    Args:
        year: Season year
        event_name: Optional race filter
        driver_id: Optional driver filter

    Returns:
        Pace analysis broken down by tire compound.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name) if event_name else None
    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH compound_laps AS (
                SELECT
                    l.driver_id,
                    l.compound,
                    l.lap_time_seconds,
                    l.stint,
                    ROW_NUMBER() OVER (PARTITION BY l.driver_id, l.stint ORDER BY l.lap_number) as lap_in_stint,
                    s.event_name
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.lap_time_seconds > 60
                    AND l.lap_time_seconds < 200
                    AND l.compound IS NOT NULL
                    AND l.compound NOT IN ('UNKNOWN', '')
                    AND ($2::text IS NULL OR LOWER(s.event_name) LIKE LOWER('%' || $2 || '%'))
                    AND ($3::text IS NULL OR l.driver_id = $3)
            ),
            compound_stats AS (
                SELECT
                    driver_id,
                    compound,
                    COUNT(*) as laps,
                    AVG(lap_time_seconds) as avg_pace,
                    MIN(lap_time_seconds) as best_lap,
                    STDDEV(lap_time_seconds) as consistency,
                    AVG(CASE WHEN lap_in_stint <= 5 THEN lap_time_seconds END) as fresh_tire_pace,
                    AVG(CASE WHEN lap_in_stint > 10 THEN lap_time_seconds END) as worn_tire_pace
                FROM compound_laps
                GROUP BY driver_id, compound
                HAVING COUNT(*) >= 3
            )
            SELECT
                driver_id,
                compound,
                laps,
                avg_pace,
                best_lap,
                consistency,
                fresh_tire_pace,
                worn_tire_pace,
                CASE
                    WHEN worn_tire_pace IS NOT NULL AND fresh_tire_pace IS NOT NULL
                    THEN worn_tire_pace - fresh_tire_pace
                    ELSE NULL
                END as degradation
            FROM compound_stats
            ORDER BY driver_id, avg_pace ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"error": f"No compound data found"}]

            # Group by driver
            driver_compounds = {}
            for row in rows:
                drv = row["driver_id"]
                if drv not in driver_compounds:
                    driver_compounds[drv] = {"driver": drv, "compounds": {}}

                compound = row["compound"].upper()
                driver_compounds[drv]["compounds"][compound] = {
                    "laps": row["laps"],
                    "avg_pace": round(row["avg_pace"], 3),
                    "best_lap": round(row["best_lap"], 3),
                    "consistency": round(row["consistency"], 3) if row["consistency"] else None,
                    "fresh_tire_pace": round(row["fresh_tire_pace"], 3) if row["fresh_tire_pace"] else None,
                    "worn_tire_pace": round(row["worn_tire_pace"], 3) if row["worn_tire_pace"] else None,
                    "degradation_per_stint": round(row["degradation"], 3) if row["degradation"] else None,
                }

            # Calculate relative performance
            results = []
            for drv, data in driver_compounds.items():
                compounds = data["compounds"]

                # Find fastest compound
                if compounds:
                    fastest_compound = min(compounds.items(), key=lambda x: x[1]["avg_pace"])
                    fastest_name, fastest_pace = fastest_compound[0], fastest_compound[1]["avg_pace"]

                    for compound, stats in compounds.items():
                        stats["delta_to_fastest"] = round(stats["avg_pace"] - fastest_pace, 3)

                    data["fastest_on"] = fastest_name
                    data["compound_preference"] = "SOFT" if fastest_name == "SOFT" else "MEDIUM" if fastest_name == "MEDIUM" else "HARD" if fastest_name == "HARD" else "MIXED"

                results.append(data)

            return results

    except Exception as e:
        logger.error(f"Error getting compound performance: {e}")
        return [{"error": str(e)}]


# ============================================================
# STREAKS, SPRINTS & SPECIAL ANALYSIS TOOLS
# ============================================================

@tool
async def get_sprint_performance(
    year: int | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze sprint race performance - sprint specialists vs main race performance.

    PERFECT FOR: "Sprint specialist", "sprint vs main race", "best in sprints"

    Args:
        year: Optional year filter
        driver_id: Optional driver filter

    Returns:
        Sprint race statistics and comparison to main race performance.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH sprint_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.year,
                    s.event_name,
                    r.position as sprint_position,
                    r.points as sprint_points,
                    r.grid_position as sprint_grid
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'S'
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            race_results AS (
                SELECT
                    r.driver_id,
                    s.year,
                    s.event_name,
                    r.position as race_position,
                    r.points as race_points
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND ($1::int IS NULL OR s.year = $1)
            ),
            combined AS (
                SELECT
                    sr.driver_id,
                    sr.team,
                    sr.year,
                    sr.event_name,
                    sr.sprint_position,
                    sr.sprint_points,
                    sr.sprint_grid,
                    rr.race_position,
                    rr.race_points
                FROM sprint_results sr
                LEFT JOIN race_results rr ON sr.driver_id = rr.driver_id
                    AND sr.year = rr.year
                    AND sr.event_name = rr.event_name
            )
            SELECT
                driver_id,
                MAX(team) as team,
                COUNT(*) as sprints,
                SUM(CASE WHEN sprint_position = 1 THEN 1 ELSE 0 END) as sprint_wins,
                SUM(CASE WHEN sprint_position <= 3 THEN 1 ELSE 0 END) as sprint_podiums,
                AVG(sprint_position) as avg_sprint_finish,
                AVG(race_position) as avg_race_finish,
                SUM(sprint_points) as total_sprint_points,
                AVG(sprint_grid - sprint_position) as avg_sprint_positions_gained
            FROM combined
            GROUP BY driver_id
            HAVING COUNT(*) >= 1
            ORDER BY avg_sprint_finish ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": "No sprint data found"}]

            results = []
            for i, row in enumerate(rows):
                sprint_avg = row["avg_sprint_finish"] or 0
                race_avg = row["avg_race_finish"] or 0
                sprint_vs_race = round(race_avg - sprint_avg, 2) if race_avg and sprint_avg else 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "sprints": row["sprints"],
                    "sprint_wins": row["sprint_wins"],
                    "sprint_podiums": row["sprint_podiums"],
                    "avg_sprint_finish": round(sprint_avg, 2) if sprint_avg else None,
                    "avg_race_finish": round(race_avg, 2) if race_avg else None,
                    "sprint_vs_race_delta": sprint_vs_race,
                    "total_sprint_points": row["total_sprint_points"] or 0,
                    "avg_positions_gained": round(row["avg_sprint_positions_gained"], 2) if row["avg_sprint_positions_gained"] else 0,
                    "sprint_specialist": "YES" if sprint_vs_race > 2 else "SIMILAR" if abs(sprint_vs_race) <= 2 else "RACE_STRONGER",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting sprint performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_winning_streaks(
    year: int | None = None,
    driver_id: str | None = None,
    streak_type: str = "wins",
) -> list[dict]:
    """
    Analyze winning streaks, podium streaks, and points streaks.

    PERFECT FOR: "Consecutive wins", "longest streak", "unbeaten run"

    Args:
        year: Optional year filter
        driver_id: Optional driver filter
        streak_type: "wins", "podiums", or "points"

    Returns:
        Streak analysis with longest and current streaks.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    # Determine condition based on streak type
    if streak_type == "wins":
        condition = "r.position = 1"
        streak_name = "Win"
    elif streak_type == "podiums":
        condition = "r.position <= 3"
        streak_name = "Podium"
    else:  # points
        condition = "r.points > 0"
        streak_name = "Points"

    try:
        query = f"""
            WITH ordered_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.year,
                    s.round_number,
                    s.event_name,
                    r.position,
                    r.points,
                    CASE WHEN {condition} THEN 1 ELSE 0 END as streak_hit,
                    ROW_NUMBER() OVER (PARTITION BY r.driver_id ORDER BY s.year, s.round_number) as race_num
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            streak_groups AS (
                SELECT *,
                    race_num - SUM(streak_hit) OVER (
                        PARTITION BY driver_id
                        ORDER BY race_num
                        ROWS UNBOUNDED PRECEDING
                    ) as streak_group
                FROM ordered_results
                WHERE streak_hit = 1
            ),
            streak_lengths AS (
                SELECT
                    driver_id,
                    streak_group,
                    COUNT(*) as streak_length,
                    MIN(year) as start_year,
                    MIN(event_name) as start_race,
                    MAX(year) as end_year,
                    MAX(event_name) as end_race
                FROM streak_groups
                GROUP BY driver_id, streak_group
            )
            SELECT
                driver_id,
                MAX(streak_length) as longest_streak,
                COUNT(*) as total_streaks,
                SUM(streak_length) as total_streak_races
            FROM streak_lengths
            GROUP BY driver_id
            ORDER BY longest_streak DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No {streak_type} streak data found"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "streak_type": streak_name,
                    "longest_streak": row["longest_streak"],
                    "total_streaks": row["total_streaks"],
                    "total_streak_races": row["total_streak_races"],
                    "dominance_rating": "LEGENDARY" if row["longest_streak"] >= 10 else "DOMINANT" if row["longest_streak"] >= 5 else "STRONG" if row["longest_streak"] >= 3 else "NORMAL",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting winning streaks: {e}")
        return [{"error": str(e)}]


@tool
async def get_constructor_evolution(
    year: int,
    team_names: list[str] | None = None,
) -> dict:
    """
    Track constructor championship points evolution throughout a season.

    PERFECT FOR: "Constructor championship battle", "team points gap", "constructor standings over time"

    Args:
        year: Season year
        team_names: Optional list of teams to focus on (otherwise top 5)

    Returns:
        Race-by-race cumulative team points and gaps.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    teams = [normalize_team_name(t) for t in team_names] if team_names else None

    try:
        query = """
            WITH race_points AS (
                SELECT
                    r.team,
                    s.round_number,
                    s.event_name,
                    SUM(r.points) as race_points,
                    SUM(SUM(r.points)) OVER (
                        PARTITION BY r.team
                        ORDER BY s.round_number
                    ) as cumulative_points
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
                GROUP BY r.team, s.round_number, s.event_name
            ),
            top_teams AS (
                SELECT team
                FROM race_points
                GROUP BY team
                ORDER BY MAX(cumulative_points) DESC
                LIMIT 5
            ),
            filtered_points AS (
                SELECT rp.*
                FROM race_points rp
                WHERE ($2::text[] IS NULL AND rp.team IN (SELECT team FROM top_teams))
                   OR (rp.team = ANY($2::text[]))
            )
            SELECT *
            FROM filtered_points
            ORDER BY round_number, cumulative_points DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, teams)

            if not rows:
                return {"error": f"No constructor data found for {year}"}

            # Organize by round
            rounds = {}
            all_teams = set()
            for row in rows:
                rnd = row["round_number"]
                if rnd not in rounds:
                    rounds[rnd] = {"round": rnd, "event": row["event_name"], "standings": {}}
                rounds[rnd]["standings"][row["team"]] = {
                    "points": row["cumulative_points"],
                    "race_points": row["race_points"],
                }
                all_teams.add(row["team"])

            # Calculate gaps and leader
            evolution = []
            for rnd in sorted(rounds.keys()):
                round_data = rounds[rnd]
                standings = round_data["standings"]

                # Find leader
                leader = max(standings.items(), key=lambda x: x[1]["points"])
                leader_team, leader_data = leader

                round_entry = {
                    "round": rnd,
                    "event": round_data["event"],
                    "leader": leader_team,
                    "leader_points": leader_data["points"],
                    "teams": {},
                }

                for team, data in sorted(standings.items(), key=lambda x: -x[1]["points"]):
                    gap_to_leader = leader_data["points"] - data["points"]
                    round_entry["teams"][team] = {
                        "cumulative_points": data["points"],
                        "race_points": data["race_points"],
                        "gap_to_leader": gap_to_leader,
                    }

                evolution.append(round_entry)

            return {
                "year": year,
                "evolution": evolution,
                "total_rounds": len(evolution),
                "teams_tracked": list(all_teams),
                "final_champion": evolution[-1]["leader"] if evolution else None,
            }

    except Exception as e:
        logger.error(f"Error getting constructor evolution: {e}")
        return {"error": str(e)}


# Map of driver nationalities to their home races
DRIVER_HOME_RACES = {
    # British drivers
    "HAM": ["Britain"], "NOR": ["Britain"], "RUS": ["Britain"],
    # Dutch
    "VER": ["Netherlands"],
    # Spanish
    "ALO": ["Spain"], "SAI": ["Spain"],
    # Monegasque
    "LEC": ["Monaco"],
    # Australian
    "RIC": ["Australia"], "PIA": ["Australia"],
    # Mexican
    "PER": ["Mexico"],
    # Canadian
    "STR": ["Canada"], "LAT": ["Canada"],
    # French
    "GAS": ["France"], "OCO": ["France"],
    # German
    "HUL": ["Germany"], "VET": ["Germany"], "MSC": ["Germany"],
    # Finnish
    "BOT": ["Finland"],
    # Japanese
    "TSU": ["Japan"],
    # Chinese
    "ZHO": ["China"],
    # Thai
    "ALB": ["Thailand"],
    # Danish
    "MAG": ["Denmark"],
    # American
    "SAR": ["United States", "Las Vegas", "Miami"],
}


@tool
async def get_home_race_performance(
    driver_id: str | None = None,
    year: int | None = None,
) -> list[dict]:
    """
    Analyze how drivers perform at their home Grand Prix.

    PERFECT FOR: "Home race advantage", "Hamilton at Silverstone", "home GP performance"

    Args:
        driver_id: Optional specific driver filter
        year: Optional year filter

    Returns:
        Performance statistics at home races vs away races.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Build home race conditions for each driver
        home_conditions = []
        for drv, races in DRIVER_HOME_RACES.items():
            race_list = "', '".join(races)
            home_conditions.append(f"(r.driver_id = '{drv}' AND s.event_name IN ('{race_list}'))")

        home_condition = " OR ".join(home_conditions) if home_conditions else "FALSE"

        query = f"""
            WITH race_data AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.year,
                    s.event_name,
                    r.position,
                    r.points,
                    r.grid_position,
                    CASE WHEN {home_condition} THEN true ELSE false END as is_home_race
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND r.position IS NOT NULL
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            home_stats AS (
                SELECT
                    driver_id,
                    COUNT(*) as home_races,
                    AVG(position) as home_avg_finish,
                    SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as home_wins,
                    SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) as home_podiums,
                    SUM(points) as home_points
                FROM race_data
                WHERE is_home_race = true
                GROUP BY driver_id
            ),
            away_stats AS (
                SELECT
                    driver_id,
                    COUNT(*) as away_races,
                    AVG(position) as away_avg_finish,
                    SUM(points) as away_points
                FROM race_data
                WHERE is_home_race = false
                GROUP BY driver_id
            )
            SELECT
                h.driver_id,
                h.home_races,
                h.home_avg_finish,
                h.home_wins,
                h.home_podiums,
                h.home_points,
                a.away_races,
                a.away_avg_finish,
                a.away_points
            FROM home_stats h
            LEFT JOIN away_stats a ON h.driver_id = a.driver_id
            ORDER BY h.home_avg_finish ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": "No home race data found"}]

            results = []
            for i, row in enumerate(rows):
                home_avg = row["home_avg_finish"] or 0
                away_avg = row["away_avg_finish"] or 0
                home_advantage = round(away_avg - home_avg, 2) if away_avg and home_avg else 0

                home_races = DRIVER_HOME_RACES.get(row["driver_id"], ["Unknown"])

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "home_gp": home_races[0] if home_races else "Unknown",
                    "home_races": row["home_races"],
                    "home_wins": row["home_wins"],
                    "home_podiums": row["home_podiums"],
                    "home_avg_finish": round(home_avg, 2) if home_avg else None,
                    "away_avg_finish": round(away_avg, 2) if away_avg else None,
                    "home_advantage_positions": home_advantage,
                    "home_points": row["home_points"] or 0,
                    "home_performance": "DOMINANT" if home_advantage >= 3 else "STRONG" if home_advantage >= 1 else "SIMILAR" if abs(home_advantage) < 1 else "STRUGGLES",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting home race performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_comeback_drives(
    year: int | None = None,
    min_positions_gained: int = 5,
    top_n: int = 20,
) -> list[dict]:
    """
    Find the best recovery drives - positions gained from poor starting positions.

    PERFECT FOR: "Best recovery", "from back of grid", "damage limitation", "great drives"

    Args:
        year: Optional year filter
        min_positions_gained: Minimum positions to qualify as comeback (default 5)
        top_n: Number of results to return

    Returns:
        Best comeback drives ranked by positions gained.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                r.driver_id,
                r.team,
                s.year,
                s.event_name,
                r.grid_position,
                r.position as finish_position,
                r.grid_position - r.position as positions_gained,
                r.points
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.session_type = 'R'
                AND r.grid_position IS NOT NULL
                AND r.position IS NOT NULL
                AND r.grid_position - r.position >= $1
                AND ($2::int IS NULL OR s.year = $2)
            ORDER BY positions_gained DESC, r.position ASC
            LIMIT $3
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, min_positions_gained, year, top_n)

            if not rows:
                return [{"error": f"No comeback drives found with {min_positions_gained}+ positions gained"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "race": f"{row['year']} {row['event_name']}",
                    "started": f"P{row['grid_position']}",
                    "finished": f"P{row['finish_position']}",
                    "positions_gained": row["positions_gained"],
                    "points": row["points"] or 0,
                    "comeback_rating": "LEGENDARY" if row["positions_gained"] >= 15 else "INCREDIBLE" if row["positions_gained"] >= 10 else "GREAT" if row["positions_gained"] >= 7 else "SOLID",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting comeback drives: {e}")
        return [{"error": str(e)}]


@tool
async def get_grid_penalty_impact(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze the impact of grid penalties on race results.

    PERFECT FOR: "Grid penalty effect", "penalty impact", "starting from back"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Analysis of races where drivers had significant grid drops.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Look for races where grid position is significantly worse than typical
        # (suggesting a penalty was applied)
        query = """
            WITH driver_typical_grid AS (
                SELECT
                    r.driver_id,
                    AVG(r.grid_position) as typical_grid,
                    STDDEV(r.grid_position) as grid_stddev
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1 AND s.session_type = 'R'
                    AND r.grid_position IS NOT NULL
                    AND ($2::text IS NULL OR r.driver_id = $2)
                GROUP BY r.driver_id
                HAVING COUNT(*) >= 3
            ),
            potential_penalties AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.event_name,
                    r.grid_position,
                    r.position as finish_position,
                    r.points,
                    dtg.typical_grid,
                    r.grid_position - dtg.typical_grid as grid_drop,
                    r.grid_position - r.position as positions_gained
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                JOIN driver_typical_grid dtg ON r.driver_id = dtg.driver_id
                WHERE s.year = $1 AND s.session_type = 'R'
                    AND r.grid_position > dtg.typical_grid + 5  -- More than 5 places worse than usual
                    AND ($2::text IS NULL OR r.driver_id = $2)
            )
            SELECT *
            FROM potential_penalties
            ORDER BY grid_drop DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"message": f"No significant grid penalties detected in {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "race": row["event_name"],
                    "typical_grid": round(row["typical_grid"], 1),
                    "actual_grid": row["grid_position"],
                    "estimated_penalty": round(row["grid_drop"]),
                    "finish_position": row["finish_position"],
                    "positions_recovered": row["positions_gained"],
                    "points_scored": row["points"] or 0,
                    "damage_limitation": "EXCELLENT" if row["positions_gained"] >= row["grid_drop"] * 0.7 else "GOOD" if row["positions_gained"] >= row["grid_drop"] * 0.5 else "MODERATE" if row["positions_gained"] > 0 else "POOR",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting grid penalty impact: {e}")
        return [{"error": str(e)}]


@tool
async def get_finishing_streaks(
    year: int | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze consecutive race finishes (no DNFs) - reliability streaks.

    PERFECT FOR: "Consecutive finishes", "no DNF streak", "reliability streak"

    Args:
        year: Optional year filter
        driver_id: Optional driver filter

    Returns:
        Finishing streak statistics showing reliability.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH ordered_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.year,
                    s.round_number,
                    s.event_name,
                    r.position,
                    r.status,
                    CASE WHEN r.position IS NOT NULL AND r.position <= 20 THEN 1 ELSE 0 END as finished,
                    ROW_NUMBER() OVER (PARTITION BY r.driver_id ORDER BY s.year, s.round_number) as race_num
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            streak_groups AS (
                SELECT *,
                    race_num - SUM(finished) OVER (
                        PARTITION BY driver_id
                        ORDER BY race_num
                        ROWS UNBOUNDED PRECEDING
                    ) as streak_group
                FROM ordered_results
                WHERE finished = 1
            ),
            streak_lengths AS (
                SELECT
                    driver_id,
                    streak_group,
                    COUNT(*) as streak_length,
                    MIN(year) as start_year,
                    MAX(year) as end_year
                FROM streak_groups
                GROUP BY driver_id, streak_group
            ),
            driver_stats AS (
                SELECT
                    driver_id,
                    MAX(streak_length) as longest_finish_streak,
                    SUM(streak_length) as total_finishes
                FROM streak_lengths
                GROUP BY driver_id
            ),
            total_races AS (
                SELECT
                    driver_id,
                    COUNT(*) as races_entered
                FROM ordered_results
                GROUP BY driver_id
            )
            SELECT
                ds.driver_id,
                ds.longest_finish_streak,
                ds.total_finishes,
                tr.races_entered,
                ROUND(ds.total_finishes::numeric / tr.races_entered * 100, 1) as finish_rate
            FROM driver_stats ds
            JOIN total_races tr ON ds.driver_id = tr.driver_id
            ORDER BY ds.longest_finish_streak DESC, finish_rate DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": "No finishing streak data found"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "longest_finish_streak": row["longest_finish_streak"],
                    "total_finishes": row["total_finishes"],
                    "races_entered": row["races_entered"],
                    "finish_rate_percent": float(row["finish_rate"]) if row["finish_rate"] else 0,
                    "dnfs": row["races_entered"] - row["total_finishes"],
                    "reliability_rating": "BULLETPROOF" if row["finish_rate"] and row["finish_rate"] >= 95 else "RELIABLE" if row["finish_rate"] and row["finish_rate"] >= 85 else "AVERAGE" if row["finish_rate"] and row["finish_rate"] >= 70 else "FRAGILE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting finishing streaks: {e}")
        return [{"error": str(e)}]


# ============================================================
# ADVANCED RACE ANALYSIS TOOLS
# ============================================================

@tool
async def get_gap_to_leader(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze gap to race leader - finishing margins and race-long gaps.

    PERFECT FOR: "How far behind was P2?", "gap to winner", "margin of victory"

    Args:
        year: Season year
        event_name: Optional race filter
        driver_id: Optional driver filter

    Returns:
        Gap analysis showing finishing margins and average gaps.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name) if event_name else None
    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH race_gaps AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.event_name,
                    s.year,
                    r.position,
                    r.time_or_gap,
                    r.points
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND r.position IS NOT NULL
                    AND ($2::text IS NULL OR LOWER(s.event_name) LIKE LOWER('%' || $2 || '%'))
                    AND ($3::text IS NULL OR r.driver_id = $3)
                ORDER BY s.round_number, r.position
            )
            SELECT
                driver_id,
                team,
                event_name,
                position,
                time_or_gap,
                points
            FROM race_gaps
            ORDER BY event_name, position
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"error": f"No gap data found for {year}"}]

            # Group by race
            races = {}
            for row in rows:
                race = row["event_name"]
                if race not in races:
                    races[race] = []
                races[race].append(row)

            results = []
            for race_name, race_results in races.items():
                winner = race_results[0] if race_results else None
                race_data = {
                    "race": race_name,
                    "winner": winner["driver_id"] if winner else None,
                    "winner_team": winner["team"] if winner else None,
                    "gaps": [],
                }

                for row in race_results[1:]:  # Skip winner
                    gap_str = row["time_or_gap"] or "Unknown"
                    gap_seconds = None

                    # Parse gap string
                    if gap_str and "+" in str(gap_str):
                        try:
                            gap_seconds = float(str(gap_str).replace("+", "").replace("s", "").split()[0])
                        except (ValueError, IndexError):
                            pass

                    race_data["gaps"].append({
                        "position": row["position"],
                        "driver": row["driver_id"],
                        "team": row["team"],
                        "gap_to_leader": gap_str,
                        "gap_seconds": gap_seconds,
                        "points": row["points"] or 0,
                    })

                results.append(race_data)

            return results

    except Exception as e:
        logger.error(f"Error getting gap to leader: {e}")
        return [{"error": str(e)}]


@tool
async def get_strategy_effectiveness(
    year: int,
    event_name: str | None = None,
) -> list[dict]:
    """
    Analyze which pit strategies (1-stop, 2-stop, 3-stop) were most effective.

    PERFECT FOR: "1-stop vs 2-stop", "which strategy worked", "optimal pit stops"

    Args:
        year: Season year
        event_name: Optional race filter

    Returns:
        Strategy effectiveness showing avg finish by number of stops.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name) if event_name else None

    try:
        query = """
            WITH stint_counts AS (
                SELECT
                    l.session_id,
                    l.driver_id,
                    MAX(l.stint) as num_stints,
                    s.event_name,
                    s.year
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR LOWER(s.event_name) LIKE LOWER('%' || $2 || '%'))
                GROUP BY l.session_id, l.driver_id, s.event_name, s.year
            ),
            strategy_results AS (
                SELECT
                    sc.event_name,
                    sc.driver_id,
                    sc.num_stints - 1 as pit_stops,
                    r.position,
                    r.points,
                    r.grid_position,
                    r.grid_position - r.position as positions_gained
                FROM stint_counts sc
                JOIN results r ON sc.session_id = r.session_id AND sc.driver_id = r.driver_id
                WHERE r.position IS NOT NULL
            )
            SELECT
                event_name,
                pit_stops,
                COUNT(*) as drivers,
                AVG(position) as avg_finish,
                AVG(positions_gained) as avg_positions_gained,
                SUM(points) as total_points,
                MIN(position) as best_finish,
                array_agg(driver_id ORDER BY position) as drivers_list
            FROM strategy_results
            GROUP BY event_name, pit_stops
            ORDER BY event_name, avg_finish ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event)

            if not rows:
                return [{"error": f"No strategy data found for {year}"}]

            # Group by race
            races = {}
            for row in rows:
                race = row["event_name"]
                if race not in races:
                    races[race] = {"race": race, "strategies": []}

                strategy_name = f"{row['pit_stops']}-stop"
                races[race]["strategies"].append({
                    "strategy": strategy_name,
                    "pit_stops": row["pit_stops"],
                    "drivers_used": row["drivers"],
                    "avg_finish": round(row["avg_finish"], 2),
                    "avg_positions_gained": round(row["avg_positions_gained"], 2) if row["avg_positions_gained"] else 0,
                    "total_points": row["total_points"] or 0,
                    "best_finish": f"P{row['best_finish']}",
                    "drivers": row["drivers_list"][:5],  # Top 5 finishers
                    "effectiveness": "OPTIMAL" if row["avg_finish"] <= 5 else "GOOD" if row["avg_finish"] <= 10 else "AVERAGE" if row["avg_finish"] <= 15 else "POOR",
                })

            # Determine winning strategy for each race
            results = []
            for race_name, race_data in races.items():
                if race_data["strategies"]:
                    best = min(race_data["strategies"], key=lambda x: x["avg_finish"])
                    race_data["optimal_strategy"] = best["strategy"]
                results.append(race_data)

            return results

    except Exception as e:
        logger.error(f"Error getting strategy effectiveness: {e}")
        return [{"error": str(e)}]


@tool
async def get_safety_car_impact(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze which drivers benefit most from safety cars (position changes during SC periods).

    PERFECT FOR: "Who benefits from safety cars?", "SC luck", "safety car impact"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Safety car beneficiaries and victims analysis.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Identify races with safety cars by looking for laps where everyone slowed significantly
        # This is an approximation - we look for races where leaders had unusually slow laps
        query = """
            WITH potential_sc_races AS (
                SELECT DISTINCT
                    l.session_id,
                    s.event_name,
                    s.year
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.position = 1
                    AND l.lap_time_seconds > 120  -- Unusually slow for leader suggests SC
            ),
            race_volatility AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.event_name,
                    r.grid_position,
                    r.position as finish_position,
                    r.grid_position - r.position as positions_gained,
                    r.points,
                    CASE WHEN psc.session_id IS NOT NULL THEN true ELSE false END as had_safety_car
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                LEFT JOIN potential_sc_races psc ON r.session_id = psc.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND r.position IS NOT NULL
                    AND r.grid_position IS NOT NULL
                    AND ($2::text IS NULL OR r.driver_id = $2)
            )
            SELECT
                driver_id,
                MAX(team) as team,
                COUNT(*) FILTER (WHERE had_safety_car) as sc_races,
                COUNT(*) FILTER (WHERE NOT had_safety_car) as non_sc_races,
                AVG(positions_gained) FILTER (WHERE had_safety_car) as avg_gain_sc,
                AVG(positions_gained) FILTER (WHERE NOT had_safety_car) as avg_gain_no_sc,
                AVG(finish_position) FILTER (WHERE had_safety_car) as avg_finish_sc,
                AVG(finish_position) FILTER (WHERE NOT had_safety_car) as avg_finish_no_sc,
                SUM(points) FILTER (WHERE had_safety_car) as points_sc,
                SUM(points) FILTER (WHERE NOT had_safety_car) as points_no_sc
            FROM race_volatility
            GROUP BY driver_id
            HAVING COUNT(*) FILTER (WHERE had_safety_car) >= 1
            ORDER BY avg_gain_sc DESC NULLS LAST
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"message": f"No safety car data detected for {year}"}]

            results = []
            for i, row in enumerate(rows):
                sc_benefit = (row["avg_gain_sc"] or 0) - (row["avg_gain_no_sc"] or 0)

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "sc_races": row["sc_races"],
                    "non_sc_races": row["non_sc_races"],
                    "avg_positions_gained_sc": round(row["avg_gain_sc"], 2) if row["avg_gain_sc"] else 0,
                    "avg_positions_gained_no_sc": round(row["avg_gain_no_sc"], 2) if row["avg_gain_no_sc"] else 0,
                    "sc_benefit": round(sc_benefit, 2),
                    "avg_finish_sc": round(row["avg_finish_sc"], 2) if row["avg_finish_sc"] else None,
                    "avg_finish_no_sc": round(row["avg_finish_no_sc"], 2) if row["avg_finish_no_sc"] else None,
                    "sc_luck_rating": "VERY_LUCKY" if sc_benefit >= 3 else "LUCKY" if sc_benefit >= 1 else "NEUTRAL" if abs(sc_benefit) < 1 else "UNLUCKY" if sc_benefit <= -1 else "VERY_UNLUCKY",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting safety car impact: {e}")
        return [{"error": str(e)}]


@tool
async def get_tire_life_masters(
    year: int,
    compound: str | None = None,
) -> list[dict]:
    """
    Find who manages tires best - longest stints while maintaining pace.

    PERFECT FOR: "Who makes tires last?", "longest stints", "tire whisperer"

    Args:
        year: Season year
        compound: Optional compound filter (SOFT, MEDIUM, HARD)

    Returns:
        Tire management rankings by stint length and pace degradation.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    compound_filter = compound.upper() if compound else None

    try:
        query = """
            WITH stint_data AS (
                SELECT
                    l.driver_id,
                    l.session_id,
                    l.stint,
                    l.compound,
                    COUNT(*) as stint_length,
                    AVG(l.lap_time_seconds) as avg_pace,
                    MIN(l.lap_time_seconds) as best_lap,
                    MAX(l.lap_time_seconds) - MIN(l.lap_time_seconds) as pace_drop
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.lap_time_seconds > 60
                    AND l.lap_time_seconds < 200
                    AND l.compound IS NOT NULL
                    AND ($2::text IS NULL OR UPPER(l.compound) = $2)
                GROUP BY l.driver_id, l.session_id, l.stint, l.compound
                HAVING COUNT(*) >= 5  -- Minimum 5 laps per stint
            )
            SELECT
                driver_id,
                COUNT(*) as total_stints,
                AVG(stint_length) as avg_stint_length,
                MAX(stint_length) as longest_stint,
                AVG(pace_drop) as avg_pace_drop,
                AVG(avg_pace) as overall_avg_pace
            FROM stint_data
            GROUP BY driver_id
            HAVING COUNT(*) >= 3
            ORDER BY avg_stint_length DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, compound_filter)

            if not rows:
                return [{"error": f"No stint data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "total_stints": row["total_stints"],
                    "avg_stint_length": round(row["avg_stint_length"], 1),
                    "longest_stint": row["longest_stint"],
                    "avg_pace_degradation": round(row["avg_pace_drop"], 3) if row["avg_pace_drop"] else 0,
                    "tire_management": "EXCEPTIONAL" if row["avg_stint_length"] >= 25 else "EXCELLENT" if row["avg_stint_length"] >= 20 else "GOOD" if row["avg_stint_length"] >= 15 else "AVERAGE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting tire life masters: {e}")
        return [{"error": str(e)}]


@tool
async def get_championship_momentum(
    year: int,
    last_n_races: int = 5,
) -> list[dict]:
    """
    Analyze recent form - points scored in last N races to show momentum.

    PERFECT FOR: "Hot streak", "form last 5 races", "momentum", "who's on fire"

    Args:
        year: Season year
        last_n_races: Number of recent races to analyze (default 5)

    Returns:
        Momentum analysis showing recent form vs season average.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            WITH race_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.round_number,
                    s.event_name,
                    r.position,
                    r.points,
                    ROW_NUMBER() OVER (PARTITION BY r.driver_id ORDER BY s.round_number DESC) as recency
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
            ),
            recent_form AS (
                SELECT
                    driver_id,
                    MAX(team) as team,
                    SUM(points) as recent_points,
                    AVG(position) as recent_avg_finish,
                    COUNT(*) as recent_races,
                    SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as recent_wins,
                    SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) as recent_podiums
                FROM race_results
                WHERE recency <= $2
                GROUP BY driver_id
            ),
            season_form AS (
                SELECT
                    driver_id,
                    SUM(points) as total_points,
                    AVG(position) as season_avg_finish,
                    COUNT(*) as total_races,
                    SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as total_wins
                FROM race_results
                GROUP BY driver_id
            )
            SELECT
                rf.driver_id,
                rf.team,
                rf.recent_points,
                rf.recent_avg_finish,
                rf.recent_races,
                rf.recent_wins,
                rf.recent_podiums,
                sf.total_points,
                sf.season_avg_finish,
                sf.total_races,
                sf.total_wins,
                rf.recent_points::float / NULLIF(rf.recent_races, 0) as recent_ppg,
                sf.total_points::float / NULLIF(sf.total_races, 0) as season_ppg
            FROM recent_form rf
            JOIN season_form sf ON rf.driver_id = sf.driver_id
            ORDER BY rf.recent_points DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, last_n_races)

            if not rows:
                return [{"error": f"No momentum data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                recent_ppg = row["recent_ppg"] or 0
                season_ppg = row["season_ppg"] or 0
                momentum = recent_ppg - season_ppg

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "last_n_races": row["recent_races"],
                    "recent_points": row["recent_points"] or 0,
                    "recent_wins": row["recent_wins"],
                    "recent_podiums": row["recent_podiums"],
                    "recent_avg_finish": round(row["recent_avg_finish"], 2) if row["recent_avg_finish"] else None,
                    "recent_points_per_race": round(recent_ppg, 2),
                    "season_points_per_race": round(season_ppg, 2),
                    "momentum_delta": round(momentum, 2),
                    "total_points": row["total_points"] or 0,
                    "form": "ON_FIRE" if momentum >= 5 else "HOT" if momentum >= 2 else "CONSISTENT" if abs(momentum) < 2 else "COOLING" if momentum <= -2 else "COLD",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting championship momentum: {e}")
        return [{"error": str(e)}]


@tool
async def get_head_to_head_career(
    driver_1: str,
    driver_2: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict:
    """
    Get all-time head-to-head record between two drivers across their careers.

    PERFECT FOR: "All-time Hamilton vs Verstappen", "career H2H", "lifetime record"

    Args:
        driver_1: First driver code (e.g., "HAM")
        driver_2: Second driver code (e.g., "VER")
        start_year: Optional start year filter
        end_year: Optional end year filter

    Returns:
        Comprehensive career head-to-head statistics.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    d1 = normalize_driver_id(driver_1)
    d2 = normalize_driver_id(driver_2)

    try:
        query = """
            WITH shared_races AS (
                SELECT
                    r1.session_id,
                    s.year,
                    s.event_name,
                    r1.driver_id as d1,
                    r1.position as d1_pos,
                    r1.points as d1_points,
                    r1.grid_position as d1_grid,
                    r2.driver_id as d2,
                    r2.position as d2_pos,
                    r2.points as d2_points,
                    r2.grid_position as d2_grid
                FROM results r1
                JOIN results r2 ON r1.session_id = r2.session_id
                JOIN sessions s ON r1.session_id = s.session_id
                WHERE r1.driver_id = $1
                    AND r2.driver_id = $2
                    AND s.session_type = 'R'
                    AND r1.position IS NOT NULL
                    AND r2.position IS NOT NULL
                    AND ($3::int IS NULL OR s.year >= $3)
                    AND ($4::int IS NULL OR s.year <= $4)
            )
            SELECT
                COUNT(*) as races_together,
                SUM(CASE WHEN d1_pos < d2_pos THEN 1 ELSE 0 END) as d1_race_wins,
                SUM(CASE WHEN d2_pos < d1_pos THEN 1 ELSE 0 END) as d2_race_wins,
                SUM(CASE WHEN d1_grid < d2_grid THEN 1 ELSE 0 END) as d1_quali_wins,
                SUM(CASE WHEN d2_grid < d1_grid THEN 1 ELSE 0 END) as d2_quali_wins,
                SUM(d1_points) as d1_total_points,
                SUM(d2_points) as d2_total_points,
                AVG(d1_pos) as d1_avg_finish,
                AVG(d2_pos) as d2_avg_finish,
                SUM(CASE WHEN d1_pos = 1 THEN 1 ELSE 0 END) as d1_wins,
                SUM(CASE WHEN d2_pos = 1 THEN 1 ELSE 0 END) as d2_wins,
                SUM(CASE WHEN d1_pos <= 3 THEN 1 ELSE 0 END) as d1_podiums,
                SUM(CASE WHEN d2_pos <= 3 THEN 1 ELSE 0 END) as d2_podiums,
                MIN(year) as first_year,
                MAX(year) as last_year
            FROM shared_races
        """

        async with _pool.acquire() as conn:
            row = await conn.fetchrow(query, d1, d2, start_year, end_year)

            if not row or row["races_together"] == 0:
                return {"error": f"No shared races found between {driver_1} and {driver_2}"}

            d1_race_wins = row["d1_race_wins"] or 0
            d2_race_wins = row["d2_race_wins"] or 0
            race_winner = d1 if d1_race_wins > d2_race_wins else d2 if d2_race_wins > d1_race_wins else "TIE"

            d1_quali_wins = row["d1_quali_wins"] or 0
            d2_quali_wins = row["d2_quali_wins"] or 0
            quali_winner = d1 if d1_quali_wins > d2_quali_wins else d2 if d2_quali_wins > d1_quali_wins else "TIE"

            return {
                "driver_1": d1,
                "driver_2": d2,
                "period": f"{row['first_year']}-{row['last_year']}",
                "races_together": row["races_together"],
                "head_to_head_race": {
                    d1: d1_race_wins,
                    d2: d2_race_wins,
                    "winner": race_winner,
                },
                "head_to_head_qualifying": {
                    d1: d1_quali_wins,
                    d2: d2_quali_wins,
                    "winner": quali_winner,
                },
                "total_points": {
                    d1: row["d1_total_points"] or 0,
                    d2: row["d2_total_points"] or 0,
                },
                "race_wins": {
                    d1: row["d1_wins"],
                    d2: row["d2_wins"],
                },
                "podiums": {
                    d1: row["d1_podiums"],
                    d2: row["d2_podiums"],
                },
                "avg_finish": {
                    d1: round(row["d1_avg_finish"], 2) if row["d1_avg_finish"] else None,
                    d2: round(row["d2_avg_finish"], 2) if row["d2_avg_finish"] else None,
                },
                "overall_winner": race_winner,
                "dominance": "DOMINANT" if abs(d1_race_wins - d2_race_wins) > row["races_together"] * 0.2 else "CLOSE",
            }

    except Exception as e:
        logger.error(f"Error getting head to head career: {e}")
        return {"error": str(e)}


# Known rookie seasons (driver_id: rookie_year)
ROOKIE_SEASONS = {
    "VER": 2015, "LEC": 2018, "NOR": 2019, "RUS": 2019, "ALB": 2019,
    "GAS": 2017, "OCO": 2016, "STR": 2019, "TSU": 2021, "MSC": 2021,
    "MAZ": 2021, "ZHO": 2022, "DEV": 2022, "SAR": 2023, "PIA": 2023,
    "LAW": 2023, "BEA": 2024, "COL": 2024,
}


@tool
async def get_rookie_comparison(
    year: int,
) -> list[dict]:
    """
    Compare rookie performance vs experienced drivers in a season.

    PERFECT FOR: "Rookie of the year", "rookie vs veteran", "best rookie"

    Args:
        year: Season year

    Returns:
        Rookie performance comparison with veterans.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                r.driver_id,
                r.team,
                COUNT(*) as races,
                SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) as podiums,
                SUM(CASE WHEN r.position <= 10 THEN 1 ELSE 0 END) as points_finishes,
                SUM(r.points) as total_points,
                AVG(r.position) as avg_finish,
                AVG(r.grid_position) as avg_grid
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND r.position IS NOT NULL
            GROUP BY r.driver_id, r.team
            HAVING COUNT(*) >= 5
            ORDER BY total_points DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year)

            if not rows:
                return [{"error": f"No data found for {year}"}]

            rookies = []
            veterans = []

            for row in rows:
                driver = row["driver_id"]
                is_rookie = ROOKIE_SEASONS.get(driver) == year

                driver_data = {
                    "driver": driver,
                    "team": row["team"],
                    "is_rookie": is_rookie,
                    "races": row["races"],
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "points_finishes": row["points_finishes"],
                    "total_points": row["total_points"] or 0,
                    "avg_finish": round(row["avg_finish"], 2) if row["avg_finish"] else None,
                    "avg_grid": round(row["avg_grid"], 2) if row["avg_grid"] else None,
                }

                if is_rookie:
                    rookies.append(driver_data)
                else:
                    veterans.append(driver_data)

            # Rank rookies
            for i, rookie in enumerate(sorted(rookies, key=lambda x: -x["total_points"])):
                rookie["rookie_rank"] = i + 1
                rookie["rating"] = "EXCEPTIONAL" if rookie["total_points"] >= 50 else "IMPRESSIVE" if rookie["total_points"] >= 20 else "SOLID" if rookie["total_points"] >= 5 else "LEARNING"

            return {
                "year": year,
                "rookies": rookies,
                "rookie_of_year": rookies[0]["driver"] if rookies else None,
                "rookie_count": len(rookies),
                "veteran_avg_points": round(sum(v["total_points"] for v in veterans) / len(veterans), 1) if veterans else 0,
                "best_rookie_points": rookies[0]["total_points"] if rookies else 0,
            }

    except Exception as e:
        logger.error(f"Error getting rookie comparison: {e}")
        return [{"error": str(e)}]


@tool
async def get_team_lockouts(
    year: int | None = None,
    team: str | None = None,
) -> list[dict]:
    """
    Find 1-2 finishes and front row lockouts by teams.

    PERFECT FOR: "1-2 finishes", "front row lockout", "team dominance"

    Args:
        year: Optional year filter
        team: Optional team filter

    Returns:
        Team lockout statistics - 1-2 finishes and front row lockouts.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    team_filter = normalize_team_name(team) if team else None

    try:
        query = """
            WITH race_results AS (
                SELECT
                    s.year,
                    s.event_name,
                    r.team,
                    r.position,
                    r.grid_position,
                    r.driver_id
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR LOWER(r.team) LIKE LOWER('%' || $2 || '%'))
            ),
            lockouts AS (
                SELECT
                    year,
                    event_name,
                    team,
                    CASE WHEN COUNT(*) FILTER (WHERE position IN (1, 2)) = 2 THEN true ELSE false END as is_1_2,
                    CASE WHEN COUNT(*) FILTER (WHERE grid_position IN (1, 2)) = 2 THEN true ELSE false END as is_front_row,
                    array_agg(driver_id ORDER BY position) FILTER (WHERE position <= 2) as top_2_drivers
                FROM race_results
                WHERE position <= 4 OR grid_position <= 4
                GROUP BY year, event_name, team
            )
            SELECT
                team,
                COUNT(*) FILTER (WHERE is_1_2) as one_two_finishes,
                COUNT(*) FILTER (WHERE is_front_row) as front_row_lockouts,
                array_agg(DISTINCT year) as years,
                array_agg(event_name) FILTER (WHERE is_1_2) as one_two_races
            FROM lockouts
            GROUP BY team
            HAVING COUNT(*) FILTER (WHERE is_1_2) > 0 OR COUNT(*) FILTER (WHERE is_front_row) > 0
            ORDER BY one_two_finishes DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, team_filter)

            if not rows:
                return [{"message": "No team lockouts found"}]

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "team": row["team"],
                    "one_two_finishes": row["one_two_finishes"],
                    "front_row_lockouts": row["front_row_lockouts"],
                    "years_active": sorted(set(row["years"])) if row["years"] else [],
                    "one_two_races": row["one_two_races"][:10] if row["one_two_races"] else [],  # Limit to 10
                    "dominance_rating": "ULTRA_DOMINANT" if row["one_two_finishes"] >= 10 else "DOMINANT" if row["one_two_finishes"] >= 5 else "STRONG" if row["one_two_finishes"] >= 2 else "OCCASIONAL",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting team lockouts: {e}")
        return [{"error": str(e)}]


@tool
async def get_undercut_success(
    year: int,
    event_name: str | None = None,
) -> list[dict]:
    """
    Analyze undercut and overcut effectiveness - position changes after pit stops.

    PERFECT FOR: "Undercut effectiveness", "overcut worked", "pit strategy moves"

    Args:
        year: Season year
        event_name: Optional race filter

    Returns:
        Undercut/overcut success rates by driver.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name) if event_name else None

    try:
        # Look for position changes around stint transitions
        query = """
            WITH stint_transitions AS (
                SELECT
                    l1.session_id,
                    l1.driver_id,
                    l1.lap_number as pit_lap,
                    l1.position as pos_before,
                    l1.stint as stint_before,
                    l2.position as pos_after,
                    l2.stint as stint_after,
                    s.event_name
                FROM lap_times l1
                JOIN lap_times l2 ON l1.session_id = l2.session_id
                    AND l1.driver_id = l2.driver_id
                    AND l2.lap_number = l1.lap_number + 2
                JOIN sessions s ON l1.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l1.stint != l2.stint  -- Stint changed = pit stop
                    AND ($2::text IS NULL OR LOWER(s.event_name) LIKE LOWER('%' || $2 || '%'))
            )
            SELECT
                driver_id,
                COUNT(*) as pit_stops,
                SUM(CASE WHEN pos_before > pos_after THEN 1 ELSE 0 END) as positions_gained_stops,
                SUM(CASE WHEN pos_before < pos_after THEN 1 ELSE 0 END) as positions_lost_stops,
                SUM(CASE WHEN pos_before = pos_after THEN 1 ELSE 0 END) as neutral_stops,
                AVG(pos_before - pos_after) as avg_position_change,
                SUM(pos_before - pos_after) as total_positions_gained
            FROM stint_transitions
            GROUP BY driver_id
            HAVING COUNT(*) >= 2
            ORDER BY avg_position_change DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event)

            if not rows:
                return [{"error": f"No pit strategy data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                total_stops = row["pit_stops"]
                gained = row["positions_gained_stops"] or 0
                lost = row["positions_lost_stops"] or 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "pit_stops": total_stops,
                    "stops_gained_position": gained,
                    "stops_lost_position": lost,
                    "stops_neutral": row["neutral_stops"] or 0,
                    "success_rate_percent": round(gained / total_stops * 100, 1) if total_stops > 0 else 0,
                    "avg_position_change": round(row["avg_position_change"], 2) if row["avg_position_change"] else 0,
                    "total_positions_gained": row["total_positions_gained"] or 0,
                    "pit_strategy_rating": "EXCELLENT" if row["avg_position_change"] and row["avg_position_change"] >= 1 else "GOOD" if row["avg_position_change"] and row["avg_position_change"] > 0 else "NEUTRAL" if row["avg_position_change"] and abs(row["avg_position_change"]) < 0.5 else "POOR",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting undercut success: {e}")
        return [{"error": str(e)}]


@tool
async def get_points_per_start(
    year: int | None = None,
    min_races: int = 10,
) -> list[dict]:
    """
    Calculate points efficiency - average points scored per race start.

    PERFECT FOR: "Points efficiency", "average points per race", "best points scorer"

    Args:
        year: Optional year filter (if None, career stats)
        min_races: Minimum races to qualify

    Returns:
        Points per start rankings showing efficiency.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                r.driver_id,
                array_agg(DISTINCT r.team ORDER BY r.team) as teams,
                COUNT(*) as races,
                SUM(r.points) as total_points,
                AVG(r.points) as points_per_race,
                SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) as podiums,
                MAX(r.points) as best_race_points,
                MIN(CASE WHEN r.points > 0 THEN r.points END) as min_points_finish
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.session_type = 'R'
                AND ($1::int IS NULL OR s.year = $1)
            GROUP BY r.driver_id
            HAVING COUNT(*) >= $2
            ORDER BY AVG(r.points) DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, min_races)

            if not rows:
                return [{"error": "No points data found"}]

            results = []
            for i, row in enumerate(rows):
                ppg = row["points_per_race"] or 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "teams": row["teams"],
                    "races": row["races"],
                    "total_points": row["total_points"] or 0,
                    "points_per_race": round(ppg, 2),
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "best_race_points": row["best_race_points"] or 0,
                    "efficiency_tier": "ELITE" if ppg >= 15 else "EXCELLENT" if ppg >= 10 else "GOOD" if ppg >= 5 else "AVERAGE" if ppg >= 2 else "LOW",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting points per start: {e}")
        return [{"error": str(e)}]


@tool
async def get_final_lap_heroics(
    year: int | None = None,
    top_n: int = 20,
) -> list[dict]:
    """
    Find dramatic final lap position changes - last lap overtakes and drama.

    PERFECT FOR: "Last lap overtakes", "final lap drama", "clutch performance"

    Args:
        year: Optional year filter
        top_n: Number of results to return

    Returns:
        Most dramatic final lap position changes.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            WITH final_laps AS (
                SELECT
                    l.session_id,
                    l.driver_id,
                    l.lap_number,
                    l.position as final_lap_pos,
                    s.event_name,
                    s.year,
                    MAX(l.lap_number) OVER (PARTITION BY l.session_id) as total_laps
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND ($1::int IS NULL OR s.year = $1)
            ),
            penultimate_laps AS (
                SELECT
                    l.session_id,
                    l.driver_id,
                    l.position as penultimate_pos
                FROM lap_times l
                JOIN final_laps fl ON l.session_id = fl.session_id
                    AND l.driver_id = fl.driver_id
                    AND l.lap_number = fl.total_laps - 1
                WHERE fl.lap_number = fl.total_laps
            ),
            position_changes AS (
                SELECT
                    fl.driver_id,
                    fl.event_name,
                    fl.year,
                    pl.penultimate_pos,
                    fl.final_lap_pos,
                    pl.penultimate_pos - fl.final_lap_pos as positions_gained,
                    r.team,
                    r.points
                FROM final_laps fl
                JOIN penultimate_laps pl ON fl.session_id = pl.session_id
                    AND fl.driver_id = pl.driver_id
                JOIN results r ON fl.session_id = r.session_id
                    AND fl.driver_id = r.driver_id
                WHERE fl.lap_number = fl.total_laps
                    AND pl.penultimate_pos != fl.final_lap_pos
            )
            SELECT *
            FROM position_changes
            WHERE positions_gained != 0
            ORDER BY ABS(positions_gained) DESC, positions_gained DESC
            LIMIT $2
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, top_n)

            if not rows:
                return [{"message": "No final lap drama found"}]

            results = []
            for i, row in enumerate(rows):
                gained = row["positions_gained"]

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "race": f"{row['year']} {row['event_name']}",
                    "penultimate_lap_position": f"P{row['penultimate_pos']}",
                    "final_position": f"P{row['final_lap_pos']}",
                    "positions_changed": gained,
                    "direction": "GAINED" if gained > 0 else "LOST",
                    "points_impact": row["points"] or 0,
                    "drama_rating": "LEGENDARY" if abs(gained) >= 3 else "DRAMATIC" if abs(gained) >= 2 else "EXCITING",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting final lap heroics: {e}")
        return [{"error": str(e)}]


@tool
async def get_clean_weekend_rate(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze incident-free race completion - clean execution without mistakes.

    PERFECT FOR: "Incident-free races", "clean execution", "no mistakes"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Clean weekend rates showing consistency of execution.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # A "clean weekend" = finished race, no position loss from grid, no DNF
        query = """
            SELECT
                r.driver_id,
                r.team,
                COUNT(*) as races,
                SUM(CASE WHEN r.position IS NOT NULL AND r.position <= 20 THEN 1 ELSE 0 END) as finished,
                SUM(CASE WHEN r.position IS NULL OR r.position > 20 THEN 1 ELSE 0 END) as dnfs,
                SUM(CASE WHEN r.position IS NOT NULL AND r.grid_position IS NOT NULL
                         AND r.position <= r.grid_position THEN 1 ELSE 0 END) as maintained_or_gained,
                SUM(CASE WHEN r.position IS NOT NULL AND r.grid_position IS NOT NULL
                         AND r.position < r.grid_position THEN 1 ELSE 0 END) as gained_positions,
                AVG(CASE WHEN r.position IS NOT NULL THEN r.grid_position - r.position END) as avg_position_change
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND ($2::text IS NULL OR r.driver_id = $2)
            GROUP BY r.driver_id, r.team
            HAVING COUNT(*) >= 5
            ORDER BY SUM(CASE WHEN r.position IS NOT NULL AND r.position <= 20 THEN 1 ELSE 0 END)::float / COUNT(*) DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                races = row["races"]
                finished = row["finished"]
                maintained = row["maintained_or_gained"] or 0

                finish_rate = (finished / races * 100) if races > 0 else 0
                clean_rate = (maintained / races * 100) if races > 0 else 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": races,
                    "finished": finished,
                    "dnfs": row["dnfs"],
                    "finish_rate_percent": round(finish_rate, 1),
                    "maintained_or_gained_position": maintained,
                    "clean_weekend_rate_percent": round(clean_rate, 1),
                    "races_with_position_gain": row["gained_positions"] or 0,
                    "avg_position_change": round(row["avg_position_change"], 2) if row["avg_position_change"] else 0,
                    "execution_rating": "FLAWLESS" if clean_rate >= 80 else "EXCELLENT" if clean_rate >= 60 else "GOOD" if clean_rate >= 40 else "INCONSISTENT",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting clean weekend rate: {e}")
        return [{"error": str(e)}]


# ============================================================
# GRID POSITION & CONVERSION ANALYSIS TOOLS
# ============================================================

@tool
async def get_pole_to_win_conversion(
    year: int | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze pole position to win conversion rates.

    PERFECT FOR: "Pole to win rate", "converting poles", "pole advantage"

    Args:
        year: Optional year filter
        driver_id: Optional driver filter

    Returns:
        Pole to win conversion statistics.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            SELECT
                r.driver_id,
                array_agg(DISTINCT r.team ORDER BY r.team) as teams,
                COUNT(*) FILTER (WHERE r.grid_position = 1) as poles,
                COUNT(*) FILTER (WHERE r.grid_position = 1 AND r.position = 1) as pole_wins,
                COUNT(*) FILTER (WHERE r.grid_position = 1 AND r.position <= 3) as pole_podiums,
                COUNT(*) FILTER (WHERE r.position = 1) as total_wins,
                COUNT(*) as races
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.session_type = 'R'
                AND ($1::int IS NULL OR s.year = $1)
                AND ($2::text IS NULL OR r.driver_id = $2)
            GROUP BY r.driver_id
            HAVING COUNT(*) FILTER (WHERE r.grid_position = 1) >= 1
            ORDER BY COUNT(*) FILTER (WHERE r.grid_position = 1) DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": "No pole position data found"}]

            results = []
            for i, row in enumerate(rows):
                poles = row["poles"]
                pole_wins = row["pole_wins"]
                conversion_rate = (pole_wins / poles * 100) if poles > 0 else 0
                podium_rate = (row["pole_podiums"] / poles * 100) if poles > 0 else 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "teams": row["teams"],
                    "poles": poles,
                    "wins_from_pole": pole_wins,
                    "podiums_from_pole": row["pole_podiums"],
                    "pole_to_win_percent": round(conversion_rate, 1),
                    "pole_to_podium_percent": round(podium_rate, 1),
                    "total_wins": row["total_wins"],
                    "wins_not_from_pole": row["total_wins"] - pole_wins,
                    "conversion_rating": "EXCEPTIONAL" if conversion_rate >= 70 else "STRONG" if conversion_rate >= 50 else "AVERAGE" if conversion_rate >= 30 else "WEAK",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting pole to win conversion: {e}")
        return [{"error": str(e)}]


@tool
async def get_grid_position_advantage(
    year: int | None = None,
) -> list[dict]:
    """
    Analyze win probability and points by starting grid position.

    PERFECT FOR: "Front row advantage", "win rate from P3", "grid position value"

    Args:
        year: Optional year filter

    Returns:
        Statistics by grid position showing win rates and expected points.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            SELECT
                r.grid_position,
                COUNT(*) as races,
                SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) as podiums,
                SUM(CASE WHEN r.position <= 10 THEN 1 ELSE 0 END) as points_finishes,
                AVG(r.position) as avg_finish,
                AVG(r.points) as avg_points,
                AVG(r.grid_position - r.position) as avg_positions_gained
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.session_type = 'R'
                AND r.grid_position IS NOT NULL
                AND r.grid_position <= 20
                AND r.position IS NOT NULL
                AND ($1::int IS NULL OR s.year = $1)
            GROUP BY r.grid_position
            ORDER BY r.grid_position
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year)

            if not rows:
                return [{"error": "No grid position data found"}]

            results = []
            for row in rows:
                races = row["races"]
                win_rate = (row["wins"] / races * 100) if races > 0 else 0
                podium_rate = (row["podiums"] / races * 100) if races > 0 else 0

                results.append({
                    "grid_position": f"P{row['grid_position']}",
                    "sample_size": races,
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "points_finishes": row["points_finishes"],
                    "win_rate_percent": round(win_rate, 1),
                    "podium_rate_percent": round(podium_rate, 1),
                    "avg_finish_position": round(row["avg_finish"], 2),
                    "avg_points": round(row["avg_points"], 2) if row["avg_points"] else 0,
                    "avg_positions_change": round(row["avg_positions_gained"], 2) if row["avg_positions_gained"] else 0,
                    "value_tier": "PREMIUM" if row["grid_position"] <= 3 else "HIGH" if row["grid_position"] <= 6 else "MEDIUM" if row["grid_position"] <= 10 else "LOW",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting grid position advantage: {e}")
        return [{"error": str(e)}]


# Circuit type classifications
STREET_CIRCUITS = ["Monaco", "Singapore", "Azerbaijan", "Saudi Arabia", "Las Vegas", "Miami"]
POWER_CIRCUITS = ["Monza", "Spa", "Baku", "Jeddah", "Las Vegas", "Mexico"]
DOWNFORCE_CIRCUITS = ["Monaco", "Hungary", "Singapore", "Spain"]
HIGH_ALTITUDE = ["Mexico", "Brazil"]


@tool
async def get_circuit_type_performance(
    year: int | None = None,
    driver_id: str | None = None,
    circuit_type: str = "street",
) -> list[dict]:
    """
    Analyze driver performance by circuit type (street, power, downforce).

    PERFECT FOR: "Street circuit specialist", "power track performance", "Monaco specialist"

    Args:
        year: Optional year filter
        driver_id: Optional driver filter
        circuit_type: "street", "power", "downforce", or "high_altitude"

    Returns:
        Performance statistics for the specified circuit type.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    # Select circuit list based on type
    if circuit_type.lower() == "street":
        circuits = STREET_CIRCUITS
    elif circuit_type.lower() == "power":
        circuits = POWER_CIRCUITS
    elif circuit_type.lower() == "downforce":
        circuits = DOWNFORCE_CIRCUITS
    elif circuit_type.lower() == "high_altitude":
        circuits = HIGH_ALTITUDE
    else:
        circuits = STREET_CIRCUITS

    try:
        # Build circuit condition
        circuit_conditions = " OR ".join([f"LOWER(s.event_name) LIKE LOWER('%{c}%')" for c in circuits])

        query = f"""
            WITH circuit_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.event_name,
                    r.position,
                    r.points,
                    r.grid_position
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.session_type = 'R'
                    AND ({circuit_conditions})
                    AND ($1::int IS NULL OR s.year = $1)
                    AND ($2::text IS NULL OR r.driver_id = $2)
                    AND r.position IS NOT NULL
            )
            SELECT
                driver_id,
                array_agg(DISTINCT team ORDER BY team) as teams,
                COUNT(*) as races,
                SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) as podiums,
                SUM(points) as total_points,
                AVG(position) as avg_finish,
                AVG(grid_position) as avg_grid,
                array_agg(DISTINCT event_name) as circuits_raced
            FROM circuit_results
            GROUP BY driver_id
            HAVING COUNT(*) >= 1
            ORDER BY AVG(position) ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No {circuit_type} circuit data found"}]

            results = []
            for i, row in enumerate(rows):
                races = row["races"]
                win_rate = (row["wins"] / races * 100) if races > 0 else 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "teams": row["teams"],
                    "circuit_type": circuit_type.upper(),
                    "races": races,
                    "wins": row["wins"],
                    "podiums": row["podiums"],
                    "total_points": row["total_points"] or 0,
                    "avg_finish": round(row["avg_finish"], 2),
                    "avg_grid": round(row["avg_grid"], 2) if row["avg_grid"] else None,
                    "win_rate_percent": round(win_rate, 1),
                    "circuits": row["circuits_raced"],
                    "specialist_rating": "MASTER" if row["avg_finish"] <= 3 else "SPECIALIST" if row["avg_finish"] <= 5 else "STRONG" if row["avg_finish"] <= 8 else "AVERAGE",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting circuit type performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_q3_shootout_performance(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze Q3 qualifying shootout performance - who delivers under pressure.

    PERFECT FOR: "Q3 specialist", "qualifying shootout", "final lap magic"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Q3 performance statistics showing clutch qualifying ability.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Compare qualifying position to typical pace
        query = """
            WITH quali_results AS (
                SELECT
                    r.driver_id,
                    r.team,
                    s.event_name,
                    r.grid_position,
                    r.position as race_position
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND r.grid_position IS NOT NULL
                    AND ($2::text IS NULL OR r.driver_id = $2)
            )
            SELECT
                driver_id,
                MAX(team) as team,
                COUNT(*) as sessions,
                SUM(CASE WHEN grid_position = 1 THEN 1 ELSE 0 END) as poles,
                SUM(CASE WHEN grid_position <= 3 THEN 1 ELSE 0 END) as front_row,
                SUM(CASE WHEN grid_position <= 10 THEN 1 ELSE 0 END) as q3_appearances,
                AVG(grid_position) as avg_grid,
                MIN(grid_position) as best_grid,
                STDDEV(grid_position) as grid_variance
            FROM quali_results
            GROUP BY driver_id
            HAVING COUNT(*) >= 5
            ORDER BY AVG(grid_position) ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No qualifying data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                sessions = row["sessions"]
                q3_rate = (row["q3_appearances"] / sessions * 100) if sessions > 0 else 0
                pole_rate = (row["poles"] / sessions * 100) if sessions > 0 else 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "sessions": sessions,
                    "poles": row["poles"],
                    "front_row_starts": row["front_row"],
                    "q3_appearances": row["q3_appearances"],
                    "q3_rate_percent": round(q3_rate, 1),
                    "pole_rate_percent": round(pole_rate, 1),
                    "avg_grid": round(row["avg_grid"], 2),
                    "best_grid": f"P{row['best_grid']}",
                    "consistency": round(row["grid_variance"], 2) if row["grid_variance"] else 0,
                    "shootout_rating": "ELITE" if row["avg_grid"] <= 3 else "STRONG" if row["avg_grid"] <= 6 else "SOLID" if row["avg_grid"] <= 10 else "STRUGGLING",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting Q3 shootout performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_race_pace_vs_quali_pace(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Compare qualifying performance to race performance - find "race drivers" vs "qualifiers".

    PERFECT FOR: "Race driver vs qualifier", "Sunday driver", "better in races"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Comparison of qualifying vs race performance.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            SELECT
                r.driver_id,
                r.team,
                COUNT(*) as races,
                AVG(r.grid_position) as avg_quali,
                AVG(r.position) as avg_race,
                AVG(r.grid_position - r.position) as avg_positions_gained,
                SUM(CASE WHEN r.position < r.grid_position THEN 1 ELSE 0 END) as races_gained,
                SUM(CASE WHEN r.position > r.grid_position THEN 1 ELSE 0 END) as races_lost,
                SUM(CASE WHEN r.position = r.grid_position THEN 1 ELSE 0 END) as races_held,
                SUM(r.points) as total_points
            FROM results r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.year = $1
                AND s.session_type = 'R'
                AND r.grid_position IS NOT NULL
                AND r.position IS NOT NULL
                AND ($2::text IS NULL OR r.driver_id = $2)
            GROUP BY r.driver_id, r.team
            HAVING COUNT(*) >= 5
            ORDER BY AVG(r.grid_position - r.position) DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No pace comparison data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                avg_gain = row["avg_positions_gained"] or 0
                quali_rank = row["avg_quali"]
                race_rank = row["avg_race"]

                # Determine driver type
                if avg_gain >= 2:
                    driver_type = "RACE_SPECIALIST"
                elif avg_gain >= 0.5:
                    driver_type = "RACE_STRONGER"
                elif avg_gain >= -0.5:
                    driver_type = "BALANCED"
                elif avg_gain >= -2:
                    driver_type = "QUALI_STRONGER"
                else:
                    driver_type = "QUALI_SPECIALIST"

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "avg_qualifying": round(quali_rank, 2) if quali_rank else None,
                    "avg_race_finish": round(race_rank, 2) if race_rank else None,
                    "avg_positions_gained": round(avg_gain, 2),
                    "races_gained_positions": row["races_gained"],
                    "races_lost_positions": row["races_lost"],
                    "races_held_position": row["races_held"],
                    "total_points": row["total_points"] or 0,
                    "driver_type": driver_type,
                    "race_craft_rating": "EXCEPTIONAL" if avg_gain >= 3 else "STRONG" if avg_gain >= 1 else "AVERAGE" if avg_gain >= -1 else "WEAK",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting race pace vs quali pace: {e}")
        return [{"error": str(e)}]


@tool
async def get_position_battle_stats(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze wheel-to-wheel racing - position changes and battles during races.

    PERFECT FOR: "Most battles", "wheel-to-wheel", "position swaps", "racing intensity"

    Args:
        year: Season year
        driver_id: Optional driver filter

    Returns:
        Position battle statistics showing racing intensity.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Count position changes by looking at lap-by-lap position changes
        query = """
            WITH position_changes AS (
                SELECT
                    l.driver_id,
                    l.session_id,
                    l.lap_number,
                    l.position,
                    LAG(l.position) OVER (PARTITION BY l.session_id, l.driver_id ORDER BY l.lap_number) as prev_position,
                    s.event_name
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.position IS NOT NULL
                    AND ($2::text IS NULL OR l.driver_id = $2)
            ),
            battle_stats AS (
                SELECT
                    driver_id,
                    COUNT(*) as total_laps,
                    SUM(CASE WHEN position != prev_position THEN 1 ELSE 0 END) as position_changes,
                    SUM(CASE WHEN position < prev_position THEN 1 ELSE 0 END) as positions_gained,
                    SUM(CASE WHEN position > prev_position THEN 1 ELSE 0 END) as positions_lost,
                    COUNT(DISTINCT session_id) as races
                FROM position_changes
                WHERE prev_position IS NOT NULL
                GROUP BY driver_id
            )
            SELECT
                bs.*,
                r.team
            FROM battle_stats bs
            JOIN (
                SELECT DISTINCT driver_id, team
                FROM results r2
                JOIN sessions s2 ON r2.session_id = s2.session_id
                WHERE s2.year = $1 AND s2.session_type = 'R'
            ) r ON bs.driver_id = r.driver_id
            ORDER BY position_changes DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"error": f"No battle stats found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                total_changes = row["position_changes"] or 0
                races = row["races"] or 1
                changes_per_race = total_changes / races

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": races,
                    "total_laps": row["total_laps"],
                    "position_changes": total_changes,
                    "positions_gained": row["positions_gained"] or 0,
                    "positions_lost": row["positions_lost"] or 0,
                    "net_positions": (row["positions_gained"] or 0) - (row["positions_lost"] or 0),
                    "changes_per_race": round(changes_per_race, 1),
                    "battle_intensity": "VERY_HIGH" if changes_per_race >= 15 else "HIGH" if changes_per_race >= 10 else "MEDIUM" if changes_per_race >= 5 else "LOW",
                    "battle_success_rate": round((row["positions_gained"] or 0) / max(1, total_changes) * 100, 1),
                })

            return results

    except Exception as e:
        logger.error(f"Error getting position battle stats: {e}")
        return [{"error": str(e)}]


@tool
async def get_average_race_position(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Calculate average running position throughout races (not just finish position).

    PERFECT FOR: "Average running position", "race position vs finish", "where they actually ran"

    Args:
        year: Season year
        event_name: Optional race filter
        driver_id: Optional driver filter

    Returns:
        Average race position analysis showing where drivers actually ran.
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    event = normalize_event_name(event_name) if event_name else None
    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH race_positions AS (
                SELECT
                    l.driver_id,
                    l.session_id,
                    s.event_name,
                    AVG(l.position) as avg_running_position,
                    MIN(l.position) as best_position,
                    MAX(l.position) as worst_position,
                    STDDEV(l.position) as position_variance,
                    COUNT(*) as laps
                FROM lap_times l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.position IS NOT NULL
                    AND ($2::text IS NULL OR LOWER(s.event_name) LIKE LOWER('%' || $2 || '%'))
                    AND ($3::text IS NULL OR l.driver_id = $3)
                GROUP BY l.driver_id, l.session_id, s.event_name
            ),
            with_results AS (
                SELECT
                    rp.*,
                    r.position as finish_position,
                    r.grid_position,
                    r.team,
                    r.points
                FROM race_positions rp
                JOIN results r ON rp.session_id = r.session_id AND rp.driver_id = r.driver_id
            )
            SELECT
                driver_id,
                MAX(team) as team,
                COUNT(*) as races,
                AVG(avg_running_position) as overall_avg_position,
                AVG(finish_position) as avg_finish,
                AVG(grid_position) as avg_grid,
                AVG(finish_position - avg_running_position) as finish_vs_avg_delta,
                SUM(points) as total_points
            FROM with_results
            GROUP BY driver_id
            HAVING COUNT(*) >= 1
            ORDER BY AVG(avg_running_position) ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"error": f"No race position data found for {year}"}]

            results = []
            for i, row in enumerate(rows):
                avg_run = row["overall_avg_position"] or 0
                avg_finish = row["avg_finish"] or 0
                delta = row["finish_vs_avg_delta"] or 0

                results.append({
                    "rank": i + 1,
                    "driver": row["driver_id"],
                    "team": row["team"],
                    "races": row["races"],
                    "avg_running_position": round(avg_run, 2),
                    "avg_finish_position": round(avg_finish, 2),
                    "avg_grid_position": round(row["avg_grid"], 2) if row["avg_grid"] else None,
                    "finish_vs_running_delta": round(delta, 2),
                    "total_points": row["total_points"] or 0,
                    "race_execution": "STRONG_FINISHER" if delta < -1 else "CONSISTENT" if abs(delta) <= 1 else "FADES_LATE" if delta > 1 else "TYPICAL",
                })

            return results

    except Exception as e:
        logger.error(f"Error getting average race position: {e}")
        return [{"error": str(e)}]


@tool
async def get_points_trajectory(
    driver_id: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict:
    """
    Track career points accumulation over time - milestone tracking.

    PERFECT FOR: "Career points curve", "points over time", "milestone races"

    Args:
        driver_id: Driver code (e.g., "VER", "HAM")
        start_year: Optional start year
        end_year: Optional end year

    Returns:
        Career points trajectory with milestones.
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    driver = normalize_driver_id(driver_id)

    try:
        query = """
            WITH career_points AS (
                SELECT
                    r.driver_id,
                    s.year,
                    s.round_number,
                    s.event_name,
                    r.points,
                    r.position,
                    r.team,
                    SUM(r.points) OVER (
                        PARTITION BY r.driver_id
                        ORDER BY s.year, s.round_number
                    ) as cumulative_points,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.driver_id
                        ORDER BY s.year, s.round_number
                    ) as race_number
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE r.driver_id = $1
                    AND s.session_type = 'R'
                    AND ($2::int IS NULL OR s.year >= $2)
                    AND ($3::int IS NULL OR s.year <= $3)
                ORDER BY s.year, s.round_number
            )
            SELECT *
            FROM career_points
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, driver, start_year, end_year)

            if not rows:
                return {"error": f"No career data found for {driver_id}"}

            trajectory = []
            milestones = []
            milestone_thresholds = [100, 250, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
            passed_milestones = set()

            for row in rows:
                cum_points = row["cumulative_points"] or 0

                # Check for milestones
                for threshold in milestone_thresholds:
                    if cum_points >= threshold and threshold not in passed_milestones:
                        milestones.append({
                            "milestone": f"{threshold} points",
                            "race": f"{row['year']} {row['event_name']}",
                            "race_number": row["race_number"],
                            "actual_points": cum_points,
                        })
                        passed_milestones.add(threshold)

                trajectory.append({
                    "race_number": row["race_number"],
                    "year": row["year"],
                    "race": row["event_name"],
                    "team": row["team"],
                    "race_points": row["points"] or 0,
                    "position": row["position"],
                    "cumulative_points": cum_points,
                })

            final_points = trajectory[-1]["cumulative_points"] if trajectory else 0
            total_races = len(trajectory)

            return {
                "driver": driver,
                "total_points": final_points,
                "total_races": total_races,
                "points_per_race": round(final_points / max(1, total_races), 2),
                "milestones": milestones,
                "trajectory": trajectory[-20:] if len(trajectory) > 20 else trajectory,  # Last 20 races
                "first_race": f"{trajectory[0]['year']} {trajectory[0]['race']}" if trajectory else None,
                "career_span": f"{trajectory[0]['year']}-{trajectory[-1]['year']}" if trajectory else None,
            }

    except Exception as e:
        logger.error(f"Error getting points trajectory: {e}")
        return {"error": str(e)}


# =============================================================================
# RACE DYNAMICS & MICRO-ANALYSIS TOOLS
# =============================================================================


@tool
async def get_drs_effectiveness(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze DRS effectiveness - overtakes, position changes in DRS zones.
    Uses lap-by-lap position changes as proxy for DRS-assisted moves.

    PERFECT FOR: "DRS effectiveness", "DRS train", "DRS overtakes"

    Args:
        year: Season year
        event_name: Optional specific race
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name) if event_name else None

    try:
        # Analyze position changes lap-by-lap as DRS effectiveness proxy
        query = """
            WITH lap_positions AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.position,
                    s.event_name,
                    LAG(l.position) OVER (
                        PARTITION BY l.driver_id, s.session_id
                        ORDER BY l.lap_number
                    ) as prev_position
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.lap_number > 1
                    AND ($2::text IS NULL OR s.event_name ILIKE '%' || $2 || '%')
                    AND ($3::text IS NULL OR l.driver_id = $3)
            ),
            overtakes AS (
                SELECT
                    driver_id,
                    event_name,
                    COUNT(*) FILTER (WHERE position < prev_position) as positions_gained,
                    COUNT(*) FILTER (WHERE position > prev_position) as positions_lost,
                    COUNT(*) FILTER (WHERE position < prev_position) -
                        COUNT(*) FILTER (WHERE position > prev_position) as net_positions
                FROM lap_positions
                WHERE prev_position IS NOT NULL
                GROUP BY driver_id, event_name
            )
            SELECT
                driver_id,
                event_name,
                positions_gained,
                positions_lost,
                net_positions,
                CASE WHEN positions_gained + positions_lost > 0
                    THEN ROUND(positions_gained::numeric / (positions_gained + positions_lost) * 100, 1)
                    ELSE 0 END as attack_success_rate
            FROM overtakes
            ORDER BY positions_gained DESC
            LIMIT 30
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            return [
                {
                    "driver": row["driver_id"],
                    "race": row["event_name"],
                    "positions_gained": row["positions_gained"],
                    "positions_lost": row["positions_lost"],
                    "net_positions": row["net_positions"],
                    "attack_success_rate": f"{row['attack_success_rate']}%",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing DRS effectiveness: {e}")
        return [{"error": str(e)}]


@tool
async def get_tire_warmup_specialist(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze tire warm-up performance - outlap pace after pit stops.
    Identifies drivers who get tires up to temperature quickly.

    PERFECT FOR: "tire warm-up", "outlap pace", "cold tire performance"

    Args:
        year: Season year
        event_name: Optional specific race
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name) if event_name else None

    try:
        query = """
            WITH pit_laps AS (
                SELECT
                    p.driver_id,
                    p.lap_number as pit_lap,
                    s.session_id,
                    s.event_name
                FROM pit_stops p
                JOIN sessions s ON p.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR s.event_name ILIKE '%' || $2 || '%')
                    AND ($3::text IS NULL OR p.driver_id = $3)
            ),
            outlap_times AS (
                SELECT
                    pl.driver_id,
                    pl.event_name,
                    l.lap_time_seconds,
                    l.lap_number as outlap_number
                FROM pit_laps pl
                JOIN laps l ON pl.session_id = l.session_id
                    AND pl.driver_id = l.driver_id
                    AND l.lap_number = pl.pit_lap + 1
                WHERE l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
            ),
            driver_outlaps AS (
                SELECT
                    driver_id,
                    COUNT(*) as outlap_count,
                    AVG(lap_time_seconds) as avg_outlap_time,
                    MIN(lap_time_seconds) as best_outlap_time,
                    STDDEV(lap_time_seconds) as outlap_consistency
                FROM outlap_times
                GROUP BY driver_id
                HAVING COUNT(*) >= 2
            )
            SELECT
                driver_id,
                outlap_count,
                avg_outlap_time,
                best_outlap_time,
                outlap_consistency,
                RANK() OVER (ORDER BY avg_outlap_time ASC) as warmup_rank
            FROM driver_outlaps
            ORDER BY avg_outlap_time ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"message": "No outlap data found"}]

            # Calculate field average for comparison
            field_avg = sum(r["avg_outlap_time"] for r in rows) / len(rows)

            return [
                {
                    "rank": row["warmup_rank"],
                    "driver": row["driver_id"],
                    "outlap_count": row["outlap_count"],
                    "avg_outlap_time": round(row["avg_outlap_time"], 3),
                    "best_outlap_time": round(row["best_outlap_time"], 3),
                    "consistency": round(row["outlap_consistency"], 3) if row["outlap_consistency"] else None,
                    "vs_field_avg": f"{row['avg_outlap_time'] - field_avg:+.3f}s",
                    "warmup_rating": "Excellent" if row["warmup_rank"] <= 3 else "Good" if row["warmup_rank"] <= 8 else "Average",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing tire warm-up: {e}")
        return [{"error": str(e)}]


@tool
async def get_qualifying_improvement(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze qualifying session improvement - Q1 to Q2 to Q3 progression.
    Identifies drivers who "peak in Q3" vs those who plateau early.

    PERFECT FOR: "Q1 to Q3 improvement", "qualifying progression", "peaks in Q3"

    Args:
        year: Season year
        event_name: Optional specific race
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name) if event_name else None

    try:
        query = """
            WITH quali_times AS (
                SELECT
                    l.driver_id,
                    s.event_name,
                    s.session_type,
                    MIN(l.lap_time_seconds) as best_time
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type IN ('Q1', 'Q2', 'Q3')
                    AND l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
                    AND ($2::text IS NULL OR s.event_name ILIKE '%' || $2 || '%')
                    AND ($3::text IS NULL OR l.driver_id = $3)
                GROUP BY l.driver_id, s.event_name, s.session_type
            ),
            pivoted AS (
                SELECT
                    driver_id,
                    event_name,
                    MAX(CASE WHEN session_type = 'Q1' THEN best_time END) as q1_time,
                    MAX(CASE WHEN session_type = 'Q2' THEN best_time END) as q2_time,
                    MAX(CASE WHEN session_type = 'Q3' THEN best_time END) as q3_time
                FROM quali_times
                GROUP BY driver_id, event_name
            ),
            improvements AS (
                SELECT
                    driver_id,
                    event_name,
                    q1_time,
                    q2_time,
                    q3_time,
                    q1_time - q2_time as q1_to_q2_gain,
                    q2_time - q3_time as q2_to_q3_gain,
                    q1_time - COALESCE(q3_time, q2_time) as total_improvement
                FROM pivoted
                WHERE q1_time IS NOT NULL
            )
            SELECT
                driver_id,
                COUNT(*) as sessions,
                AVG(q1_to_q2_gain) as avg_q1_to_q2,
                AVG(q2_to_q3_gain) as avg_q2_to_q3,
                AVG(total_improvement) as avg_total_improvement,
                MAX(total_improvement) as best_improvement
            FROM improvements
            GROUP BY driver_id
            ORDER BY avg_total_improvement DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            return [
                {
                    "driver": row["driver_id"],
                    "quali_sessions": row["sessions"],
                    "avg_q1_to_q2_gain": f"{row['avg_q1_to_q2']:.3f}s" if row["avg_q1_to_q2"] else "N/A",
                    "avg_q2_to_q3_gain": f"{row['avg_q2_to_q3']:.3f}s" if row["avg_q2_to_q3"] else "N/A",
                    "avg_total_improvement": f"{row['avg_total_improvement']:.3f}s" if row["avg_total_improvement"] else "N/A",
                    "best_improvement": f"{row['best_improvement']:.3f}s" if row["best_improvement"] else "N/A",
                    "q3_specialist": "Yes" if row["avg_q2_to_q3"] and row["avg_q2_to_q3"] > 0.2 else "No",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing qualifying improvement: {e}")
        return [{"error": str(e)}]


@tool
async def get_theoretical_best_lap(
    year: int,
    event_name: str,
    session_type: str = "Q",
    driver_id: str | None = None,
) -> list[dict]:
    """
    Calculate theoretical best lap from best individual sectors.
    Shows potential pole time vs actual pole time.

    PERFECT FOR: "theoretical best", "best sectors combined", "potential pole"

    Args:
        year: Season year
        event_name: Race name (e.g., "Monaco", "Silverstone")
        session_type: Session type (Q for qualifying, R for race)
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name)

    try:
        query = """
            WITH best_sectors AS (
                SELECT
                    l.driver_id,
                    MIN(l.sector_1_time) as best_s1,
                    MIN(l.sector_2_time) as best_s2,
                    MIN(l.sector_3_time) as best_s3,
                    MIN(l.lap_time_seconds) as actual_best_lap
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.event_name ILIKE '%' || $2 || '%'
                    AND s.session_type LIKE $3 || '%'
                    AND l.sector_1_time IS NOT NULL
                    AND l.sector_2_time IS NOT NULL
                    AND l.sector_3_time IS NOT NULL
                    AND ($4::text IS NULL OR l.driver_id = $4)
                GROUP BY l.driver_id
            )
            SELECT
                driver_id,
                best_s1,
                best_s2,
                best_s3,
                best_s1 + best_s2 + best_s3 as theoretical_best,
                actual_best_lap,
                actual_best_lap - (best_s1 + best_s2 + best_s3) as time_left_on_table,
                RANK() OVER (ORDER BY best_s1 + best_s2 + best_s3 ASC) as theoretical_rank,
                RANK() OVER (ORDER BY actual_best_lap ASC) as actual_rank
            FROM best_sectors
            ORDER BY theoretical_best ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, session_type, driver)

            if not rows:
                return [{"message": f"No sector data found for {event_name} {year}"}]

            # Find overall theoretical best (best of each sector from any driver)
            overall_best_s1 = min(r["best_s1"] for r in rows)
            overall_best_s2 = min(r["best_s2"] for r in rows)
            overall_best_s3 = min(r["best_s3"] for r in rows)
            ultimate_theoretical = overall_best_s1 + overall_best_s2 + overall_best_s3

            results = [
                {
                    "theoretical_rank": row["theoretical_rank"],
                    "actual_rank": row["actual_rank"],
                    "driver": row["driver_id"],
                    "best_s1": round(row["best_s1"], 3),
                    "best_s2": round(row["best_s2"], 3),
                    "best_s3": round(row["best_s3"], 3),
                    "theoretical_best": round(row["theoretical_best"], 3),
                    "actual_best": round(row["actual_best_lap"], 3),
                    "time_left_on_table": f"+{row['time_left_on_table']:.3f}s",
                    "position_change": row["actual_rank"] - row["theoretical_rank"],
                }
                for row in rows
            ]

            # Add ultimate theoretical lap info
            results.insert(0, {
                "note": "ULTIMATE THEORETICAL LAP",
                "best_s1": round(overall_best_s1, 3),
                "best_s2": round(overall_best_s2, 3),
                "best_s3": round(overall_best_s3, 3),
                "ultimate_time": round(ultimate_theoretical, 3),
            })

            return results

    except Exception as e:
        logger.error(f"Error calculating theoretical best lap: {e}")
        return [{"error": str(e)}]


@tool
async def get_race_pace_degradation(
    year: int,
    event_name: str,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze pace degradation through race stints.
    Shows how lap times increase due to fuel burn and tire wear.

    PERFECT FOR: "pace degradation", "tire drop-off", "fuel effect"

    Args:
        year: Season year
        event_name: Race name (e.g., "Monaco", "Silverstone")
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name)

    try:
        query = """
            WITH race_laps AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.lap_time_seconds,
                    l.compound,
                    NTILE(4) OVER (PARTITION BY l.driver_id ORDER BY l.lap_number) as stint_quarter
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.event_name ILIKE '%' || $2 || '%'
                    AND s.session_type = 'R'
                    AND l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
                    AND l.lap_time_seconds < 200
                    AND l.is_pit_in_lap = false
                    AND l.is_pit_out_lap = false
                    AND ($3::text IS NULL OR l.driver_id = $3)
            ),
            quarter_pace AS (
                SELECT
                    driver_id,
                    stint_quarter,
                    AVG(lap_time_seconds) as avg_pace,
                    MIN(lap_time_seconds) as best_pace,
                    COUNT(*) as lap_count
                FROM race_laps
                GROUP BY driver_id, stint_quarter
            ),
            degradation AS (
                SELECT
                    driver_id,
                    MAX(CASE WHEN stint_quarter = 1 THEN avg_pace END) as q1_pace,
                    MAX(CASE WHEN stint_quarter = 2 THEN avg_pace END) as q2_pace,
                    MAX(CASE WHEN stint_quarter = 3 THEN avg_pace END) as q3_pace,
                    MAX(CASE WHEN stint_quarter = 4 THEN avg_pace END) as q4_pace
                FROM quarter_pace
                GROUP BY driver_id
            )
            SELECT
                driver_id,
                q1_pace,
                q2_pace,
                q3_pace,
                q4_pace,
                q4_pace - q1_pace as total_degradation,
                (q4_pace - q1_pace) / NULLIF(q1_pace, 0) * 100 as degradation_pct
            FROM degradation
            WHERE q1_pace IS NOT NULL AND q4_pace IS NOT NULL
            ORDER BY total_degradation ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"message": f"No degradation data found for {event_name} {year}"}]

            return [
                {
                    "driver": row["driver_id"],
                    "early_race_pace": round(row["q1_pace"], 3),
                    "mid_race_pace": round((row["q2_pace"] + row["q3_pace"]) / 2, 3) if row["q2_pace"] and row["q3_pace"] else None,
                    "late_race_pace": round(row["q4_pace"], 3),
                    "total_degradation": f"+{row['total_degradation']:.3f}s",
                    "degradation_pct": f"+{row['degradation_pct']:.1f}%",
                    "tire_management": "Excellent" if row["total_degradation"] < 1.5 else "Good" if row["total_degradation"] < 2.5 else "Poor",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing pace degradation: {e}")
        return [{"error": str(e)}]


@tool
async def get_red_flag_restart_performance(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze performance on red flag restarts (standing starts mid-race).
    Tracks positions gained/lost on restart laps.

    PERFECT FOR: "red flag restart", "standing restart", "restart performance"

    Args:
        year: Season year
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        # Look for significant position changes after gaps in lap numbers (red flags)
        query = """
            WITH lap_gaps AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.position,
                    s.event_name,
                    LAG(l.lap_number) OVER (
                        PARTITION BY l.driver_id, s.session_id
                        ORDER BY l.lap_number
                    ) as prev_lap_number,
                    LAG(l.position) OVER (
                        PARTITION BY l.driver_id, s.session_id
                        ORDER BY l.lap_number
                    ) as prev_position
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR l.driver_id = $2)
            ),
            restart_laps AS (
                SELECT
                    driver_id,
                    event_name,
                    lap_number as restart_lap,
                    prev_position as position_before,
                    position as position_after,
                    prev_position - position as positions_gained
                FROM lap_gaps
                WHERE prev_lap_number IS NOT NULL
                    AND lap_number - prev_lap_number > 2  -- Gap indicates red flag
                    AND prev_position IS NOT NULL
            )
            SELECT
                driver_id,
                COUNT(*) as restarts,
                SUM(positions_gained) as total_positions_gained,
                AVG(positions_gained) as avg_positions_gained,
                COUNT(*) FILTER (WHERE positions_gained > 0) as restarts_with_gains,
                COUNT(*) FILTER (WHERE positions_gained < 0) as restarts_with_losses,
                MAX(positions_gained) as best_restart,
                MIN(positions_gained) as worst_restart
            FROM restart_laps
            GROUP BY driver_id
            HAVING COUNT(*) >= 1
            ORDER BY avg_positions_gained DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"message": f"No red flag restart data found for {year}"}]

            return [
                {
                    "driver": row["driver_id"],
                    "restarts": row["restarts"],
                    "total_positions_gained": row["total_positions_gained"],
                    "avg_positions_gained": round(row["avg_positions_gained"], 2),
                    "restarts_with_gains": row["restarts_with_gains"],
                    "restarts_with_losses": row["restarts_with_losses"],
                    "best_restart": f"+{row['best_restart']}" if row["best_restart"] > 0 else str(row["best_restart"]),
                    "worst_restart": f"+{row['worst_restart']}" if row["worst_restart"] > 0 else str(row["worst_restart"]),
                    "restart_rating": "Excellent" if row["avg_positions_gained"] > 1 else "Good" if row["avg_positions_gained"] > 0 else "Poor",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing red flag restarts: {e}")
        return [{"error": str(e)}]


@tool
async def get_season_phase_performance(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze performance by season phase (early/mid/late).
    Identifies who improves through season vs who fades.

    PERFECT FOR: "early season form", "late season surge", "season phases"

    Args:
        year: Season year
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH race_results AS (
                SELECT
                    r.driver_id,
                    s.round_number,
                    r.points,
                    r.position,
                    r.grid_position,
                    CASE
                        WHEN s.round_number <= 7 THEN 'early'
                        WHEN s.round_number <= 15 THEN 'mid'
                        ELSE 'late'
                    END as phase
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            phase_stats AS (
                SELECT
                    driver_id,
                    phase,
                    SUM(points) as total_points,
                    AVG(position) as avg_position,
                    AVG(grid_position - position) as avg_positions_gained,
                    COUNT(*) as races
                FROM race_results
                GROUP BY driver_id, phase
            ),
            pivoted AS (
                SELECT
                    driver_id,
                    MAX(CASE WHEN phase = 'early' THEN total_points END) as early_points,
                    MAX(CASE WHEN phase = 'mid' THEN total_points END) as mid_points,
                    MAX(CASE WHEN phase = 'late' THEN total_points END) as late_points,
                    MAX(CASE WHEN phase = 'early' THEN avg_position END) as early_avg_pos,
                    MAX(CASE WHEN phase = 'mid' THEN avg_position END) as mid_avg_pos,
                    MAX(CASE WHEN phase = 'late' THEN avg_position END) as late_avg_pos
                FROM phase_stats
                GROUP BY driver_id
            )
            SELECT
                driver_id,
                COALESCE(early_points, 0) as early_points,
                COALESCE(mid_points, 0) as mid_points,
                COALESCE(late_points, 0) as late_points,
                early_avg_pos,
                mid_avg_pos,
                late_avg_pos,
                COALESCE(late_avg_pos, mid_avg_pos) - COALESCE(early_avg_pos, 10) as position_trend
            FROM pivoted
            ORDER BY (COALESCE(early_points, 0) + COALESCE(mid_points, 0) + COALESCE(late_points, 0)) DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            return [
                {
                    "driver": row["driver_id"],
                    "early_season_points": row["early_points"],
                    "mid_season_points": row["mid_points"],
                    "late_season_points": row["late_points"],
                    "early_avg_position": round(row["early_avg_pos"], 1) if row["early_avg_pos"] else None,
                    "mid_avg_position": round(row["mid_avg_pos"], 1) if row["mid_avg_pos"] else None,
                    "late_avg_position": round(row["late_avg_pos"], 1) if row["late_avg_pos"] else None,
                    "season_trend": "Improving" if row["position_trend"] and row["position_trend"] < -1 else
                                   "Declining" if row["position_trend"] and row["position_trend"] > 1 else "Consistent",
                    "total_points": row["early_points"] + row["mid_points"] + row["late_points"],
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing season phases: {e}")
        return [{"error": str(e)}]


@tool
async def get_back_to_back_performance(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze performance in back-to-back race weekends (double/triple headers).
    Identifies drivers who handle or struggle with consecutive races.

    PERFECT FOR: "back to back races", "double header", "triple header fatigue"

    Args:
        year: Season year
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH race_dates AS (
                SELECT
                    session_id,
                    event_name,
                    round_number,
                    date,
                    LAG(date) OVER (ORDER BY round_number) as prev_race_date,
                    date - LAG(date) OVER (ORDER BY round_number) as days_since_last
                FROM sessions
                WHERE year = $1 AND session_type = 'R'
            ),
            back_to_back AS (
                SELECT
                    session_id,
                    event_name,
                    round_number,
                    CASE WHEN days_since_last <= 8 THEN true ELSE false END as is_back_to_back
                FROM race_dates
            ),
            results_typed AS (
                SELECT
                    r.driver_id,
                    r.points,
                    r.position,
                    btb.is_back_to_back
                FROM results r
                JOIN back_to_back btb ON r.session_id = btb.session_id
                WHERE ($2::text IS NULL OR r.driver_id = $2)
            )
            SELECT
                driver_id,
                COUNT(*) FILTER (WHERE is_back_to_back) as back_to_back_races,
                COUNT(*) FILTER (WHERE NOT is_back_to_back) as standalone_races,
                AVG(points) FILTER (WHERE is_back_to_back) as avg_points_btb,
                AVG(points) FILTER (WHERE NOT is_back_to_back) as avg_points_standalone,
                AVG(position) FILTER (WHERE is_back_to_back) as avg_position_btb,
                AVG(position) FILTER (WHERE NOT is_back_to_back) as avg_position_standalone
            FROM results_typed
            GROUP BY driver_id
            HAVING COUNT(*) FILTER (WHERE is_back_to_back) >= 2
            ORDER BY avg_points_btb DESC NULLS LAST
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"message": f"No back-to-back race data found for {year}"}]

            return [
                {
                    "driver": row["driver_id"],
                    "back_to_back_races": row["back_to_back_races"],
                    "standalone_races": row["standalone_races"],
                    "avg_points_back_to_back": round(row["avg_points_btb"], 1) if row["avg_points_btb"] else 0,
                    "avg_points_standalone": round(row["avg_points_standalone"], 1) if row["avg_points_standalone"] else 0,
                    "points_difference": round((row["avg_points_btb"] or 0) - (row["avg_points_standalone"] or 0), 1),
                    "handles_btb": "Well" if (row["avg_points_btb"] or 0) >= (row["avg_points_standalone"] or 0) else "Struggles",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing back-to-back performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_championship_pressure_performance(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze performance under championship pressure.
    Compares performance when in title contention vs when not.

    PERFECT FOR: "championship pressure", "title fight performance", "pressure handling"

    Args:
        year: Season year
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH cumulative_standings AS (
                SELECT
                    r.driver_id,
                    s.round_number,
                    s.event_name,
                    r.points as race_points,
                    r.position,
                    SUM(r.points) OVER (
                        PARTITION BY r.driver_id
                        ORDER BY s.round_number
                    ) as cumulative_points
                FROM results r
                JOIN sessions s ON r.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR r.driver_id = $2)
            ),
            with_leader AS (
                SELECT
                    cs.*,
                    MAX(cumulative_points) OVER (PARTITION BY round_number) as leader_points,
                    cumulative_points - MAX(cumulative_points) OVER (PARTITION BY round_number) as gap_to_leader
                FROM cumulative_standings cs
            ),
            pressure_classified AS (
                SELECT
                    driver_id,
                    round_number,
                    race_points,
                    position,
                    gap_to_leader,
                    CASE
                        WHEN gap_to_leader >= -50 THEN 'in_contention'
                        ELSE 'out_of_contention'
                    END as pressure_status
                FROM with_leader
            )
            SELECT
                driver_id,
                COUNT(*) FILTER (WHERE pressure_status = 'in_contention') as races_in_contention,
                COUNT(*) FILTER (WHERE pressure_status = 'out_of_contention') as races_out,
                AVG(race_points) FILTER (WHERE pressure_status = 'in_contention') as avg_points_under_pressure,
                AVG(race_points) FILTER (WHERE pressure_status = 'out_of_contention') as avg_points_no_pressure,
                AVG(position) FILTER (WHERE pressure_status = 'in_contention') as avg_position_under_pressure,
                AVG(position) FILTER (WHERE pressure_status = 'out_of_contention') as avg_position_no_pressure
            FROM pressure_classified
            GROUP BY driver_id
            HAVING COUNT(*) FILTER (WHERE pressure_status = 'in_contention') >= 3
            ORDER BY avg_points_under_pressure DESC NULLS LAST
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            if not rows:
                return [{"message": f"No championship pressure data found for {year}"}]

            return [
                {
                    "driver": row["driver_id"],
                    "races_in_title_fight": row["races_in_contention"],
                    "races_out_of_contention": row["races_out"],
                    "avg_points_under_pressure": round(row["avg_points_under_pressure"], 1) if row["avg_points_under_pressure"] else 0,
                    "avg_points_relaxed": round(row["avg_points_no_pressure"], 1) if row["avg_points_no_pressure"] else 0,
                    "pressure_effect": round((row["avg_points_under_pressure"] or 0) - (row["avg_points_no_pressure"] or 0), 1),
                    "handles_pressure": "Thrives" if (row["avg_points_under_pressure"] or 0) > (row["avg_points_no_pressure"] or 0) else
                                       "Struggles" if (row["avg_points_under_pressure"] or 0) < (row["avg_points_no_pressure"] or 0) - 2 else "Neutral",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing championship pressure: {e}")
        return [{"error": str(e)}]


@tool
async def get_pit_exit_performance(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze pit exit and out-lap performance.
    Tracks how quickly drivers get up to speed after stops.

    PERFECT FOR: "pit exit", "out-lap pace", "getting up to speed"

    Args:
        year: Season year
        event_name: Optional specific race
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name) if event_name else None

    try:
        query = """
            WITH pit_data AS (
                SELECT
                    p.driver_id,
                    p.lap_number as pit_lap,
                    p.pit_duration,
                    s.session_id,
                    s.event_name
                FROM pit_stops p
                JOIN sessions s ON p.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR s.event_name ILIKE '%' || $2 || '%')
                    AND ($3::text IS NULL OR p.driver_id = $3)
            ),
            outlap_data AS (
                SELECT
                    pd.driver_id,
                    pd.event_name,
                    pd.pit_duration,
                    l.lap_time_seconds as outlap_time,
                    l2.lap_time_seconds as second_lap_time
                FROM pit_data pd
                JOIN laps l ON pd.session_id = l.session_id
                    AND pd.driver_id = l.driver_id
                    AND l.lap_number = pd.pit_lap + 1
                LEFT JOIN laps l2 ON pd.session_id = l2.session_id
                    AND pd.driver_id = l2.driver_id
                    AND l2.lap_number = pd.pit_lap + 2
                WHERE l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
            )
            SELECT
                driver_id,
                COUNT(*) as pit_stops,
                AVG(pit_duration) as avg_pit_duration,
                AVG(outlap_time) as avg_outlap_time,
                AVG(second_lap_time) as avg_second_lap,
                AVG(outlap_time - second_lap_time) as avg_warmup_delta,
                MIN(outlap_time) as best_outlap
            FROM outlap_data
            GROUP BY driver_id
            HAVING COUNT(*) >= 2
            ORDER BY avg_outlap_time ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"message": "No pit exit data found"}]

            return [
                {
                    "driver": row["driver_id"],
                    "pit_stops": row["pit_stops"],
                    "avg_pit_duration": round(row["avg_pit_duration"], 3) if row["avg_pit_duration"] else None,
                    "avg_outlap_time": round(row["avg_outlap_time"], 3),
                    "avg_second_lap": round(row["avg_second_lap"], 3) if row["avg_second_lap"] else None,
                    "warmup_penalty": f"+{row['avg_warmup_delta']:.3f}s" if row["avg_warmup_delta"] else "N/A",
                    "best_outlap": round(row["best_outlap"], 3),
                    "pit_exit_rating": "Excellent" if row["avg_warmup_delta"] and row["avg_warmup_delta"] < 2 else
                                      "Good" if row["avg_warmup_delta"] and row["avg_warmup_delta"] < 4 else "Average",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing pit exit performance: {e}")
        return [{"error": str(e)}]


@tool
async def get_defensive_driving_stats(
    year: int,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze defensive driving ability - position defense success.
    Tracks how well drivers hold position when under attack.

    PERFECT FOR: "defensive driving", "position defense", "holding position"

    Args:
        year: Season year
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None

    try:
        query = """
            WITH lap_positions AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.position,
                    s.session_id,
                    s.event_name,
                    LAG(l.position) OVER (
                        PARTITION BY l.driver_id, s.session_id
                        ORDER BY l.lap_number
                    ) as prev_position,
                    LEAD(l.position) OVER (
                        PARTITION BY l.driver_id, s.session_id
                        ORDER BY l.lap_number
                    ) as next_position
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND ($2::text IS NULL OR l.driver_id = $2)
            ),
            defense_events AS (
                SELECT
                    driver_id,
                    -- Held position for multiple laps (defensive success)
                    COUNT(*) FILTER (
                        WHERE position = prev_position
                        AND position = next_position
                        AND position > 1  -- Not leading
                    ) as laps_defending,
                    -- Lost position (failed defense)
                    COUNT(*) FILTER (
                        WHERE position > prev_position
                    ) as positions_lost,
                    -- Total racing laps
                    COUNT(*) as total_laps
                FROM lap_positions
                WHERE prev_position IS NOT NULL
                GROUP BY driver_id
            )
            SELECT
                driver_id,
                laps_defending,
                positions_lost,
                total_laps,
                CASE WHEN laps_defending + positions_lost > 0
                    THEN ROUND(laps_defending::numeric / (laps_defending + positions_lost) * 100, 1)
                    ELSE 0 END as defense_success_rate
            FROM defense_events
            ORDER BY defense_success_rate DESC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, driver)

            return [
                {
                    "driver": row["driver_id"],
                    "laps_defending": row["laps_defending"],
                    "positions_lost": row["positions_lost"],
                    "total_racing_laps": row["total_laps"],
                    "defense_success_rate": f"{row['defense_success_rate']}%",
                    "defensive_rating": "Excellent" if row["defense_success_rate"] > 85 else
                                       "Good" if row["defense_success_rate"] > 75 else "Average",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing defensive driving: {e}")
        return [{"error": str(e)}]


@tool
async def get_traffic_management(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze how leaders handle lapped traffic.
    Tracks pace delta when encountering backmarkers.

    PERFECT FOR: "traffic management", "lapped cars", "blue flags", "backmarkers"

    Args:
        year: Season year
        event_name: Optional specific race
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name) if event_name else None

    try:
        # Compare pace in top 5 vs rest of the field
        query = """
            WITH race_laps AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.lap_time_seconds,
                    l.position,
                    s.event_name
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
                    AND l.lap_time_seconds < 180
                    AND l.is_pit_in_lap = false
                    AND l.is_pit_out_lap = false
                    AND ($2::text IS NULL OR s.event_name ILIKE '%' || $2 || '%')
                    AND ($3::text IS NULL OR l.driver_id = $3)
            ),
            leader_laps AS (
                SELECT
                    driver_id,
                    event_name,
                    AVG(lap_time_seconds) FILTER (WHERE position <= 3) as pace_in_clean_air,
                    AVG(lap_time_seconds) FILTER (WHERE position > 3) as pace_in_traffic,
                    COUNT(*) FILTER (WHERE position <= 3) as laps_leading,
                    COUNT(*) FILTER (WHERE position > 3) as laps_in_pack
                FROM race_laps
                GROUP BY driver_id, event_name
                HAVING COUNT(*) FILTER (WHERE position <= 3) >= 5
            )
            SELECT
                driver_id,
                COUNT(*) as races_leading,
                AVG(pace_in_clean_air) as avg_clean_air_pace,
                AVG(pace_in_traffic) as avg_traffic_pace,
                AVG(pace_in_traffic - pace_in_clean_air) as traffic_penalty,
                SUM(laps_leading) as total_laps_leading
            FROM leader_laps
            GROUP BY driver_id
            ORDER BY traffic_penalty ASC NULLS LAST
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"message": "No traffic management data found"}]

            return [
                {
                    "driver": row["driver_id"],
                    "races_with_lead_laps": row["races_leading"],
                    "total_lead_laps": row["total_laps_leading"],
                    "clean_air_pace": round(row["avg_clean_air_pace"], 3) if row["avg_clean_air_pace"] else None,
                    "traffic_pace": round(row["avg_traffic_pace"], 3) if row["avg_traffic_pace"] else None,
                    "traffic_penalty": f"+{row['traffic_penalty']:.3f}s" if row["traffic_penalty"] else "N/A",
                    "traffic_handling": "Excellent" if row["traffic_penalty"] and row["traffic_penalty"] < 0.3 else
                                       "Good" if row["traffic_penalty"] and row["traffic_penalty"] < 0.6 else "Struggles",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing traffic management: {e}")
        return [{"error": str(e)}]


@tool
async def get_fuel_adjusted_pace(
    year: int,
    event_name: str,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze pace adjusted for fuel load - early race (heavy) vs late race (light).
    Shows natural pace improvement as fuel burns off.

    PERFECT FOR: "fuel effect", "heavy fuel pace", "light fuel pace"

    Args:
        year: Season year
        event_name: Race name (e.g., "Monaco", "Silverstone")
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name)

    try:
        query = """
            WITH race_laps AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.lap_time_seconds,
                    MAX(l.lap_number) OVER (PARTITION BY l.driver_id) as total_laps
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.event_name ILIKE '%' || $2 || '%'
                    AND s.session_type = 'R'
                    AND l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
                    AND l.lap_time_seconds < 180
                    AND l.is_pit_in_lap = false
                    AND l.is_pit_out_lap = false
                    AND ($3::text IS NULL OR l.driver_id = $3)
            ),
            fuel_phases AS (
                SELECT
                    driver_id,
                    lap_number,
                    lap_time_seconds,
                    CASE
                        WHEN lap_number <= total_laps * 0.25 THEN 'heavy_fuel'
                        WHEN lap_number >= total_laps * 0.75 THEN 'light_fuel'
                        ELSE 'mid_fuel'
                    END as fuel_phase
                FROM race_laps
            )
            SELECT
                driver_id,
                AVG(lap_time_seconds) FILTER (WHERE fuel_phase = 'heavy_fuel') as heavy_fuel_pace,
                AVG(lap_time_seconds) FILTER (WHERE fuel_phase = 'mid_fuel') as mid_fuel_pace,
                AVG(lap_time_seconds) FILTER (WHERE fuel_phase = 'light_fuel') as light_fuel_pace,
                COUNT(*) FILTER (WHERE fuel_phase = 'heavy_fuel') as heavy_laps,
                COUNT(*) FILTER (WHERE fuel_phase = 'light_fuel') as light_laps
            FROM fuel_phases
            GROUP BY driver_id
            HAVING COUNT(*) FILTER (WHERE fuel_phase = 'heavy_fuel') >= 3
                AND COUNT(*) FILTER (WHERE fuel_phase = 'light_fuel') >= 3
            ORDER BY light_fuel_pace ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"message": f"No fuel-adjusted pace data found for {event_name} {year}"}]

            return [
                {
                    "driver": row["driver_id"],
                    "heavy_fuel_pace": round(row["heavy_fuel_pace"], 3),
                    "mid_fuel_pace": round(row["mid_fuel_pace"], 3) if row["mid_fuel_pace"] else None,
                    "light_fuel_pace": round(row["light_fuel_pace"], 3),
                    "fuel_burn_effect": f"-{row['heavy_fuel_pace'] - row['light_fuel_pace']:.3f}s",
                    "pace_improvement_pct": f"{((row['heavy_fuel_pace'] - row['light_fuel_pace']) / row['heavy_fuel_pace'] * 100):.1f}%",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing fuel-adjusted pace: {e}")
        return [{"error": str(e)}]


@tool
async def get_tire_cliff_analysis(
    year: int,
    event_name: str | None = None,
    driver_id: str | None = None,
) -> list[dict]:
    """
    Analyze tire cliff - sudden pace drop-off when tires degrade.
    Identifies drivers who manage vs fall off the cliff.

    PERFECT FOR: "tire cliff", "tire drop-off", "tire degradation spike"

    Args:
        year: Season year
        event_name: Optional specific race
        driver_id: Optional driver filter (3-letter code)
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

    driver = normalize_driver_id(driver_id) if driver_id else None
    event = normalize_event_name(event_name) if event_name else None

    try:
        query = """
            WITH stint_laps AS (
                SELECT
                    l.driver_id,
                    l.lap_number,
                    l.lap_time_seconds,
                    l.compound,
                    s.event_name,
                    LAG(l.lap_time_seconds) OVER (
                        PARTITION BY l.driver_id, s.session_id, l.compound
                        ORDER BY l.lap_number
                    ) as prev_lap_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY l.driver_id, s.session_id, l.compound
                        ORDER BY l.lap_number
                    ) as stint_lap
                FROM laps l
                JOIN sessions s ON l.session_id = s.session_id
                WHERE s.year = $1
                    AND s.session_type = 'R'
                    AND l.lap_time_seconds IS NOT NULL
                    AND l.lap_time_seconds > 60
                    AND l.lap_time_seconds < 180
                    AND l.is_pit_in_lap = false
                    AND ($2::text IS NULL OR s.event_name ILIKE '%' || $2 || '%')
                    AND ($3::text IS NULL OR l.driver_id = $3)
            ),
            lap_deltas AS (
                SELECT
                    driver_id,
                    event_name,
                    compound,
                    stint_lap,
                    lap_time_seconds,
                    lap_time_seconds - prev_lap_time as lap_delta,
                    CASE WHEN lap_time_seconds - prev_lap_time > 1.0 THEN true ELSE false END as cliff_lap
                FROM stint_laps
                WHERE prev_lap_time IS NOT NULL
            ),
            cliff_stats AS (
                SELECT
                    driver_id,
                    COUNT(*) as total_stint_laps,
                    COUNT(*) FILTER (WHERE cliff_lap) as cliff_events,
                    MAX(lap_delta) as worst_dropoff,
                    AVG(lap_delta) as avg_degradation
                FROM lap_deltas
                GROUP BY driver_id
            )
            SELECT
                driver_id,
                total_stint_laps,
                cliff_events,
                worst_dropoff,
                avg_degradation,
                ROUND(cliff_events::numeric / NULLIF(total_stint_laps, 0) * 100, 1) as cliff_frequency
            FROM cliff_stats
            ORDER BY cliff_frequency ASC
        """

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, year, event, driver)

            if not rows:
                return [{"message": "No tire cliff data found"}]

            return [
                {
                    "driver": row["driver_id"],
                    "total_stint_laps": row["total_stint_laps"],
                    "cliff_events": row["cliff_events"],
                    "cliff_frequency": f"{row['cliff_frequency']}%",
                    "worst_dropoff": f"+{row['worst_dropoff']:.3f}s" if row["worst_dropoff"] else "N/A",
                    "avg_degradation": f"+{row['avg_degradation']:.3f}s/lap" if row["avg_degradation"] else "N/A",
                    "tire_management": "Excellent" if row["cliff_frequency"] < 2 else
                                      "Good" if row["cliff_frequency"] < 5 else "Poor",
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error analyzing tire cliff: {e}")
        return [{"error": str(e)}]


# Export all tools
TIMESCALE_TOOLS = [
    # Original tools (for detailed queries)
    get_lap_times,
    get_pit_stops,
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
    # Advanced analytical tools
    get_driver_vs_field,
    get_season_pace_ranking,
    get_performance_trend,
    compare_teams,
    get_qualifying_race_delta,
    # Specialized analytical tools
    get_overtaking_analysis,
    get_sector_performance,
    get_consistency_ranking,
    get_reliability_stats,
    get_wet_weather_performance,
    get_lap1_performance,
    get_fastest_lap_stats,
    get_teammate_battle,
    get_points_finish_rate,
    # Circuit & historical tools
    get_track_specialist,
    get_championship_evolution,
    get_career_stats,
    get_qualifying_stats,
    get_podium_stats,
    get_race_dominance,
    get_compound_performance,
    # Streaks, sprints & special analysis tools
    get_sprint_performance,
    get_winning_streaks,
    get_constructor_evolution,
    get_home_race_performance,
    get_comeback_drives,
    get_grid_penalty_impact,
    get_finishing_streaks,
    # Advanced race analysis tools
    get_gap_to_leader,
    get_strategy_effectiveness,
    get_safety_car_impact,
    get_tire_life_masters,
    get_championship_momentum,
    get_head_to_head_career,
    get_rookie_comparison,
    get_team_lockouts,
    get_undercut_success,
    get_points_per_start,
    get_final_lap_heroics,
    get_clean_weekend_rate,
    # Grid position & conversion analysis tools
    get_pole_to_win_conversion,
    get_grid_position_advantage,
    get_circuit_type_performance,
    get_q3_shootout_performance,
    get_race_pace_vs_quali_pace,
    get_position_battle_stats,
    get_average_race_position,
    get_points_trajectory,
    # Race dynamics & micro-analysis tools
    get_drs_effectiveness,
    get_tire_warmup_specialist,
    get_qualifying_improvement,
    get_theoretical_best_lap,
    get_race_pace_degradation,
    get_red_flag_restart_performance,
    get_season_phase_performance,
    get_back_to_back_performance,
    get_championship_pressure_performance,
    get_pit_exit_performance,
    get_defensive_driving_stats,
    get_traffic_management,
    get_fuel_adjusted_pace,
    get_tire_cliff_analysis,
    # Flexible query tools
    query_f1_database,
    get_database_schema,
    simulate_pit_strategy,
    find_similar_race_scenarios,
]
