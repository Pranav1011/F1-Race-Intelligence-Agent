"""
Neo4j Tools

Tools for querying the F1 knowledge graph.
"""

import logging
from typing import Any

from langchain_core.tools import tool
from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

# Driver instance (initialized at startup)
_driver = None


async def init_driver(uri: str, user: str, password: str):
    """Initialize the Neo4j driver."""
    global _driver
    _driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    logger.info("Neo4j tool driver initialized")


async def close_driver():
    """Close the Neo4j driver."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


@tool
async def get_driver_info(driver_id: str) -> dict:
    """
    Get information about a driver.

    Args:
        driver_id: Driver abbreviation (e.g., "VER", "HAM")

    Returns:
        Driver info including name, number, teams
    """
    if not _driver:
        return {"error": "Database connection not initialized"}

    try:
        query = """
            MATCH (d:Driver {id: $driver_id})
            OPTIONAL MATCH (d)-[df:DROVE_FOR]->(t:Team)
            RETURN d.name as name,
                   d.abbreviation as abbreviation,
                   d.number as number,
                   collect(DISTINCT {team: t.name, year: df.year}) as teams
        """

        async with _driver.session() as session:
            result = await session.run(query, driver_id=driver_id.upper())
            record = await result.single()
            if record:
                return dict(record)
            return {"error": f"Driver {driver_id} not found"}

    except Exception as e:
        logger.error(f"Error getting driver info: {e}")
        return {"error": str(e)}


@tool
async def get_driver_race_history(
    driver_id: str,
    year: int | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Get race results history for a driver.

    Args:
        driver_id: Driver abbreviation (e.g., "VER")
        year: Filter by season (optional)
        limit: Maximum results to return

    Returns:
        List of race results with positions, points
    """
    if not _driver:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            MATCH (d:Driver {id: $driver_id})-[f:FINISHED]->(r:Race)
            WHERE $year IS NULL OR r.year = $year
            RETURN r.name as race,
                   r.year as year,
                   r.round as round,
                   f.position as position,
                   f.grid as grid,
                   f.points as points,
                   f.status as status
            ORDER BY r.year DESC, r.round DESC
            LIMIT $limit
        """

        async with _driver.session() as session:
            result = await session.run(
                query,
                driver_id=driver_id.upper(),
                year=year,
                limit=limit,
            )
            records = await result.data()
            return records

    except Exception as e:
        logger.error(f"Error getting driver race history: {e}")
        return [{"error": str(e)}]


@tool
async def get_team_drivers(
    team_name: str,
    year: int | None = None,
) -> list[dict]:
    """
    Get drivers for a team.

    Args:
        team_name: Team name (partial match supported)
        year: Filter by season

    Returns:
        List of drivers who drove for the team
    """
    if not _driver:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            MATCH (d:Driver)-[df:DROVE_FOR]->(t:Team)
            WHERE toLower(t.name) CONTAINS toLower($team_name)
                AND ($year IS NULL OR df.year = $year)
            RETURN d.name as driver,
                   d.abbreviation as abbreviation,
                   t.name as team,
                   df.year as year
            ORDER BY df.year DESC, d.name
        """

        async with _driver.session() as session:
            result = await session.run(query, team_name=team_name, year=year)
            records = await result.data()
            return records

    except Exception as e:
        logger.error(f"Error getting team drivers: {e}")
        return [{"error": str(e)}]


@tool
async def get_race_info(
    race_name: str | None = None,
    year: int | None = None,
    round_number: int | None = None,
) -> list[dict]:
    """
    Get information about races.

    Args:
        race_name: Race name (partial match)
        year: Season year
        round_number: Round number

    Returns:
        Race info with circuit, date, results summary
    """
    if not _driver:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            MATCH (r:Race)-[:HELD_AT]->(c:Circuit)
            WHERE ($race_name IS NULL OR toLower(r.name) CONTAINS toLower($race_name))
                AND ($year IS NULL OR r.year = $year)
                AND ($round IS NULL OR r.round = $round)
            OPTIONAL MATCH (d:Driver)-[f:FINISHED {position: 1}]->(r)
            RETURN r.name as race,
                   r.year as year,
                   r.round as round,
                   r.date as date,
                   c.name as circuit,
                   c.location as location,
                   d.name as winner
            ORDER BY r.year DESC, r.round DESC
            LIMIT 20
        """

        async with _driver.session() as session:
            result = await session.run(
                query,
                race_name=race_name,
                year=year,
                round=round_number,
            )
            records = await result.data()
            return records

    except Exception as e:
        logger.error(f"Error getting race info: {e}")
        return [{"error": str(e)}]


@tool
async def get_driver_stints_graph(
    driver_id: str,
    race_id: str,
) -> list[dict]:
    """
    Get stint and pit stop information for a driver from the knowledge graph.

    Args:
        driver_id: Driver abbreviation (e.g., "VER")
        race_id: Race ID (e.g., "2024_1")

    Returns:
        Stint info with tire compounds, lap ranges, pit stops
    """
    if not _driver:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            MATCH (d:Driver {id: $driver_id})-[:HAD_STINT]->(s:Stint)-[:DURING]->(r:Race {id: $race_id})
            OPTIONAL MATCH (s)-[:USED_COMPOUND]->(tc:TireCompound)
            OPTIONAL MATCH (prev:Stint)-[:FOLLOWED_BY]->(ps:PitStop)-[:FOLLOWED_BY]->(s)
            RETURN s.number as stint_number,
                   s.start_lap as start_lap,
                   s.end_lap as end_lap,
                   s.lap_count as lap_count,
                   tc.name as compound,
                   ps.lap as pit_lap,
                   ps.from_compound as from_compound,
                   ps.to_compound as to_compound
            ORDER BY s.number
        """

        async with _driver.session() as session:
            result = await session.run(query, driver_id=driver_id.upper(), race_id=race_id)
            records = await result.data()
            return records

    except Exception as e:
        logger.error(f"Error getting driver stints: {e}")
        return [{"error": str(e)}]


@tool
async def compare_teammates(
    year: int,
    team_name: str | None = None,
) -> list[dict]:
    """
    Compare teammates' performance.

    Args:
        year: Season year
        team_name: Team name (optional, returns all teams if not specified)

    Returns:
        Head-to-head comparison of teammates
    """
    if not _driver:
        return [{"error": "Database connection not initialized"}]

    try:
        query = """
            MATCH (d1:Driver)-[df1:DROVE_FOR {year: $year}]->(t:Team)<-[df2:DROVE_FOR {year: $year}]-(d2:Driver)
            WHERE d1.id < d2.id
                AND ($team_name IS NULL OR toLower(t.name) CONTAINS toLower($team_name))
            OPTIONAL MATCH (d1)-[f1:FINISHED]->(r:Race {year: $year})
            OPTIONAL MATCH (d2)-[f2:FINISHED]->(r)
            WITH t, d1, d2, r,
                 CASE WHEN f1.position < f2.position THEN 1 ELSE 0 END as d1_ahead,
                 CASE WHEN f2.position < f1.position THEN 1 ELSE 0 END as d2_ahead,
                 coalesce(f1.points, 0) as d1_points,
                 coalesce(f2.points, 0) as d2_points
            RETURN t.name as team,
                   d1.name as driver1,
                   d2.name as driver2,
                   sum(d1_ahead) as driver1_ahead,
                   sum(d2_ahead) as driver2_ahead,
                   sum(d1_points) as driver1_points,
                   sum(d2_points) as driver2_points,
                   count(r) as races
        """

        async with _driver.session() as session:
            result = await session.run(query, year=year, team_name=team_name)
            records = await result.data()
            return records

    except Exception as e:
        logger.error(f"Error comparing teammates: {e}")
        return [{"error": str(e)}]


@tool
async def get_circuit_info(circuit_name: str) -> dict:
    """
    Get information about a circuit.

    Args:
        circuit_name: Circuit name or location (partial match)

    Returns:
        Circuit details and races held there
    """
    if not _driver:
        return {"error": "Database connection not initialized"}

    try:
        query = """
            MATCH (c:Circuit)
            WHERE toLower(c.name) CONTAINS toLower($circuit_name)
                OR toLower(c.location) CONTAINS toLower($circuit_name)
            OPTIONAL MATCH (r:Race)-[:HELD_AT]->(c)
            WITH c, r ORDER BY r.year DESC
            RETURN c.name as name,
                   c.location as location,
                   collect({year: r.year, race: r.name})[0..5] as recent_races
            LIMIT 1
        """

        async with _driver.session() as session:
            result = await session.run(query, circuit_name=circuit_name)
            record = await result.single()
            if record:
                return dict(record)
            return {"error": f"Circuit {circuit_name} not found"}

    except Exception as e:
        logger.error(f"Error getting circuit info: {e}")
        return {"error": str(e)}


@tool
async def find_similar_situations(
    scenario: str,
    limit: int = 5,
) -> list[dict]:
    """
    Find historically similar race situations using graph patterns.

    Args:
        scenario: Description of the situation to find (e.g., "rain during pit window")
        limit: Maximum results

    Returns:
        Similar historical situations from the knowledge graph
    """
    if not _driver:
        return [{"error": "Database connection not initialized"}]

    # This is a simplified version - in production, this would use
    # more sophisticated pattern matching or vector similarity
    try:
        # For now, return recent races as examples
        query = """
            MATCH (r:Race)-[:HELD_AT]->(c:Circuit)
            MATCH (d:Driver)-[f:FINISHED]->(r)
            WHERE f.position = 1
            RETURN r.name as race,
                   r.year as year,
                   c.location as circuit,
                   d.name as winner,
                   f.status as status
            ORDER BY r.year DESC, r.round DESC
            LIMIT $limit
        """

        async with _driver.session() as session:
            result = await session.run(query, limit=limit)
            records = await result.data()
            return records

    except Exception as e:
        logger.error(f"Error finding similar situations: {e}")
        return [{"error": str(e)}]


# Export all tools
NEO4J_TOOLS = [
    get_driver_info,
    get_driver_race_history,
    get_team_drivers,
    get_race_info,
    get_driver_stints_graph,
    compare_teammates,
    get_circuit_info,
    find_similar_situations,
]
