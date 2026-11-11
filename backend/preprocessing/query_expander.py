"""
Query expansion for F1 RIA.

Handles:
- Shortcut expansion ("VER vs NOR" → full comparison context)
- Default context injection (no year → current year)
- Smart inference (natural language → structured intent)
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from preprocessing.fuzzy_matcher import FuzzyMatcher, MatchResult

logger = logging.getLogger(__name__)

# Current F1 season
CURRENT_YEAR = datetime.now().year

# Last season the ingestion pipeline covers (2018-2024). A question that names
# no year, or a relative one ("this season", "last year"), is read against this
# season rather than the calendar year, which has no data.
LATEST_DATA_SEASON = 2024

# Where a query's year came from (ExpandedQuery.inferred_context["year_source"])
YEAR_EXPLICIT = "explicit"  # "2021"
YEAR_RELATIVE = "relative"  # "this season", "last year", "2 years ago"
YEAR_PREVIOUS_TURN = "previous_turn"  # no year; kept from the session's last question
YEAR_DEFAULT = "default"  # no year and no earlier question


def describe_year(year: int, source: str) -> str | None:
    """Short note for the UI when the year was not stated outright."""
    if source == YEAR_DEFAULT:
        return f"assumed {year} (latest season with data)"
    if source == YEAR_RELATIVE:
        return f"read as {year} (data runs to the {LATEST_DATA_SEASON} season)"
    if source == YEAR_PREVIOUS_TURN:
        return f"kept {year} from your earlier question"
    return None


@dataclass
class ExpandedQuery:
    """Result of query expansion."""

    original: str
    expanded: str
    drivers: list[str] = field(default_factory=list)  # Driver codes
    teams: list[str] = field(default_factory=list)  # Team IDs
    circuits: list[str] = field(default_factory=list)  # Circuit IDs
    year: int | None = None
    is_comparison: bool = False
    comparison_type: Literal["driver", "team", None] = None
    inferred_context: dict = field(default_factory=dict)


class QueryExpander:
    """Expands and normalizes F1 queries."""

    # Comparison patterns
    COMPARISON_PATTERNS = [
        r"(\w+)\s+(?:vs\.?|versus|v\.?|against)\s+(\w+)",  # X vs Y
        r"compare\s+(\w+)\s+(?:and|to|with|&)\s+(\w+)",  # compare X and Y
        r"(\w+)\s+(?:compared?\s+to|or)\s+(\w+)",  # X compared to Y
        r"how\s+does\s+(\w+)\s+(?:compare|stack\s+up|match\s+up)\s+(?:to|against|with)\s+(\w+)",
        r"(\w+)\s+(?:better|worse|faster|slower)\s+than\s+(\w+)",  # X faster than Y
        r"difference\s+between\s+(\w+)\s+and\s+(\w+)",  # difference between X and Y
        r"head\s*(?:to|2)\s*head\s+(\w+)\s+(?:and|vs\.?|&)\s+(\w+)",  # head to head X and Y
    ]

    # Year patterns
    YEAR_PATTERNS = [
        r"\b(20[0-2][0-9])\b",  # Direct year mention (2010-2029)
        r"\bthis\s+(?:year|season)\b",  # this year/season
        r"\blast\s+(?:year|season)\b",  # last year/season
        r"\b(\d+)\s+(?:years?\s+)?ago\b",  # X years ago
    ]

    # Race/GP patterns
    RACE_PATTERNS = [
        r"(?:at|in)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s+(?:gp|grand\s+prix|race)",
        r"(\w+(?:\s+\w+)?)\s+(?:gp|grand\s+prix)",
        r"(?:at|in)\s+(\w+(?:\s+\w+)?)\s+(?:circuit|track)",
    ]

    def __init__(self, fuzzy_matcher: FuzzyMatcher | None = None):
        """
        Initialize the query expander.

        Args:
            fuzzy_matcher: FuzzyMatcher instance (created if not provided)
        """
        self.fuzzy_matcher = fuzzy_matcher or FuzzyMatcher()

    def expand(self, query: str, previous_year: int | None = None) -> ExpandedQuery:
        """
        Expand and normalize a query.

        Args:
            query: Raw user query

            previous_year: Year of the session's previous question, used when
                this one names no year (follow-ups like "what about Hamilton?")

        Returns:
            ExpandedQuery with extracted entities and context
        """
        original = query
        expanded = query

        # Extract entities using fuzzy matcher
        entities = self.fuzzy_matcher.extract_entities(query)

        drivers = [e.canonical for e in entities if e.entity_type == "driver"]
        teams = [e.canonical for e in entities if e.entity_type == "team"]
        circuits = [e.canonical for e in entities if e.entity_type == "circuit"]

        # Detect comparison
        is_comparison, comparison_type, comparison_entities = self._detect_comparison(query)

        if is_comparison and comparison_entities:
            # Add comparison entities to drivers/teams if not already present
            for entity in comparison_entities:
                match = self.fuzzy_matcher.match_driver(entity)
                if match and match.canonical not in drivers:
                    drivers.append(match.canonical)
                else:
                    team_match = self.fuzzy_matcher.match_team(entity)
                    if team_match and team_match.canonical not in teams:
                        teams.append(team_match.canonical)

        # Extract/infer year; a follow-up with no year keeps the previous one
        year, year_source = self._extract_year(query)
        if year_source == YEAR_DEFAULT and previous_year is not None:
            year, year_source = previous_year, YEAR_PREVIOUS_TURN

        # Extract circuit from race patterns
        circuit_from_race = self._extract_race_circuit(query)
        if circuit_from_race and circuit_from_race not in circuits:
            circuits.append(circuit_from_race)

        # Build expanded query
        expanded = self._build_expanded_query(
            original, drivers, teams, circuits, year, is_comparison
        )

        # Build inferred context
        inferred_context = {}
        if year and year_source != YEAR_EXPLICIT:
            inferred_context["year_inferred"] = True
            inferred_context["year_source"] = year_source
            inferred_context["year_note"] = describe_year(year, year_source)
        if is_comparison and "vs" not in original.lower() and "compare" not in original.lower():
            inferred_context["comparison_inferred"] = True

        return ExpandedQuery(
            original=original,
            expanded=expanded,
            drivers=drivers,
            teams=teams,
            circuits=circuits,
            year=year,
            is_comparison=is_comparison,
            comparison_type=comparison_type,
            inferred_context=inferred_context,
        )

    def _detect_comparison(self, query: str) -> tuple[bool, str | None, list[str]]:
        """
        Detect if query is a comparison and extract entities.

        Returns:
            (is_comparison, comparison_type, entities)
        """
        query_lower = query.lower()

        for pattern in self.COMPARISON_PATTERNS:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                entities = list(match.groups())

                # Determine comparison type (driver vs team)
                driver_count = sum(1 for e in entities if self.fuzzy_matcher.match_driver(e))
                team_count = sum(1 for e in entities if self.fuzzy_matcher.match_team(e))

                if driver_count >= team_count:
                    comp_type = "driver"
                else:
                    comp_type = "team"

                return True, comp_type, entities

        return False, None, []

    def _extract_year(self, query: str) -> tuple[int, str]:
        """Extract or infer the year, and say where it came from."""
        query_lower = query.lower()

        # Direct year mention
        year_match = re.search(r"\b(20[0-2][0-9])\b", query)
        if year_match:
            return int(year_match.group(1)), YEAR_EXPLICIT

        # Relative years count back from the latest season with data
        latest = min(CURRENT_YEAR, LATEST_DATA_SEASON)

        if re.search(r"\bthis\s+(?:year|season)\b", query_lower):
            return latest, YEAR_RELATIVE

        if re.search(r"\blast\s+(?:year|season)\b", query_lower):
            return latest - 1, YEAR_RELATIVE

        ago_match = re.search(r"\b(\d+)\s+(?:years?\s+)?ago\b", query_lower)
        if ago_match:
            return latest - int(ago_match.group(1)), YEAR_RELATIVE

        # No year given: use the latest season that has data
        return LATEST_DATA_SEASON, YEAR_DEFAULT

    def _extract_race_circuit(self, query: str) -> str | None:
        """Extract circuit from race/GP mentions."""
        query_lower = query.lower()

        for pattern in self.RACE_PATTERNS:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                circuit_name = match.group(1)
                circuit_match = self.fuzzy_matcher.match_circuit(circuit_name)
                if circuit_match:
                    return circuit_match.canonical

        return None

    def _build_expanded_query(
        self,
        original: str,
        drivers: list[str],
        teams: list[str],
        circuits: list[str],
        year: int | None,
        is_comparison: bool,
    ) -> str:
        """Build human-readable expanded query."""
        parts = []

        if is_comparison and len(drivers) >= 2:
            # Get full names for drivers
            driver_names = []
            for code in drivers[:2]:
                match = self.fuzzy_matcher.match_driver(code)
                if match:
                    driver_names.append(match.matched)
                else:
                    driver_names.append(code)
            parts.append(f"{driver_names[0]} vs {driver_names[1]}")
        elif drivers:
            driver_names = []
            for code in drivers:
                match = self.fuzzy_matcher.match_driver(code)
                if match:
                    driver_names.append(match.matched)
                else:
                    driver_names.append(code)
            parts.append(", ".join(driver_names))

        if teams and not drivers:
            team_names = []
            for team_id in teams:
                match = self.fuzzy_matcher.match_team(team_id)
                if match:
                    team_names.append(match.matched)
                else:
                    team_names.append(team_id)
            parts.append(", ".join(team_names))

        if circuits:
            circuit_names = []
            for circuit_id in circuits:
                match = self.fuzzy_matcher.match_circuit(circuit_id)
                if match:
                    circuit_names.append(match.matched)
                else:
                    circuit_names.append(circuit_id)
            circuit_text = ", ".join(circuit_names)
            parts.append(f"at {circuit_text}" if parts else circuit_text)

        if year:
            parts.append(str(year))

        if parts:
            return " ".join(parts)

        return original

    def normalize_driver_mentions(self, query: str) -> str:
        """
        Replace driver mentions with standardized codes.

        Args:
            query: Raw query

        Returns:
            Query with driver names replaced by codes
        """
        result = query
        entities = self.fuzzy_matcher.extract_entities(query)

        # Sort by length of original (longest first) to avoid partial replacements
        driver_entities = [e for e in entities if e.entity_type == "driver"]
        driver_entities.sort(key=lambda e: len(e.original), reverse=True)

        for entity in driver_entities:
            # Replace with code
            result = re.sub(
                re.escape(entity.original),
                entity.canonical,
                result,
                flags=re.IGNORECASE,
            )

        return result
