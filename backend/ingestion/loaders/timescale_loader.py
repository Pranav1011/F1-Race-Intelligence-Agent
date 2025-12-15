"""
TimescaleDB Loader

Loads F1 telemetry, lap times, and weather data into TimescaleDB.
Uses hypertables for efficient time-series storage and querying.
"""

import logging
from datetime import datetime

import asyncpg
import pandas as pd

from ingestion.extractors.fastf1_extractor import ExtractedSession

logger = logging.getLogger(__name__)


class TimescaleLoader:
    """Load F1 data into TimescaleDB."""

    def __init__(self, connection_string: str):
        """
        Initialize the loader.

        Args:
            connection_string: PostgreSQL connection string
                e.g., "postgresql://f1:f1_password@localhost:5432/f1_telemetry"
        """
        self.connection_string = connection_string
        self.pool: asyncpg.Pool | None = None

    async def initialize(self):
        """Create connection pool and ensure schema exists."""
        logger.info("Initializing TimescaleDB connection pool")
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=10,
        )
        await self._create_schema()
        logger.info("TimescaleDB schema initialized")

    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("TimescaleDB connection pool closed")

    async def _create_schema(self):
        """Create tables, hypertables, and indexes."""
        async with self.pool.acquire() as conn:
            # Enable TimescaleDB extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

            # Sessions reference table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    year INT NOT NULL,
                    round_number INT NOT NULL,
                    event_name TEXT NOT NULL,
                    session_type TEXT NOT NULL,
                    circuit TEXT NOT NULL,
                    session_date TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_year ON sessions(year);
                CREATE INDEX IF NOT EXISTS idx_sessions_event ON sessions(event_name);
            """)

            # Lap times table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS lap_times (
                    id SERIAL,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    driver_number TEXT,
                    team TEXT,
                    lap_number INT NOT NULL,
                    lap_time_seconds DOUBLE PRECISION,
                    sector_1_seconds DOUBLE PRECISION,
                    sector_2_seconds DOUBLE PRECISION,
                    sector_3_seconds DOUBLE PRECISION,
                    compound TEXT,
                    tire_life INT,
                    stint INT,
                    position INT,
                    is_personal_best BOOLEAN,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    deleted_reason TEXT,
                    lap_start_time TIMESTAMPTZ,
                    recorded_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (session_id, driver_id, lap_number)
                );

                CREATE INDEX IF NOT EXISTS idx_lap_times_session ON lap_times(session_id);
                CREATE INDEX IF NOT EXISTS idx_lap_times_driver ON lap_times(driver_id);
                CREATE INDEX IF NOT EXISTS idx_lap_times_compound ON lap_times(compound);
            """)

            # Telemetry hypertable
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    time TIMESTAMPTZ NOT NULL,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    distance DOUBLE PRECISION,
                    speed DOUBLE PRECISION,
                    rpm INT,
                    gear INT,
                    throttle DOUBLE PRECISION,
                    brake DOUBLE PRECISION,
                    drs INT,
                    position_x DOUBLE PRECISION,
                    position_y DOUBLE PRECISION,
                    position_z DOUBLE PRECISION
                );
            """)

            # Convert to hypertable if not already
            try:
                await conn.execute("""
                    SELECT create_hypertable('telemetry', 'time',
                        if_not_exists => TRUE,
                        chunk_time_interval => INTERVAL '1 hour'
                    );
                """)
            except Exception as e:
                logger.debug(f"Hypertable might already exist: {e}")

            # Telemetry indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_telemetry_session_driver
                    ON telemetry(session_id, driver_id, time DESC);
            """)

            # Weather hypertable
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weather (
                    time TIMESTAMPTZ NOT NULL,
                    session_id TEXT NOT NULL,
                    air_temp DOUBLE PRECISION,
                    track_temp DOUBLE PRECISION,
                    humidity DOUBLE PRECISION,
                    pressure DOUBLE PRECISION,
                    wind_speed DOUBLE PRECISION,
                    wind_direction INT,
                    rainfall BOOLEAN
                );
            """)

            try:
                await conn.execute("""
                    SELECT create_hypertable('weather', 'time',
                        if_not_exists => TRUE,
                        chunk_time_interval => INTERVAL '1 day'
                    );
                """)
            except Exception as e:
                logger.debug(f"Weather hypertable might already exist: {e}")

            # Results table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    driver_number TEXT,
                    driver_name TEXT,
                    team TEXT,
                    position INT,
                    grid_position INT,
                    status TEXT,
                    points DOUBLE PRECISION,
                    time_seconds DOUBLE PRECISION,
                    q1_seconds DOUBLE PRECISION,
                    q2_seconds DOUBLE PRECISION,
                    q3_seconds DOUBLE PRECISION,
                    UNIQUE(session_id, driver_id)
                );

                CREATE INDEX IF NOT EXISTS idx_results_session ON results(session_id);
                CREATE INDEX IF NOT EXISTS idx_results_driver ON results(driver_id);
            """)

    async def load_session(self, session_data: ExtractedSession) -> bool:
        """
        Load a complete session into TimescaleDB.

        Args:
            session_data: Extracted session data from FastF1

        Returns:
            True if successful, False otherwise
        """
        session_id = f"{session_data.year}_{session_data.round_number}_{session_data.session_type}"
        logger.info(f"Loading session {session_id} into TimescaleDB")

        try:
            async with self.pool.acquire() as conn:
                # Handle session_date - convert to timezone-aware if needed
                session_date = session_data.session_date
                if session_date is not None and pd.notna(session_date):
                    if hasattr(session_date, 'tz') and session_date.tz is None:
                        # Localize naive timestamp to UTC
                        session_date = session_date.tz_localize('UTC')
                    session_date = session_date.to_pydatetime() if hasattr(session_date, 'to_pydatetime') else session_date
                else:
                    session_date = None

                # Insert session metadata
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, year, round_number, event_name,
                                         session_type, circuit, session_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (session_id) DO UPDATE SET
                        event_name = EXCLUDED.event_name,
                        circuit = EXCLUDED.circuit,
                        session_date = EXCLUDED.session_date
                    """,
                    session_id,
                    session_data.year,
                    session_data.round_number,
                    session_data.event_name,
                    session_data.session_type,
                    session_data.circuit,
                    session_date,
                )

                # Load lap times
                await self._load_laps(conn, session_id, session_data.laps)

                # Load results
                await self._load_results(conn, session_id, session_data.results)

                # Load telemetry (can be large)
                await self._load_telemetry(conn, session_id, session_data.telemetry)

                # Load weather
                await self._load_weather(conn, session_id, session_data.weather)

            logger.info(f"Successfully loaded session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return False

    async def _load_laps(self, conn, session_id: str, laps: pd.DataFrame):
        """Load lap times data."""
        if laps is None or len(laps) == 0:
            logger.debug("No lap data to load")
            return

        # Delete existing laps for this session (for re-runs)
        await conn.execute("DELETE FROM lap_times WHERE session_id = $1", session_id)

        records = []
        for _, row in laps.iterrows():
            # Handle LapStartTime - convert to timezone-aware if needed
            lap_start_time = row.get("LapStartTime")
            if lap_start_time is not None and pd.notna(lap_start_time):
                if hasattr(lap_start_time, 'tz') and lap_start_time.tz is None:
                    lap_start_time = lap_start_time.tz_localize('UTC')
                if hasattr(lap_start_time, 'to_pydatetime'):
                    lap_start_time = lap_start_time.to_pydatetime()
            else:
                lap_start_time = None

            records.append((
                session_id,
                row.get("Driver", ""),
                str(row.get("DriverNumber", "")),
                row.get("Team", ""),
                int(row.get("LapNumber", 0)),
                row.get("LapTimeSeconds"),
                row.get("Sector1TimeSeconds"),
                row.get("Sector2TimeSeconds"),
                row.get("Sector3TimeSeconds"),
                row.get("Compound"),
                int(row["TyreLife"]) if pd.notna(row.get("TyreLife")) else None,
                int(row["Stint"]) if pd.notna(row.get("Stint")) else None,
                int(row["Position"]) if pd.notna(row.get("Position")) else None,
                bool(row.get("IsPersonalBest", False)),
                bool(row.get("Deleted", False)),
                row.get("DeletedReason"),
                lap_start_time,
            ))

        if records:
            await conn.executemany(
                """
                INSERT INTO lap_times (session_id, driver_id, driver_number, team,
                    lap_number, lap_time_seconds, sector_1_seconds, sector_2_seconds,
                    sector_3_seconds, compound, tire_life, stint, position,
                    is_personal_best, is_deleted, deleted_reason, lap_start_time)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                ON CONFLICT (session_id, driver_id, lap_number) DO NOTHING
                """,
                records,
            )
            logger.info(f"Loaded {len(records)} lap records")

    async def _load_results(self, conn, session_id: str, results: pd.DataFrame):
        """Load session results."""
        if results is None or len(results) == 0:
            logger.debug("No results data to load")
            return

        # Delete existing results for this session
        await conn.execute("DELETE FROM results WHERE session_id = $1", session_id)

        records = []
        for _, row in results.iterrows():
            records.append((
                session_id,
                row.get("Abbreviation", ""),
                str(row.get("DriverNumber", "")),
                row.get("FullName", ""),
                row.get("TeamName", ""),
                int(row["Position"]) if pd.notna(row.get("Position")) else None,
                int(row["GridPosition"]) if pd.notna(row.get("GridPosition")) else None,
                row.get("Status", ""),
                float(row["Points"]) if pd.notna(row.get("Points")) else 0,
                row.get("TimeSeconds"),
                row.get("Q1Seconds"),
                row.get("Q2Seconds"),
                row.get("Q3Seconds"),
            ))

        if records:
            await conn.executemany(
                """
                INSERT INTO results (session_id, driver_id, driver_number, driver_name,
                    team, position, grid_position, status, points, time_seconds,
                    q1_seconds, q2_seconds, q3_seconds)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (session_id, driver_id) DO NOTHING
                """,
                records,
            )
            logger.info(f"Loaded {len(records)} result records")

    async def _load_telemetry(self, conn, session_id: str, telemetry: dict[str, pd.DataFrame]):
        """Load telemetry data for all drivers."""
        if not telemetry:
            logger.debug("No telemetry data to load")
            return

        # Delete existing telemetry for this session
        await conn.execute("DELETE FROM telemetry WHERE session_id = $1", session_id)

        total_records = 0
        for driver_id, tel_df in telemetry.items():
            if tel_df is None or len(tel_df) == 0:
                continue

            # Sample telemetry if too large (keep every Nth point)
            # Full telemetry can be 50k+ points per driver per session
            if len(tel_df) > 10000:
                # Keep ~10k points per driver
                sample_rate = len(tel_df) // 10000
                tel_df = tel_df.iloc[::sample_rate].copy()
                logger.debug(f"Sampled telemetry for {driver_id}: {len(tel_df)} points")

            records = []
            for _, row in tel_df.iterrows():
                # Get timestamp
                time_val = row.get("Date")
                if pd.isna(time_val):
                    # Use SessionTime as fallback
                    time_val = row.get("SessionTime")
                if pd.isna(time_val):
                    continue

                records.append((
                    time_val,
                    session_id,
                    driver_id,
                    float(row["Distance"]) if pd.notna(row.get("Distance")) else None,
                    float(row["Speed"]) if pd.notna(row.get("Speed")) else None,
                    int(row["RPM"]) if pd.notna(row.get("RPM")) else None,
                    int(row["nGear"]) if pd.notna(row.get("nGear")) else None,
                    float(row["Throttle"]) if pd.notna(row.get("Throttle")) else None,
                    float(row["Brake"]) if pd.notna(row.get("Brake")) else None,
                    int(row["DRS"]) if pd.notna(row.get("DRS")) else None,
                    float(row["X"]) if pd.notna(row.get("X")) else None,
                    float(row["Y"]) if pd.notna(row.get("Y")) else None,
                    float(row["Z"]) if pd.notna(row.get("Z")) else None,
                ))

            if records:
                # Batch insert in chunks
                chunk_size = 5000
                for i in range(0, len(records), chunk_size):
                    chunk = records[i : i + chunk_size]
                    await conn.executemany(
                        """
                        INSERT INTO telemetry (time, session_id, driver_id, distance,
                            speed, rpm, gear, throttle, brake, drs,
                            position_x, position_y, position_z)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        """,
                        chunk,
                    )
                total_records += len(records)

        logger.info(f"Loaded {total_records} telemetry records")

    async def _load_weather(self, conn, session_id: str, weather: pd.DataFrame):
        """Load weather data."""
        if weather is None or len(weather) == 0:
            logger.debug("No weather data to load")
            return

        # Delete existing weather for this session
        await conn.execute("DELETE FROM weather WHERE session_id = $1", session_id)

        records = []
        for _, row in weather.iterrows():
            time_val = row.get("Time")
            if pd.isna(time_val):
                continue

            # Weather data's Time column is often a Timedelta from session start
            # Convert to a datetime by adding to a reference date
            if isinstance(time_val, pd.Timedelta):
                # Use a reference datetime (epoch + timedelta offset)
                from datetime import datetime, timezone
                time_val = datetime(2000, 1, 1, tzinfo=timezone.utc) + time_val
            elif hasattr(time_val, 'tz') and time_val.tz is None:
                time_val = time_val.tz_localize('UTC')
            if hasattr(time_val, 'to_pydatetime'):
                time_val = time_val.to_pydatetime()

            records.append((
                time_val,
                session_id,
                float(row["AirTemp"]) if pd.notna(row.get("AirTemp")) else None,
                float(row["TrackTemp"]) if pd.notna(row.get("TrackTemp")) else None,
                float(row["Humidity"]) if pd.notna(row.get("Humidity")) else None,
                float(row["Pressure"]) if pd.notna(row.get("Pressure")) else None,
                float(row["WindSpeed"]) if pd.notna(row.get("WindSpeed")) else None,
                int(row["WindDirection"]) if pd.notna(row.get("WindDirection")) else None,
                bool(row.get("Rainfall", False)),
            ))

        if records:
            await conn.executemany(
                """
                INSERT INTO weather (time, session_id, air_temp, track_temp,
                    humidity, pressure, wind_speed, wind_direction, rainfall)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                records,
            )
            logger.info(f"Loaded {len(records)} weather records")

    async def get_session_count(self) -> int:
        """Get the number of sessions loaded."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("SELECT COUNT(*) FROM sessions")
            return result or 0

    async def get_lap_count(self) -> int:
        """Get the total number of laps loaded."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("SELECT COUNT(*) FROM lap_times")
            return result or 0
