"""
Fuzzy matching for F1 entity names.

Handles typo correction and alias resolution for:
- Driver names (verstapen → Verstappen, Max → Verstappen)
- Team names (redbull → Red Bull Racing, merc → Mercedes)
- Circuit names (silverston → Silverstone)
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of a fuzzy match."""
    original: str
    matched: str
    canonical: str  # Standardized form (e.g., driver code)
    entity_type: Literal["driver", "team", "circuit"]
    confidence: float  # 0.0 to 1.0


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


class FuzzyMatcher:
    """Fuzzy matcher for F1 entities."""

    def __init__(self, data_dir: str | Path | None = None):
        """
        Initialize the fuzzy matcher.

        Args:
            data_dir: Path to directory containing JSON data files
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        else:
            data_dir = Path(data_dir)

        self.drivers = self._load_drivers(data_dir / "drivers.json")
        self.teams = self._load_teams(data_dir / "teams.json")
        self.circuits = self._load_circuits(data_dir / "circuits.json")

        # Build lookup indices
        self._build_indices()

        logger.info(
            f"FuzzyMatcher initialized: {len(self.drivers)} drivers, "
            f"{len(self.teams)} teams, {len(self.circuits)} circuits"
        )

    def _load_drivers(self, path: Path) -> list[dict]:
        """Load driver data from JSON."""
        try:
            with open(path) as f:
                data = json.load(f)
                return data.get("drivers", []) + data.get("historic_drivers", [])
        except Exception as e:
            logger.error(f"Failed to load drivers: {e}")
            return []

    def _load_teams(self, path: Path) -> list[dict]:
        """Load team data from JSON."""
        try:
            with open(path) as f:
                data = json.load(f)
                return data.get("teams", []) + data.get("historic_teams", [])
        except Exception as e:
            logger.error(f"Failed to load teams: {e}")
            return []

    def _load_circuits(self, path: Path) -> list[dict]:
        """Load circuit data from JSON."""
        try:
            with open(path) as f:
                data = json.load(f)
                return data.get("circuits", [])
        except Exception as e:
            logger.error(f"Failed to load circuits: {e}")
            return []

    def _build_indices(self):
        """Build lookup indices for fast matching."""
        # Driver index: alias/name → driver data
        self.driver_index: dict[str, dict] = {}
        for driver in self.drivers:
            code = driver.get("code", "").upper()
            # Add code
            self.driver_index[code.lower()] = driver
            # Add full name
            full_name = driver.get("full_name", "").lower()
            self.driver_index[full_name] = driver
            # Add first/last names
            self.driver_index[driver.get("first_name", "").lower()] = driver
            self.driver_index[driver.get("last_name", "").lower()] = driver
            # Add aliases
            for alias in driver.get("aliases", []):
                self.driver_index[alias.lower()] = driver

        # Team index: alias/name → team data
        self.team_index: dict[str, dict] = {}
        for team in self.teams:
            team_id = team.get("id", "")
            self.team_index[team_id.lower()] = team
            self.team_index[team.get("full_name", "").lower()] = team
            self.team_index[team.get("short_name", "").lower()] = team
            for alias in team.get("aliases", []):
                self.team_index[alias.lower()] = team

        # Circuit index: alias/name → circuit data
        self.circuit_index: dict[str, dict] = {}
        for circuit in self.circuits:
            circuit_id = circuit.get("id", "")
            self.circuit_index[circuit_id.lower()] = circuit
            self.circuit_index[circuit.get("full_name", "").lower()] = circuit
            self.circuit_index[circuit.get("short_name", "").lower()] = circuit
            self.circuit_index[circuit.get("country", "").lower()] = circuit
            self.circuit_index[circuit.get("city", "").lower()] = circuit
            for alias in circuit.get("aliases", []):
                self.circuit_index[alias.lower()] = circuit

    def match_driver(self, text: str, max_distance: int = 2) -> MatchResult | None:
        """
        Match text to a driver.

        Args:
            text: Text to match
            max_distance: Maximum Levenshtein distance for fuzzy matching

        Returns:
            MatchResult if found, None otherwise
        """
        text_lower = text.lower().strip()

        # Exact match first
        if text_lower in self.driver_index:
            driver = self.driver_index[text_lower]
            return MatchResult(
                original=text,
                matched=driver.get("full_name", ""),
                canonical=driver.get("code", ""),
                entity_type="driver",
                confidence=1.0,
            )

        # Check if it's already a 3-letter code
        if len(text_lower) == 3 and text_lower.isalpha():
            text_upper = text_lower.upper()
            for driver in self.drivers:
                if driver.get("code", "").upper() == text_upper:
                    return MatchResult(
                        original=text,
                        matched=driver.get("full_name", ""),
                        canonical=driver.get("code", ""),
                        entity_type="driver",
                        confidence=1.0,
                    )

        # Fuzzy match
        best_match = None
        best_distance = max_distance + 1

        for key, driver in self.driver_index.items():
            distance = levenshtein_distance(text_lower, key)
            if distance <= max_distance and distance < best_distance:
                best_distance = distance
                best_match = driver

        if best_match:
            # Confidence decreases with distance
            confidence = 1.0 - (best_distance / (max_distance + 1))
            return MatchResult(
                original=text,
                matched=best_match.get("full_name", ""),
                canonical=best_match.get("code", ""),
                entity_type="driver",
                confidence=confidence,
            )

        return None

    def match_team(self, text: str, max_distance: int = 2) -> MatchResult | None:
        """
        Match text to a team.

        Args:
            text: Text to match
            max_distance: Maximum Levenshtein distance for fuzzy matching

        Returns:
            MatchResult if found, None otherwise
        """
        text_lower = text.lower().strip()

        # Exact match first
        if text_lower in self.team_index:
            team = self.team_index[text_lower]
            return MatchResult(
                original=text,
                matched=team.get("short_name", team.get("full_name", "")),
                canonical=team.get("id", ""),
                entity_type="team",
                confidence=1.0,
            )

        # Fuzzy match
        best_match = None
        best_distance = max_distance + 1

        for key, team in self.team_index.items():
            distance = levenshtein_distance(text_lower, key)
            if distance <= max_distance and distance < best_distance:
                best_distance = distance
                best_match = team

        if best_match:
            confidence = 1.0 - (best_distance / (max_distance + 1))
            return MatchResult(
                original=text,
                matched=best_match.get("short_name", best_match.get("full_name", "")),
                canonical=best_match.get("id", ""),
                entity_type="team",
                confidence=confidence,
            )

        return None

    def match_circuit(self, text: str, max_distance: int = 2) -> MatchResult | None:
        """
        Match text to a circuit.

        Args:
            text: Text to match
            max_distance: Maximum Levenshtein distance for fuzzy matching

        Returns:
            MatchResult if found, None otherwise
        """
        text_lower = text.lower().strip()

        # Exact match first
        if text_lower in self.circuit_index:
            circuit = self.circuit_index[text_lower]
            return MatchResult(
                original=text,
                matched=circuit.get("short_name", circuit.get("full_name", "")),
                canonical=circuit.get("id", ""),
                entity_type="circuit",
                confidence=1.0,
            )

        # Fuzzy match
        best_match = None
        best_distance = max_distance + 1

        for key, circuit in self.circuit_index.items():
            distance = levenshtein_distance(text_lower, key)
            if distance <= max_distance and distance < best_distance:
                best_distance = distance
                best_match = circuit

        if best_match:
            confidence = 1.0 - (best_distance / (max_distance + 1))
            return MatchResult(
                original=text,
                matched=best_match.get("short_name", best_match.get("full_name", "")),
                canonical=best_match.get("id", ""),
                entity_type="circuit",
                confidence=confidence,
            )

        return None

    def match_any(self, text: str, max_distance: int = 2) -> MatchResult | None:
        """
        Try to match text to any entity type.

        Tries driver first, then team, then circuit.

        Args:
            text: Text to match
            max_distance: Maximum Levenshtein distance for fuzzy matching

        Returns:
            MatchResult if found, None otherwise
        """
        # Try driver first (most common)
        result = self.match_driver(text, max_distance)
        if result and result.confidence >= 0.7:
            return result

        # Try team
        team_result = self.match_team(text, max_distance)
        if team_result:
            if result is None or team_result.confidence > result.confidence:
                result = team_result

        # Try circuit
        circuit_result = self.match_circuit(text, max_distance)
        if circuit_result:
            if result is None or circuit_result.confidence > result.confidence:
                result = circuit_result

        return result

    def extract_entities(self, text: str) -> list[MatchResult]:
        """
        Extract all F1 entities from text.

        Args:
            text: Text to analyze

        Returns:
            List of matched entities
        """
        results = []

        # Split text into words and try to match each
        words = re.findall(r'\b[\w-]+\b', text)

        # Also try consecutive word pairs (for names like "Max Verstappen")
        word_pairs = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]

        # Try pairs first (longer matches)
        matched_indices = set()
        for i, pair in enumerate(word_pairs):
            result = self.match_any(pair, max_distance=1)
            if result and result.confidence >= 0.8:
                results.append(result)
                matched_indices.add(i)
                matched_indices.add(i + 1)

        # Then try individual words
        for i, word in enumerate(words):
            if i in matched_indices:
                continue
            if len(word) < 2:
                continue
            result = self.match_any(word, max_distance=2)
            if result and result.confidence >= 0.6:
                results.append(result)

        # Deduplicate by canonical form
        seen = set()
        unique_results = []
        for result in results:
            key = (result.canonical, result.entity_type)
            if key not in seen:
                seen.add(key)
                unique_results.append(result)

        return unique_results

    def get_driver_code(self, name: str) -> str | None:
        """Get driver code from name/alias."""
        result = self.match_driver(name)
        return result.canonical if result else None

    def get_team_id(self, name: str) -> str | None:
        """Get team ID from name/alias."""
        result = self.match_team(name)
        return result.canonical if result else None

    def get_circuit_id(self, name: str) -> str | None:
        """Get circuit ID from name/alias."""
        result = self.match_circuit(name)
        return result.canonical if result else None
