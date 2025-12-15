"""
Neo4j Knowledge Graph Loader

Builds F1 knowledge graph with entities and relationships:
- Drivers, Teams, Seasons, Races, Circuits
- Stints, PitStops, TireCompounds
- Relationships between all entities
"""

import logging

import pandas as pd
from neo4j import AsyncGraphDatabase

from ingestion.extractors.fastf1_extractor import ExtractedSession

logger = logging.getLogger(__name__)


class Neo4jLoader:
    """Build F1 knowledge graph in Neo4j."""

    def __init__(self, uri: str, user: str, password: str):
        """
        Initialize the Neo4j loader.

        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            user: Neo4j username
            password: Neo4j password
        """
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"Neo4j driver initialized for {uri}")

    async def close(self):
        """Close the Neo4j driver."""
        await self.driver.close()
        logger.info("Neo4j driver closed")

    async def initialize(self):
        """Create constraints and indexes for the knowledge graph."""
        logger.info("Initializing Neo4j schema")

        async with self.driver.session() as session:
            # Create constraints for unique identifiers
            constraints = [
                "CREATE CONSTRAINT driver_id IF NOT EXISTS FOR (d:Driver) REQUIRE d.id IS UNIQUE",
                "CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.id IS UNIQUE",
                "CREATE CONSTRAINT race_id IF NOT EXISTS FOR (r:Race) REQUIRE r.id IS UNIQUE",
                "CREATE CONSTRAINT circuit_id IF NOT EXISTS FOR (c:Circuit) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT season_year IF NOT EXISTS FOR (s:Season) REQUIRE s.year IS UNIQUE",
                "CREATE CONSTRAINT tire_compound IF NOT EXISTS FOR (tc:TireCompound) REQUIRE tc.name IS UNIQUE",
            ]

            for constraint in constraints:
                try:
                    await session.run(constraint)
                except Exception as e:
                    logger.debug(f"Constraint may already exist: {e}")

            # Create indexes for common queries
            indexes = [
                "CREATE INDEX driver_name IF NOT EXISTS FOR (d:Driver) ON (d.name)",
                "CREATE INDEX team_name IF NOT EXISTS FOR (t:Team) ON (t.name)",
                "CREATE INDEX race_round IF NOT EXISTS FOR (r:Race) ON (r.round)",
            ]

            for index in indexes:
                try:
                    await session.run(index)
                except Exception as e:
                    logger.debug(f"Index may already exist: {e}")

        logger.info("Neo4j schema initialized")

    async def load_session(self, session_data: ExtractedSession) -> bool:
        """
        Load session data into the knowledge graph.

        Creates/updates nodes for:
        - Season, Circuit, Race
        - Drivers, Teams
        - Stints, PitStops (for race sessions)

        Args:
            session_data: Extracted session data

        Returns:
            True if successful
        """
        logger.info(
            f"Loading {session_data.year} {session_data.event_name} "
            f"{session_data.session_type} into Neo4j"
        )

        try:
            async with self.driver.session() as session:
                # Create core entities
                await self._create_season(session, session_data.year)
                await self._create_circuit(session, session_data)
                await self._create_race(session, session_data)

                # Create drivers and teams from results
                if session_data.results is not None and len(session_data.results) > 0:
                    await self._create_drivers_and_teams(session, session_data)

                    # Create race results relationships
                    if session_data.session_type == "R":
                        await self._create_race_results(session, session_data)

                # Create stints and pit stops for race sessions
                if (
                    session_data.session_type == "R"
                    and session_data.laps is not None
                    and len(session_data.laps) > 0
                ):
                    await self._create_stints(session, session_data)

            logger.info(f"Successfully loaded session into Neo4j")
            return True

        except Exception as e:
            logger.error(f"Failed to load session into Neo4j: {e}")
            return False

    async def _create_season(self, session, year: int):
        """Create or merge Season node."""
        await session.run(
            "MERGE (s:Season {year: $year})",
            year=year,
        )

    async def _create_circuit(self, session, session_data: ExtractedSession):
        """Create or merge Circuit node."""
        circuit_id = session_data.circuit.lower().replace(" ", "_").replace("-", "_")

        await session.run(
            """
            MERGE (c:Circuit {id: $circuit_id})
            SET c.name = $name,
                c.location = $location
            """,
            circuit_id=circuit_id,
            name=session_data.event_name,
            location=session_data.circuit,
        )

    async def _create_race(self, session, session_data: ExtractedSession):
        """Create Race node and connect to Season and Circuit."""
        race_id = f"{session_data.year}_{session_data.round_number}"
        circuit_id = session_data.circuit.lower().replace(" ", "_").replace("-", "_")

        await session.run(
            """
            MATCH (s:Season {year: $year})
            MATCH (c:Circuit {id: $circuit_id})
            MERGE (r:Race {id: $race_id})
            SET r.name = $name,
                r.round = $round,
                r.year = $year,
                r.date = $date
            MERGE (r)-[:PART_OF]->(s)
            MERGE (r)-[:HELD_AT]->(c)
            """,
            year=session_data.year,
            circuit_id=circuit_id,
            race_id=race_id,
            name=session_data.event_name,
            round=session_data.round_number,
            date=str(session_data.session_date) if session_data.session_date else None,
        )

    async def _create_drivers_and_teams(self, session, session_data: ExtractedSession):
        """Create Driver and Team nodes with relationships."""
        results = session_data.results

        for _, row in results.iterrows():
            driver_id = row.get("Abbreviation", "")
            if not driver_id:
                continue

            driver_name = row.get("FullName", driver_id)
            team_name = row.get("TeamName", "")
            team_id = team_name.lower().replace(" ", "_").replace("-", "_") if team_name else None

            # Create Driver
            await session.run(
                """
                MERGE (d:Driver {id: $driver_id})
                SET d.name = $driver_name,
                    d.abbreviation = $driver_id,
                    d.number = $driver_number
                """,
                driver_id=driver_id,
                driver_name=driver_name,
                driver_number=str(row.get("DriverNumber", "")),
            )

            # Create Team and DROVE_FOR relationship
            if team_id:
                await session.run(
                    """
                    MERGE (t:Team {id: $team_id})
                    SET t.name = $team_name
                    WITH t
                    MATCH (d:Driver {id: $driver_id})
                    MERGE (d)-[r:DROVE_FOR]->(t)
                    SET r.year = $year
                    """,
                    team_id=team_id,
                    team_name=team_name,
                    driver_id=driver_id,
                    year=session_data.year,
                )

    async def _create_race_results(self, session, session_data: ExtractedSession):
        """Create FINISHED relationships between Drivers and Race."""
        race_id = f"{session_data.year}_{session_data.round_number}"
        results = session_data.results

        for _, row in results.iterrows():
            driver_id = row.get("Abbreviation", "")
            if not driver_id:
                continue

            position = row.get("Position")
            grid = row.get("GridPosition")
            points = row.get("Points", 0)
            status = row.get("Status", "")

            await session.run(
                """
                MATCH (d:Driver {id: $driver_id})
                MATCH (r:Race {id: $race_id})
                MERGE (d)-[result:FINISHED]->(r)
                SET result.position = $position,
                    result.grid = $grid,
                    result.points = $points,
                    result.status = $status
                """,
                driver_id=driver_id,
                race_id=race_id,
                position=int(position) if pd.notna(position) else None,
                grid=int(grid) if pd.notna(grid) else None,
                points=float(points) if pd.notna(points) else 0,
                status=status,
            )

    async def _create_stints(self, session, session_data: ExtractedSession):
        """Create Stint nodes and PitStop nodes from lap data."""
        race_id = f"{session_data.year}_{session_data.round_number}"
        laps = session_data.laps

        # Group by driver
        for driver_id in laps["Driver"].unique():
            driver_laps = laps[laps["Driver"] == driver_id]

            # Group by stint
            stints = driver_laps.groupby("Stint").agg({
                "LapNumber": ["min", "max", "count"],
                "Compound": "first",
            }).reset_index()

            previous_stint_id = None

            for _, stint_row in stints.iterrows():
                stint_num = int(stint_row["Stint"].iloc[0] if hasattr(stint_row["Stint"], 'iloc') else stint_row["Stint"])
                start_lap = int(stint_row[("LapNumber", "min")].iloc[0] if hasattr(stint_row[("LapNumber", "min")], 'iloc') else stint_row[("LapNumber", "min")])
                end_lap = int(stint_row[("LapNumber", "max")].iloc[0] if hasattr(stint_row[("LapNumber", "max")], 'iloc') else stint_row[("LapNumber", "max")])
                lap_count = int(stint_row[("LapNumber", "count")].iloc[0] if hasattr(stint_row[("LapNumber", "count")], 'iloc') else stint_row[("LapNumber", "count")])
                compound_val = stint_row[("Compound", "first")]
                compound = compound_val.iloc[0] if hasattr(compound_val, 'iloc') else compound_val

                stint_id = f"{race_id}_{driver_id}_{stint_num}"

                # Create TireCompound node
                if compound and pd.notna(compound):
                    await session.run(
                        "MERGE (tc:TireCompound {name: $compound})",
                        compound=compound,
                    )

                # Create Stint node
                await session.run(
                    """
                    MATCH (d:Driver {id: $driver_id})
                    MATCH (r:Race {id: $race_id})
                    MERGE (stint:Stint {id: $stint_id})
                    SET stint.number = $stint_num,
                        stint.start_lap = $start_lap,
                        stint.end_lap = $end_lap,
                        stint.lap_count = $lap_count,
                        stint.compound = $compound
                    MERGE (d)-[:HAD_STINT]->(stint)
                    MERGE (stint)-[:DURING]->(r)
                    """,
                    driver_id=driver_id,
                    race_id=race_id,
                    stint_id=stint_id,
                    stint_num=stint_num,
                    start_lap=start_lap,
                    end_lap=end_lap,
                    lap_count=lap_count,
                    compound=compound if pd.notna(compound) else None,
                )

                # Link stint to tire compound
                if compound and pd.notna(compound):
                    await session.run(
                        """
                        MATCH (stint:Stint {id: $stint_id})
                        MATCH (tc:TireCompound {name: $compound})
                        MERGE (stint)-[:USED_COMPOUND]->(tc)
                        """,
                        stint_id=stint_id,
                        compound=compound,
                    )

                # Create PitStop between stints
                if previous_stint_id and stint_num > 1:
                    pitstop_id = f"{race_id}_{driver_id}_pit_{stint_num}"

                    await session.run(
                        """
                        MATCH (d:Driver {id: $driver_id})
                        MATCH (r:Race {id: $race_id})
                        MATCH (prev:Stint {id: $prev_stint_id})
                        MATCH (curr:Stint {id: $curr_stint_id})
                        MERGE (ps:PitStop {id: $pitstop_id})
                        SET ps.lap = $lap,
                            ps.from_compound = prev.compound,
                            ps.to_compound = curr.compound
                        MERGE (d)-[:MADE_PITSTOP]->(ps)
                        MERGE (ps)-[:DURING]->(r)
                        MERGE (prev)-[:FOLLOWED_BY]->(ps)
                        MERGE (ps)-[:FOLLOWED_BY]->(curr)
                        """,
                        driver_id=driver_id,
                        race_id=race_id,
                        prev_stint_id=previous_stint_id,
                        curr_stint_id=stint_id,
                        pitstop_id=pitstop_id,
                        lap=start_lap,
                    )

                previous_stint_id = stint_id

    async def get_driver_count(self) -> int:
        """Get the number of drivers in the graph."""
        async with self.driver.session() as session:
            result = await session.run("MATCH (d:Driver) RETURN count(d) as count")
            record = await result.single()
            return record["count"] if record else 0

    async def get_race_count(self) -> int:
        """Get the number of races in the graph."""
        async with self.driver.session() as session:
            result = await session.run("MATCH (r:Race) RETURN count(r) as count")
            record = await result.single()
            return record["count"] if record else 0
