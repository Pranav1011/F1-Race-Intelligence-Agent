"""
TimescaleDB Tools

Tools for querying F1 telemetry, lap times, and weather data from TimescaleDB.
"""

import logging
from typing import Any

import asyncpg
from langchain_core.tools import tool

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
        year: Filter by season year
        event_name: Filter by race name (partial match)
        limit: Maximum number of results

    Returns:
        List of lap time records with driver, lap number, times, tire info
    """
    if not _pool:
        return [{"error": "Database connection not initialized"}]

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

        if driver_id:
            query += f" AND lt.driver_id = ${param_idx}"
            params.append(driver_id.upper())
            param_idx += 1

        if year:
            query += f" AND s.year = ${param_idx}"
            params.append(year)
            param_idx += 1

        if event_name:
            query += f" AND s.event_name ILIKE ${param_idx}"
            params.append(f"%{event_name}%")
            param_idx += 1

        query += f" ORDER BY lt.lap_number LIMIT ${param_idx}"
        params.append(limit)

        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting lap times: {e}")
        return [{"error": str(e)}]


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
        driver_ids: List of driver abbreviations to compare
        stint: Specific stint to compare (optional)

    Returns:
        Comparison data with average pace, best laps, consistency
    """
    if not _pool:
        return {"error": "Database connection not initialized"}

    try:
        results = {}

        for driver_id in driver_ids:
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
                row = await conn.fetchrow(query, session_id, driver_id.upper(), stint)
                if row:
                    results[driver_id.upper()] = dict(row)

        return results

    except Exception as e:
        logger.error(f"Error comparing driver pace: {e}")
        return {"error": str(e)}


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


# Export all tools
TIMESCALE_TOOLS = [
    get_lap_times,
    get_driver_stint_summary,
    compare_driver_pace,
    get_tire_degradation,
    get_weather_conditions,
    get_session_results,
    get_available_sessions,
]
