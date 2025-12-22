"""
F1 RIA Query Preprocessing Module

Provides fuzzy matching, query expansion, intent classification,
and query history/suggestions for preprocessing user queries.
"""

from preprocessing.query_preprocessor import QueryPreprocessor, PreprocessedQuery
from preprocessing.fuzzy_matcher import FuzzyMatcher, MatchResult
from preprocessing.query_expander import QueryExpander, ExpandedQuery
from preprocessing.intent_classifier import IntentClassifier, ClassifiedIntent
from preprocessing.query_history import (
    QueryHistoryManager,
    QueryHistoryEntry,
    QuerySuggestion,
    get_history_manager,
)

__all__ = [
    "QueryPreprocessor",
    "PreprocessedQuery",
    "FuzzyMatcher",
    "MatchResult",
    "QueryExpander",
    "ExpandedQuery",
    "IntentClassifier",
    "ClassifiedIntent",
    "QueryHistoryManager",
    "QueryHistoryEntry",
    "QuerySuggestion",
    "get_history_manager",
]
