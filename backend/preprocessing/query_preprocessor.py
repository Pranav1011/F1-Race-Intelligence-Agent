"""
Main query preprocessor for F1 RIA.

Combines fuzzy matching, query expansion, and intent classification
to preprocess user queries before they hit the LLM.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from preprocessing.fuzzy_matcher import FuzzyMatcher, MatchResult
from preprocessing.query_expander import QueryExpander, ExpandedQuery
from preprocessing.intent_classifier import IntentClassifier, ClassifiedIntent

logger = logging.getLogger(__name__)


@dataclass
class PreprocessedQuery:
    """Complete result of query preprocessing."""

    # Original query
    original: str

    # Normalized/expanded version
    normalized: str
    expanded_display: str  # Human-readable version for UI

    # Extracted entities
    drivers: list[str] = field(default_factory=list)  # Driver codes
    teams: list[str] = field(default_factory=list)  # Team IDs
    circuits: list[str] = field(default_factory=list)  # Circuit IDs

    # Inferred context
    year: int | None = None
    is_comparison: bool = False
    comparison_type: str | None = None  # "driver" or "team"

    # Intent classification
    intent: str = "general"
    intent_confidence: float = 0.0
    suggested_tools: list[str] = field(default_factory=list)
    is_simple_query: bool = False

    # Fuzzy match corrections made
    corrections: list[dict] = field(default_factory=list)

    # Hints for LLM
    hints: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "original": self.original,
            "normalized": self.normalized,
            "expanded_display": self.expanded_display,
            "drivers": self.drivers,
            "teams": self.teams,
            "circuits": self.circuits,
            "year": self.year,
            "is_comparison": self.is_comparison,
            "comparison_type": self.comparison_type,
            "intent": self.intent,
            "intent_confidence": self.intent_confidence,
            "suggested_tools": self.suggested_tools,
            "is_simple_query": self.is_simple_query,
            "corrections": self.corrections,
            "hints": self.hints,
        }


class QueryPreprocessor:
    """
    Main preprocessor combining all preprocessing steps.

    Usage:
        preprocessor = QueryPreprocessor()
        result = preprocessor.process("verstapen vs norris monaco")
        # result.normalized = "VER vs NOR"
        # result.expanded_display = "Max Verstappen vs Lando Norris at Monaco 2024"
        # result.drivers = ["VER", "NOR"]
        # result.circuits = ["monaco"]
        # result.year = 2024
        # result.is_comparison = True
    """

    def __init__(self, data_dir: str | Path | None = None):
        """
        Initialize the query preprocessor.

        Args:
            data_dir: Path to directory containing JSON data files
        """
        self.fuzzy_matcher = FuzzyMatcher(data_dir)
        self.query_expander = QueryExpander(self.fuzzy_matcher)
        self.intent_classifier = IntentClassifier()

        logger.info("QueryPreprocessor initialized")

    def process(self, query: str) -> PreprocessedQuery:
        """
        Process a query through all preprocessing steps.

        Args:
            query: Raw user query

        Returns:
            PreprocessedQuery with all extracted information
        """
        # Step 1: Extract entities and correct typos
        entities = self.fuzzy_matcher.extract_entities(query)

        # Track corrections made
        corrections = []
        for entity in entities:
            if entity.original.lower() != entity.matched.lower():
                corrections.append({
                    "original": entity.original,
                    "corrected": entity.matched,
                    "type": entity.entity_type,
                    "confidence": entity.confidence,
                })

        # Step 2: Expand query (normalize names, infer context)
        expanded = self.query_expander.expand(query)

        # Step 3: Classify intent
        classified = self.intent_classifier.classify(query)

        # Step 4: Build normalized query (with codes)
        normalized = self.query_expander.normalize_driver_mentions(query)

        # Build result
        result = PreprocessedQuery(
            original=query,
            normalized=normalized,
            expanded_display=expanded.expanded,
            drivers=expanded.drivers,
            teams=expanded.teams,
            circuits=expanded.circuits,
            year=expanded.year,
            is_comparison=expanded.is_comparison,
            comparison_type=expanded.comparison_type,
            intent=classified.intent,
            intent_confidence=classified.confidence,
            suggested_tools=classified.suggested_tools,
            is_simple_query=classified.is_simple,
            corrections=corrections,
            hints={
                **classified.hints,
                **expanded.inferred_context,
            },
        )

        logger.debug(
            f"Preprocessed query: '{query}' → intent={result.intent}, "
            f"drivers={result.drivers}, year={result.year}"
        )

        return result

    def get_driver_code(self, name: str) -> str | None:
        """Get driver code from any name/alias."""
        return self.fuzzy_matcher.get_driver_code(name)

    def get_team_id(self, name: str) -> str | None:
        """Get team ID from any name/alias."""
        return self.fuzzy_matcher.get_team_id(name)

    def get_circuit_id(self, name: str) -> str | None:
        """Get circuit ID from any name/alias."""
        return self.fuzzy_matcher.get_circuit_id(name)

    def correct_typos(self, text: str) -> tuple[str, list[dict]]:
        """
        Correct typos in text and return corrections made.

        Args:
            text: Text to correct

        Returns:
            (corrected_text, list of corrections)
        """
        entities = self.fuzzy_matcher.extract_entities(text)
        result = text
        corrections = []

        for entity in entities:
            if entity.original.lower() != entity.matched.lower():
                # Replace with matched (corrected) form
                result = result.replace(entity.original, entity.matched)
                corrections.append({
                    "original": entity.original,
                    "corrected": entity.matched,
                    "type": entity.entity_type,
                })

        return result, corrections

    def extract_comparison(self, query: str) -> tuple[bool, list[str], list[str]]:
        """
        Extract comparison entities from query.

        Args:
            query: User query

        Returns:
            (is_comparison, driver_codes, team_ids)
        """
        expanded = self.query_expander.expand(query)
        return expanded.is_comparison, expanded.drivers, expanded.teams

    def infer_year(self, query: str) -> int | None:
        """Infer year from query context."""
        expanded = self.query_expander.expand(query)
        return expanded.year


# Singleton instance for easy import
_preprocessor: QueryPreprocessor | None = None


def get_preprocessor() -> QueryPreprocessor:
    """Get or create the singleton preprocessor instance."""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = QueryPreprocessor()
    return _preprocessor


def preprocess_query(query: str) -> PreprocessedQuery:
    """
    Convenience function to preprocess a query.

    Args:
        query: Raw user query

    Returns:
        PreprocessedQuery with all extracted information
    """
    return get_preprocessor().process(query)
