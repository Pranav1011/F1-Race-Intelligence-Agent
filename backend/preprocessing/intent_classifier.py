"""
Fast intent classification for F1 queries.

Pre-LLM classification to:
- Route simple queries directly to tools
- Provide hints to the LLM for faster processing
- Reduce token usage for obvious queries
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedIntent:
    """Result of intent classification."""
    intent: str
    confidence: float  # 0.0 to 1.0
    suggested_tools: list[str] = field(default_factory=list)
    is_simple: bool = False  # Can be handled without full LLM pipeline
    hints: dict = field(default_factory=dict)


# Intent patterns with associated tools
INTENT_PATTERNS = {
    "standings": {
        "patterns": [
            r"\b(?:championship|standings|points|leaderboard|table)\b",
            r"\bwho\s+(?:is\s+)?(?:leading|winning|first|top)\b",
            r"\bwdc|wcc\b",
        ],
        "tools": ["get_season_standings", "get_championship_evolution"],
        "simple": True,
    },
    "race_results": {
        "patterns": [
            r"\bwho\s+won\b",
            r"\b(?:race|gp)\s+(?:results?|winner|podium)\b",
            r"\bresults?\s+(?:of|for|from)\b",
            r"\bpodium\b",
        ],
        "tools": ["get_session_results", "search_race_reports"],
        "simple": True,
    },
    "comparison": {
        "patterns": [
            r"\bvs\.?\b|\bversus\b|\bv\.?\s+\b",
            r"\bcompare\b|\bcomparison\b",
            r"\bbetter\s+than\b|\bworse\s+than\b",
            r"\bhead\s*(?:to|2)\s*head\b",
            r"\bdifference\s+between\b",
        ],
        "tools": ["get_head_to_head", "compare_driver_pace", "get_head_to_head_career"],
        "simple": False,
    },
    "lap_times": {
        "patterns": [
            r"\blap\s*times?\b",
            r"\bfastest\s+lap\b",
            r"\bpace\b",
            r"\bsector\s+times?\b",
        ],
        "tools": ["get_lap_times", "get_sector_performance", "get_fastest_lap_stats"],
        "simple": False,
    },
    "pit_stops": {
        "patterns": [
            r"\bpit\s*stops?\b",
            r"\bpit\s+(?:time|duration|strategy)\b",
            r"\bboxed\b|\bpitting\b",
        ],
        "tools": ["get_pit_stops", "get_strategy_effectiveness"],
        "simple": True,
    },
    "tire_strategy": {
        "patterns": [
            r"\btire|tyre\b",
            r"\bstint\b",
            r"\bcompound\b",
            r"\bsoft|medium|hard|intermediate|wet\b",
            r"\bdegradation|deg\b",
        ],
        "tools": ["get_driver_stint_summary", "get_tire_degradation", "get_compound_performance"],
        "simple": False,
    },
    "qualifying": {
        "patterns": [
            r"\bquali(?:fying)?\b",
            r"\bpole\s+position\b|\bpole\b",
            r"\bgrid\s+position\b",
            r"\bq1|q2|q3\b",
        ],
        "tools": ["get_qualifying_stats", "get_qualifying_improvement", "get_pole_to_win_conversion"],
        "simple": False,
    },
    "overtaking": {
        "patterns": [
            r"\bovertake|overtaking|overtook\b",
            r"\bpass(?:es|ing|ed)?\b",
            r"\bposition\s+(?:gain|change|lost)\b",
        ],
        "tools": ["get_overtaking_analysis", "get_lap1_performance"],
        "simple": False,
    },
    "reliability": {
        "patterns": [
            r"\bdnf\b|\bretire[ds]?\b|\bretirement\b",
            r"\breliability\b",
            r"\bmechanical\s+(?:failure|issue|problem)\b",
            r"\bengine\s+(?:failure|blow)\b",
        ],
        "tools": ["get_reliability_stats", "get_finishing_streaks"],
        "simple": True,
    },
    "weather": {
        "patterns": [
            r"\brain|wet|dry\b",
            r"\bweather\b",
            r"\bintermediate\b",
            r"\bconditions\b",
        ],
        "tools": ["get_wet_weather_performance", "get_weather_conditions"],
        "simple": False,
    },
    "team_performance": {
        "patterns": [
            r"\bteam\s+(?:performance|comparison|battle)\b",
            r"\bconstructor\b",
            r"\bteammate\s+battle\b",
        ],
        "tools": ["compare_teams", "get_teammate_battle", "get_constructor_evolution"],
        "simple": False,
    },
    "career_stats": {
        "patterns": [
            r"\bcareer\b",
            r"\ball[- ]time\b",
            r"\bhistor(?:y|ic|ical)\b",
            r"\btotal\s+(?:wins|poles|podiums|points)\b",
        ],
        "tools": ["get_career_stats", "get_head_to_head_career", "get_points_trajectory"],
        "simple": False,
    },
    "track_specific": {
        "patterns": [
            r"\bat\s+(?:the\s+)?(?:\w+\s+)?(?:gp|grand\s+prix|circuit|track)\b",
            r"\bspecialist\b|\bking\s+of\b",
        ],
        "tools": ["get_track_specialist", "get_circuit_type_performance"],
        "simple": False,
    },
    "trend": {
        "patterns": [
            r"\btrend\b|\bform\b|\bmomentum\b",
            r"\blast\s+\d+\s+races?\b",
            r"\brecent(?:ly)?\b",
            r"\bseason\s+(?:so\s+far|progress)\b",
        ],
        "tools": ["get_performance_trend", "get_championship_momentum", "get_season_phase_performance"],
        "simple": False,
    },
    "general": {
        "patterns": [],
        "tools": [],
        "simple": False,
    },
}


class IntentClassifier:
    """Fast pre-LLM intent classifier."""

    def __init__(self):
        """Initialize the classifier."""
        # Pre-compile patterns for efficiency
        self.compiled_patterns = {}
        for intent, config in INTENT_PATTERNS.items():
            self.compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE)
                for p in config["patterns"]
            ]

    def classify(self, query: str) -> ClassifiedIntent:
        """
        Classify the intent of a query.

        Args:
            query: User query

        Returns:
            ClassifiedIntent with suggested tools and hints
        """
        query_lower = query.lower()

        # Score each intent
        scores: dict[str, float] = {}

        for intent, patterns in self.compiled_patterns.items():
            score = 0.0
            matches = 0

            for pattern in patterns:
                if pattern.search(query_lower):
                    matches += 1
                    score += 1.0

            if patterns:  # Avoid division by zero
                # Normalize by number of patterns, but reward multiple matches
                scores[intent] = (score / len(patterns)) * (1 + matches * 0.1)

        # Get best intent
        if scores:
            best_intent = max(scores, key=lambda k: scores[k])
            best_score = scores[best_intent]
        else:
            best_intent = "general"
            best_score = 0.0

        # If score is too low, fall back to general
        if best_score < 0.3:
            best_intent = "general"
            best_score = 0.0

        config = INTENT_PATTERNS[best_intent]

        # Build hints for the LLM
        hints = self._build_hints(query, best_intent, scores)

        return ClassifiedIntent(
            intent=best_intent,
            confidence=min(best_score, 1.0),
            suggested_tools=config["tools"],
            is_simple=config["simple"] and best_score > 0.5,
            hints=hints,
        )

    def _build_hints(
        self,
        query: str,
        primary_intent: str,
        scores: dict[str, float]
    ) -> dict:
        """Build hints to help the LLM."""
        hints = {
            "primary_intent": primary_intent,
            "secondary_intents": [
                intent for intent, score in sorted(
                    scores.items(), key=lambda x: x[1], reverse=True
                )[:3]
                if score > 0.2 and intent != primary_intent
            ],
        }

        # Add specific hints based on query content
        query_lower = query.lower()

        # Season detection
        if re.search(r"\bseason\b", query_lower):
            hints["scope"] = "full_season"
        elif re.search(r"\brace\b|\bgp\b", query_lower):
            hints["scope"] = "full_race"
        elif re.search(r"\blap\b|\bsector\b", query_lower):
            hints["scope"] = "single_lap"

        # Comparison detection
        if primary_intent == "comparison":
            if re.search(r"\bteam\b|\bconstructor\b", query_lower):
                hints["comparison_type"] = "team"
            else:
                hints["comparison_type"] = "driver"

        return hints

    def get_quick_response_tools(self, intent: str) -> list[str]:
        """Get tools for quick response (simple queries)."""
        config = INTENT_PATTERNS.get(intent, {})
        return config.get("tools", [])

    def is_simple_query(self, query: str) -> bool:
        """Check if query can be handled simply without full LLM."""
        result = self.classify(query)
        return result.is_simple
