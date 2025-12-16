"""
F1 RIA Validation Module

Provides input validation and structured error handling for edge cases:
- Invalid race names/years
- Drivers not participating in a race
- Missing telemetry data
- Ambiguous queries
- Data not found scenarios
"""

import logging
from enum import Enum
from typing import Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# ERROR TYPES
# ============================================================

class ErrorCode(Enum):
    """Structured error codes for better error handling."""
    # Validation errors
    INVALID_YEAR = "INVALID_YEAR"
    INVALID_RACE_NAME = "INVALID_RACE_NAME"
    INVALID_DRIVER = "INVALID_DRIVER"
    INVALID_SESSION_TYPE = "INVALID_SESSION_TYPE"

    # Data not found errors
    RACE_NOT_FOUND = "RACE_NOT_FOUND"
    DRIVER_NOT_IN_RACE = "DRIVER_NOT_IN_RACE"
    NO_TELEMETRY_DATA = "NO_TELEMETRY_DATA"
    NO_RESULTS_DATA = "NO_RESULTS_DATA"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"

    # Database errors
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    DATABASE_QUERY_ERROR = "DATABASE_QUERY_ERROR"
    DATABASE_TIMEOUT = "DATABASE_TIMEOUT"

    # Rate limiting
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"

    # Ambiguity errors
    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"
    MULTIPLE_MATCHES = "MULTIPLE_MATCHES"

    # Generic
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class ValidationResult:
    """Result of validation with structured error info."""
    is_valid: bool
    error_code: ErrorCode | None = None
    error_message: str | None = None
    suggestion: str | None = None
    alternatives: list[str] | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"is_valid": self.is_valid}
        if not self.is_valid:
            result["error"] = {
                "code": self.error_code.value if self.error_code else "UNKNOWN",
                "message": self.error_message or "Unknown error",
            }
            if self.suggestion:
                result["error"]["suggestion"] = self.suggestion
            if self.alternatives:
                result["error"]["alternatives"] = self.alternatives
        return result


# ============================================================
# CONSTANTS
# ============================================================

# Valid F1 season years (first championship was 1950)
MIN_F1_YEAR = 1950
MAX_F1_YEAR = datetime.now().year + 1  # Allow next year for upcoming season

# Valid session types
VALID_SESSION_TYPES = {"R", "Q", "FP1", "FP2", "FP3", "S", "SQ"}

# Common race name aliases
RACE_NAME_ALIASES = {
    # Full names to canonical
    "monaco": "Monaco Grand Prix",
    "monza": "Italian Grand Prix",
    "silverstone": "British Grand Prix",
    "spa": "Belgian Grand Prix",
    "suzuka": "Japanese Grand Prix",
    "interlagos": "Brazilian Grand Prix",
    "sao paulo": "Brazilian Grand Prix",
    "singapore": "Singapore Grand Prix",
    "bahrain": "Bahrain Grand Prix",
    "jeddah": "Saudi Arabian Grand Prix",
    "saudi": "Saudi Arabian Grand Prix",
    "australia": "Australian Grand Prix",
    "melbourne": "Australian Grand Prix",
    "miami": "Miami Grand Prix",
    "canada": "Canadian Grand Prix",
    "montreal": "Canadian Grand Prix",
    "austria": "Austrian Grand Prix",
    "spielberg": "Austrian Grand Prix",
    "red bull ring": "Austrian Grand Prix",
    "hungary": "Hungarian Grand Prix",
    "hungaroring": "Hungarian Grand Prix",
    "zandvoort": "Dutch Grand Prix",
    "netherlands": "Dutch Grand Prix",
    "barcelona": "Spanish Grand Prix",
    "spain": "Spanish Grand Prix",
    "baku": "Azerbaijan Grand Prix",
    "azerbaijan": "Azerbaijan Grand Prix",
    "las vegas": "Las Vegas Grand Prix",
    "vegas": "Las Vegas Grand Prix",
    "qatar": "Qatar Grand Prix",
    "abu dhabi": "Abu Dhabi Grand Prix",
    "yas marina": "Abu Dhabi Grand Prix",
    "mexico": "Mexico City Grand Prix",
    "usa": "United States Grand Prix",
    "austin": "United States Grand Prix",
    "cota": "United States Grand Prix",
    "china": "Chinese Grand Prix",
    "shanghai": "Chinese Grand Prix",
    "imola": "Emilia Romagna Grand Prix",
}

# Common driver abbreviations and full names
DRIVER_ABBREVIATIONS = {
    # Current drivers (2024)
    "VER": "Max Verstappen",
    "PER": "Sergio Perez",
    "HAM": "Lewis Hamilton",
    "RUS": "George Russell",
    "LEC": "Charles Leclerc",
    "SAI": "Carlos Sainz",
    "NOR": "Lando Norris",
    "PIA": "Oscar Piastri",
    "ALO": "Fernando Alonso",
    "STR": "Lance Stroll",
    "GAS": "Pierre Gasly",
    "OCO": "Esteban Ocon",
    "ALB": "Alexander Albon",
    "SAR": "Logan Sargeant",
    "BOT": "Valtteri Bottas",
    "ZHO": "Zhou Guanyu",
    "MAG": "Kevin Magnussen",
    "HUL": "Nico Hulkenberg",
    "TSU": "Yuki Tsunoda",
    "RIC": "Daniel Ricciardo",
    "LAW": "Liam Lawson",
    "BEA": "Oliver Bearman",
    # Historical drivers
    "VET": "Sebastian Vettel",
    "RAI": "Kimi Raikkonen",
    "MSC": "Michael Schumacher",
    "SCH": "Mick Schumacher",
    "GIO": "Antonio Giovinazzi",
    "LAT": "Nicholas Latifi",
    "MAZ": "Nikita Mazepin",
    "KUB": "Robert Kubica",
    "ROS": "Nico Rosberg",
    "BUT": "Jenson Button",
    "WEB": "Mark Webber",
    "MAS": "Felipe Massa",
    "BAR": "Rubens Barrichello",
}

# Driver name variations (for fuzzy matching)
DRIVER_NAME_VARIATIONS = {
    "verstappen": "VER",
    "max": "VER",
    "hamilton": "HAM",
    "lewis": "HAM",
    "leclerc": "LEC",
    "charles": "LEC",
    "norris": "NOR",
    "lando": "NOR",
    "sainz": "SAI",
    "carlos": "SAI",
    "russell": "RUS",
    "george": "RUS",
    "perez": "PER",
    "sergio": "PER",
    "checo": "PER",
    "alonso": "ALO",
    "fernando": "ALO",
    "piastri": "PIA",
    "oscar": "PIA",
    "gasly": "GAS",
    "pierre": "GAS",
    "ocon": "OCO",
    "esteban": "OCO",
    "stroll": "STR",
    "lance": "STR",
    "albon": "ALB",
    "alex": "ALB",
    "bottas": "BOT",
    "valtteri": "BOT",
    "tsunoda": "TSU",
    "yuki": "TSU",
    "ricciardo": "RIC",
    "daniel": "RIC",
    "magnussen": "MAG",
    "kevin": "MAG",
    "hulkenberg": "HUL",
    "nico": "HUL",
    "zhou": "ZHO",
    "guanyu": "ZHO",
    "vettel": "VET",
    "sebastian": "VET",
    "raikkonen": "RAI",
    "kimi": "RAI",
    "schumacher": "MSC",
    "michael": "MSC",
}


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def validate_year(year: int | None) -> ValidationResult:
    """
    Validate that a year is a valid F1 season.

    Args:
        year: Season year to validate

    Returns:
        ValidationResult with error details if invalid
    """
    if year is None:
        return ValidationResult(is_valid=True)

    if not isinstance(year, int):
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.INVALID_YEAR,
            error_message=f"Year must be an integer, got {type(year).__name__}",
            suggestion="Provide a valid year like 2024",
        )

    if year < MIN_F1_YEAR:
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.INVALID_YEAR,
            error_message=f"Year {year} is before F1 World Championship started",
            suggestion=f"F1 World Championship began in {MIN_F1_YEAR}. Use a year from {MIN_F1_YEAR} onwards.",
        )

    if year > MAX_F1_YEAR:
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.INVALID_YEAR,
            error_message=f"Year {year} is in the future",
            suggestion=f"Use a year up to {MAX_F1_YEAR}. Current available data is typically up to the current season.",
        )

    return ValidationResult(is_valid=True)


def validate_driver(driver_id: str | None) -> ValidationResult:
    """
    Validate and normalize a driver identifier.

    Args:
        driver_id: Driver abbreviation or name to validate

    Returns:
        ValidationResult with normalized driver abbreviation
    """
    if driver_id is None:
        return ValidationResult(is_valid=True)

    if not isinstance(driver_id, str):
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.INVALID_DRIVER,
            error_message=f"Driver ID must be a string, got {type(driver_id).__name__}",
            suggestion="Use a 3-letter driver code like 'VER' or 'HAM'",
        )

    driver_upper = driver_id.upper().strip()
    driver_lower = driver_id.lower().strip()

    # Check if it's a valid 3-letter code
    if len(driver_upper) == 3 and driver_upper in DRIVER_ABBREVIATIONS:
        return ValidationResult(is_valid=True)

    # Check if it's a name variation we can map
    if driver_lower in DRIVER_NAME_VARIATIONS:
        normalized = DRIVER_NAME_VARIATIONS[driver_lower]
        return ValidationResult(
            is_valid=True,
            suggestion=f"Normalized '{driver_id}' to '{normalized}' ({DRIVER_ABBREVIATIONS[normalized]})",
        )

    # Try to find similar drivers
    similar_drivers = []
    for abbr, name in DRIVER_ABBREVIATIONS.items():
        if driver_lower in name.lower() or driver_lower in abbr.lower():
            similar_drivers.append(f"{abbr} ({name})")

    if similar_drivers:
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.INVALID_DRIVER,
            error_message=f"Driver '{driver_id}' not found",
            suggestion="Did you mean one of these drivers?",
            alternatives=similar_drivers[:5],
        )

    return ValidationResult(
        is_valid=False,
        error_code=ErrorCode.INVALID_DRIVER,
        error_message=f"Driver '{driver_id}' not recognized",
        suggestion="Use a 3-letter driver code (e.g., VER, HAM, LEC) or a driver name",
        alternatives=list(DRIVER_ABBREVIATIONS.keys())[:10],
    )


def validate_race_name(race_name: str | None) -> ValidationResult:
    """
    Validate and normalize a race name.

    Args:
        race_name: Race name to validate

    Returns:
        ValidationResult with canonical race name if found
    """
    if race_name is None:
        return ValidationResult(is_valid=True)

    if not isinstance(race_name, str):
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.INVALID_RACE_NAME,
            error_message=f"Race name must be a string, got {type(race_name).__name__}",
        )

    race_lower = race_name.lower().strip()

    # Check if it's a known alias
    if race_lower in RACE_NAME_ALIASES:
        canonical = RACE_NAME_ALIASES[race_lower]
        return ValidationResult(
            is_valid=True,
            suggestion=f"Normalized '{race_name}' to '{canonical}'",
        )

    # Check for partial matches
    matches = []
    for alias, canonical in RACE_NAME_ALIASES.items():
        if race_lower in alias or alias in race_lower:
            matches.append(canonical)
        elif race_lower in canonical.lower():
            matches.append(canonical)

    matches = list(set(matches))  # Remove duplicates

    if len(matches) == 1:
        return ValidationResult(
            is_valid=True,
            suggestion=f"Matched '{race_name}' to '{matches[0]}'",
        )
    elif len(matches) > 1:
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.MULTIPLE_MATCHES,
            error_message=f"Race name '{race_name}' is ambiguous",
            suggestion="Please specify which race you mean:",
            alternatives=matches[:5],
        )

    # No matches found - still valid but warn
    return ValidationResult(
        is_valid=True,
        suggestion=f"Race '{race_name}' not in common aliases. Will search database directly.",
    )


def validate_session_type(session_type: str | None) -> ValidationResult:
    """
    Validate a session type.

    Args:
        session_type: Session type to validate (R, Q, FP1, FP2, FP3, S, SQ)

    Returns:
        ValidationResult with error if invalid
    """
    if session_type is None:
        return ValidationResult(is_valid=True)

    session_upper = session_type.upper().strip()

    # Common aliases
    aliases = {
        "RACE": "R",
        "QUALIFYING": "Q",
        "QUALI": "Q",
        "SPRINT": "S",
        "SPRINT QUALI": "SQ",
        "PRACTICE 1": "FP1",
        "PRACTICE 2": "FP2",
        "PRACTICE 3": "FP3",
        "FREE PRACTICE 1": "FP1",
        "FREE PRACTICE 2": "FP2",
        "FREE PRACTICE 3": "FP3",
    }

    if session_upper in aliases:
        session_upper = aliases[session_upper]

    if session_upper in VALID_SESSION_TYPES:
        return ValidationResult(is_valid=True)

    return ValidationResult(
        is_valid=False,
        error_code=ErrorCode.INVALID_SESSION_TYPE,
        error_message=f"Invalid session type '{session_type}'",
        suggestion="Valid session types are:",
        alternatives=["R (Race)", "Q (Qualifying)", "FP1/FP2/FP3 (Practice)", "S (Sprint)", "SQ (Sprint Qualifying)"],
    )


def normalize_driver_id(driver_id: str) -> str:
    """
    Normalize a driver identifier to 3-letter abbreviation.

    Args:
        driver_id: Driver name or abbreviation

    Returns:
        Normalized 3-letter code (uppercase)
    """
    if not driver_id:
        return ""

    driver_upper = driver_id.upper().strip()
    driver_lower = driver_id.lower().strip()

    # Already a valid abbreviation
    if len(driver_upper) == 3 and driver_upper in DRIVER_ABBREVIATIONS:
        return driver_upper

    # Try name mapping
    if driver_lower in DRIVER_NAME_VARIATIONS:
        return DRIVER_NAME_VARIATIONS[driver_lower]

    # Return uppercase as-is (let database query handle it)
    return driver_upper


def normalize_race_name(race_name: str) -> str:
    """
    Normalize a race name to canonical form if known.

    Args:
        race_name: Race name or alias

    Returns:
        Canonical race name or original input
    """
    if not race_name:
        return ""

    race_lower = race_name.lower().strip()

    if race_lower in RACE_NAME_ALIASES:
        return RACE_NAME_ALIASES[race_lower]

    return race_name


# ============================================================
# RESULT VALIDATION
# ============================================================

def validate_tool_result(
    result: Any,
    tool_name: str,
    expected_keys: list[str] | None = None,
) -> ValidationResult:
    """
    Validate the result from a tool execution.

    Args:
        result: Tool execution result
        tool_name: Name of the tool that was executed
        expected_keys: Expected keys in result dict

    Returns:
        ValidationResult indicating data quality
    """
    # Check for explicit errors
    if isinstance(result, dict) and "error" in result:
        error_msg = result.get("error", "Unknown error")

        # Classify error type
        if "connection" in error_msg.lower():
            return ValidationResult(
                is_valid=False,
                error_code=ErrorCode.DATABASE_CONNECTION_ERROR,
                error_message=error_msg,
                suggestion="Database connection issue. Please try again.",
            )
        elif "timeout" in error_msg.lower():
            return ValidationResult(
                is_valid=False,
                error_code=ErrorCode.DATABASE_TIMEOUT,
                error_message=error_msg,
                suggestion="Query took too long. Try adding more specific filters.",
            )
        else:
            return ValidationResult(
                is_valid=False,
                error_code=ErrorCode.DATABASE_QUERY_ERROR,
                error_message=error_msg,
            )

    # Check for empty results
    if isinstance(result, list):
        if len(result) == 0:
            return ValidationResult(
                is_valid=False,
                error_code=ErrorCode.NO_RESULTS_DATA,
                error_message=f"No data returned from {tool_name}",
                suggestion="Try adjusting your search parameters (year, driver, race name).",
            )

        # Check if first item has error
        if result[0].get("error"):
            return ValidationResult(
                is_valid=False,
                error_code=ErrorCode.DATABASE_QUERY_ERROR,
                error_message=result[0]["error"],
            )

    if isinstance(result, dict):
        if not result or all(v is None for v in result.values()):
            return ValidationResult(
                is_valid=False,
                error_code=ErrorCode.NO_RESULTS_DATA,
                error_message=f"No data returned from {tool_name}",
            )

        # Check expected keys if provided
        if expected_keys:
            missing = [k for k in expected_keys if k not in result]
            if missing:
                return ValidationResult(
                    is_valid=True,
                    suggestion=f"Result missing expected fields: {missing}",
                )

    return ValidationResult(is_valid=True)


def check_driver_in_result(
    result: list[dict],
    driver_id: str,
) -> ValidationResult:
    """
    Check if a driver appears in the query result.

    Args:
        result: Query result list
        driver_id: Driver to check for

    Returns:
        ValidationResult indicating if driver was found
    """
    if not result:
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.DRIVER_NOT_IN_RACE,
            error_message=f"No data found for driver {driver_id}",
            suggestion="This driver may not have participated in the specified race/session.",
        )

    driver_upper = normalize_driver_id(driver_id)

    found_drivers = set()
    for row in result:
        if row.get("driver_id"):
            found_drivers.add(row["driver_id"].upper())

    if driver_upper not in found_drivers:
        return ValidationResult(
            is_valid=False,
            error_code=ErrorCode.DRIVER_NOT_IN_RACE,
            error_message=f"Driver {driver_upper} not found in this session",
            suggestion="This driver may not have participated. Available drivers:",
            alternatives=sorted(list(found_drivers))[:10],
        )

    return ValidationResult(is_valid=True)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def create_user_friendly_error(
    error_code: ErrorCode,
    context: dict | None = None,
) -> str:
    """
    Create a user-friendly error message for display.

    Args:
        error_code: The error code
        context: Additional context like driver, year, race

    Returns:
        Human-readable error message
    """
    context = context or {}

    messages = {
        ErrorCode.INVALID_YEAR: "The year {year} is not valid for F1 data. F1 World Championship runs from 1950 to present.",
        ErrorCode.INVALID_RACE_NAME: "I couldn't find a race matching '{race}'. Try using the full Grand Prix name (e.g., 'Monaco Grand Prix').",
        ErrorCode.INVALID_DRIVER: "I don't recognize the driver '{driver}'. Use a 3-letter code (VER, HAM) or full name.",
        ErrorCode.RACE_NOT_FOUND: "No race data found for {race} {year}. This race may not have occurred or data isn't available yet.",
        ErrorCode.DRIVER_NOT_IN_RACE: "{driver} did not participate in this race. They may have been injured, had a seat change, or it was before/after their F1 career.",
        ErrorCode.NO_TELEMETRY_DATA: "Telemetry data is not available for this session. Historical races may have limited data.",
        ErrorCode.NO_RESULTS_DATA: "No results found for your query. Try broadening your search or checking the race/year.",
        ErrorCode.DATABASE_CONNECTION_ERROR: "I'm having trouble connecting to the F1 database. Please try again in a moment.",
        ErrorCode.RATE_LIMITED: "Too many requests. Please wait a moment before asking another question.",
        ErrorCode.AMBIGUOUS_QUERY: "Your question could refer to multiple things. Could you be more specific?",
    }

    template = messages.get(error_code, "An error occurred processing your request.")

    try:
        return template.format(**context)
    except KeyError:
        return template


def suggest_alternatives_for_empty_result(
    query_type: str,
    params: dict,
) -> list[str]:
    """
    Generate helpful suggestions when a query returns no results.

    Args:
        query_type: Type of query (lap_times, results, etc.)
        params: Query parameters used

    Returns:
        List of suggestions for the user
    """
    suggestions = []

    year = params.get("year")
    driver = params.get("driver_id")
    race = params.get("event_name")

    if year:
        if year > 2024:
            suggestions.append(f"The {year} season may not have complete data yet. Try 2024 or earlier.")
        elif year < 2018:
            suggestions.append(f"Detailed telemetry for {year} may be limited. Data coverage improves for 2018 onwards.")

    if driver:
        norm_driver = normalize_driver_id(driver)
        if norm_driver in DRIVER_ABBREVIATIONS:
            suggestions.append(f"Verify {DRIVER_ABBREVIATIONS[norm_driver]} participated in this race.")

    if race:
        norm_race = normalize_race_name(race)
        if norm_race != race:
            suggestions.append(f"Try searching for '{norm_race}' instead.")

    if query_type == "lap_times":
        suggestions.append("Lap time data is typically only available for race sessions, not all practice sessions.")

    if query_type == "weather":
        suggestions.append("Weather data may not be available for all historical races.")

    if not suggestions:
        suggestions.append("Try adjusting your search parameters.")
        suggestions.append("Use broader criteria or check if the race/session exists.")

    return suggestions
