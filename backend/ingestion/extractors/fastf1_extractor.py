"""
FastF1 Data Extractor

Extracts F1 telemetry, lap times, results, and weather data from the FastF1 library.
FastF1 provides official F1 timing data from 2018 onwards.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fastf1
import pandas as pd
from fastf1.core import Session

logger = logging.getLogger(__name__)


@dataclass
class RaceWeekend:
    """Metadata for a race weekend."""

    year: int
    round_number: int
    event_name: str
    circuit: str
    country: str
    sessions: list[str] = field(default_factory=list)


@dataclass
class ExtractedSession:
    """All extracted data from a single session."""

    year: int
    round_number: int
    event_name: str
    circuit: str
    session_type: str  # FP1, FP2, FP3, Q, SQ, SS, S, R
    session_date: pd.Timestamp | None
    laps: pd.DataFrame
    telemetry: dict[str, pd.DataFrame]  # driver_id -> telemetry DataFrame
    results: pd.DataFrame
    weather: pd.DataFrame


class FastF1Extractor:
    """Extract F1 data from FastF1 library."""

    def __init__(self, cache_dir: str = "/root/.fastf1_cache"):
        """
        Initialize the extractor.

        Args:
            cache_dir: Directory to cache downloaded data (speeds up subsequent runs)
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(self.cache_dir))
        logger.info(f"FastF1 cache enabled at {self.cache_dir}")

    def get_available_races(
        self, start_year: int = 2018, end_year: int = 2024
    ) -> list[RaceWeekend]:
        """
        Get all available race weekends in the given year range.

        Args:
            start_year: First year to include (default: 2018, earliest with telemetry)
            end_year: Last year to include

        Returns:
            List of RaceWeekend objects
        """
        races = []

        for year in range(start_year, end_year + 1):
            try:
                schedule = fastf1.get_event_schedule(year)

                for _, event in schedule.iterrows():
                    # Skip testing events
                    if event["EventFormat"] == "testing":
                        continue

                    # Skip events that haven't happened yet
                    if pd.isna(event["EventDate"]):
                        continue

                    races.append(
                        RaceWeekend(
                            year=year,
                            round_number=int(event["RoundNumber"]),
                            event_name=event["EventName"],
                            circuit=event["Location"],
                            country=event.get("Country", ""),
                            sessions=self._get_session_types(event["EventFormat"]),
                        )
                    )

                logger.info(f"Found {len([r for r in races if r.year == year])} races for {year}")

            except Exception as e:
                logger.error(f"Failed to get schedule for {year}: {e}")

        return races

    def extract_session(
        self,
        year: int,
        round_number: int,
        session_type: str,
        include_telemetry: bool = True,
    ) -> ExtractedSession | None:
        """
        Extract all data from a single session.

        Args:
            year: Season year
            round_number: Round number in the season
            session_type: Session type (FP1, FP2, FP3, Q, SQ, SS, S, R)
            include_telemetry: Whether to extract detailed telemetry (large data)

        Returns:
            ExtractedSession with all data, or None if extraction fails
        """
        logger.info(f"Extracting {year} Round {round_number} {session_type}")

        try:
            session = fastf1.get_session(year, round_number, session_type)
            session.load(
                telemetry=include_telemetry,
                weather=True,
                messages=False,  # Skip race control messages for now
            )

            # Extract components
            laps = self._extract_laps(session)
            telemetry = self._extract_telemetry(session) if include_telemetry else {}
            results = self._extract_results(session)
            weather = self._extract_weather(session)

            return ExtractedSession(
                year=year,
                round_number=round_number,
                event_name=session.event["EventName"],
                circuit=session.event["Location"],
                session_type=session_type,
                session_date=session.date if hasattr(session, "date") else None,
                laps=laps,
                telemetry=telemetry,
                results=results,
                weather=weather,
            )

        except Exception as e:
            logger.error(f"Failed to extract {year} R{round_number} {session_type}: {e}")
            return None

    def _extract_laps(self, session: Session) -> pd.DataFrame:
        """Extract lap times with sector splits and tire info."""
        if session.laps is None or len(session.laps) == 0:
            return pd.DataFrame()

        laps = session.laps.copy()

        # Select relevant columns (handle missing columns gracefully)
        columns = [
            "Driver",
            "DriverNumber",
            "Team",
            "LapNumber",
            "LapTime",
            "Sector1Time",
            "Sector2Time",
            "Sector3Time",
            "Compound",
            "TyreLife",
            "Stint",
            "IsPersonalBest",
            "Position",
            "Deleted",
            "DeletedReason",
            "LapStartTime",
        ]
        available_columns = [c for c in columns if c in laps.columns]
        laps = laps[available_columns].copy()

        # Convert timedeltas to seconds for easier storage/querying
        time_columns = ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]
        for col in time_columns:
            if col in laps.columns:
                laps[f"{col}Seconds"] = laps[col].dt.total_seconds()

        # Convert LapStartTime to timestamp
        if "LapStartTime" in laps.columns:
            laps["LapStartTime"] = pd.to_datetime(laps["LapStartTime"], errors="coerce")

        logger.info(f"Extracted {len(laps)} laps")
        return laps

    def _extract_telemetry(self, session: Session) -> dict[str, pd.DataFrame]:
        """Extract car telemetry for each driver."""
        telemetry = {}

        if session.laps is None:
            return telemetry

        for driver in session.drivers:
            try:
                driver_laps = session.laps.pick_driver(driver)

                if driver_laps is None or len(driver_laps) == 0:
                    continue

                # Get telemetry for all laps combined
                driver_tel = driver_laps.get_telemetry()

                if driver_tel is not None and len(driver_tel) > 0:
                    # Select relevant columns
                    columns = [
                        "Date",
                        "SessionTime",
                        "Time",
                        "RPM",
                        "Speed",
                        "nGear",
                        "Throttle",
                        "Brake",
                        "DRS",
                        "Distance",
                        "X",
                        "Y",
                        "Z",
                    ]
                    available_columns = [c for c in columns if c in driver_tel.columns]
                    driver_tel = driver_tel[available_columns].copy()

                    driver_tel["Driver"] = driver
                    telemetry[driver] = driver_tel

                    logger.debug(f"Extracted {len(driver_tel)} telemetry points for {driver}")

            except Exception as e:
                logger.warning(f"Failed to extract telemetry for {driver}: {e}")

        logger.info(f"Extracted telemetry for {len(telemetry)} drivers")
        return telemetry

    def _extract_results(self, session: Session) -> pd.DataFrame:
        """Extract session results."""
        if session.results is None or len(session.results) == 0:
            return pd.DataFrame()

        results = session.results.copy()

        # Select relevant columns
        columns = [
            "DriverNumber",
            "Abbreviation",
            "FullName",
            "TeamName",
            "Position",
            "GridPosition",
            "Status",
            "Points",
            "Time",
            "Q1",
            "Q2",
            "Q3",
        ]
        available_columns = [c for c in columns if c in results.columns]
        results = results[available_columns].copy()

        # Convert time columns
        for col in ["Time", "Q1", "Q2", "Q3"]:
            if col in results.columns:
                results[f"{col}Seconds"] = results[col].dt.total_seconds()

        logger.info(f"Extracted results for {len(results)} drivers")
        return results

    def _extract_weather(self, session: Session) -> pd.DataFrame:
        """Extract weather data throughout session."""
        if session.weather_data is None or len(session.weather_data) == 0:
            return pd.DataFrame()

        weather = session.weather_data.copy()

        columns = [
            "Time",
            "AirTemp",
            "TrackTemp",
            "Humidity",
            "Pressure",
            "WindSpeed",
            "WindDirection",
            "Rainfall",
        ]
        available_columns = [c for c in columns if c in weather.columns]
        weather = weather[available_columns].copy()

        logger.info(f"Extracted {len(weather)} weather data points")
        return weather

    def _get_session_types(self, event_format: str) -> list[str]:
        """Get session types for an event format."""
        if event_format == "conventional":
            return ["FP1", "FP2", "FP3", "Q", "R"]
        elif event_format == "sprint":
            return ["FP1", "Q", "SQ", "S", "R"]
        elif event_format == "sprint_shootout":
            return ["FP1", "Q", "SS", "S", "R"]
        elif event_format == "sprint_qualifying":
            return ["FP1", "SQ", "S", "Q", "R"]
        else:
            # Fallback - at minimum we have a race
            return ["R"]

    def extract_race_only(
        self, year: int, round_number: int, include_telemetry: bool = True
    ) -> ExtractedSession | None:
        """
        Convenience method to extract just the race session.

        Args:
            year: Season year
            round_number: Round number
            include_telemetry: Whether to include telemetry data

        Returns:
            ExtractedSession for the race
        """
        return self.extract_session(year, round_number, "R", include_telemetry)
