"""
Entity extraction must not turn ordinary words into F1 names.

Regression for the "Understood as: Zhou Guanyu, ... Oscar Piastri" card: "Who",
"lap", "at", "of" and "pit" were matched to drivers and teams in the built-in
prompts, and the bogus entities reached the agent.
"""

import pytest

from preprocessing.fuzzy_matcher import FuzzyMatcher
from preprocessing.query_preprocessor import QueryPreprocessor

# The four prompts on the empty-state screen (frontend/components/chat/SuggestedPrompts.tsx)
BUILT_IN_PROMPTS = [
    "Who won the 2024 Bahrain GP?",
    "Compare Verstappen and Norris's lap times at Monaco 2024",
    "Why did Ferrari's strategy fail at Silverstone?",
    "Show me the fastest pit stops of 2024",
]


@pytest.fixture(scope="module")
def matcher() -> FuzzyMatcher:
    return FuzzyMatcher()


@pytest.fixture(scope="module")
def preprocessor() -> QueryPreprocessor:
    return QueryPreprocessor()


def test_committed_entity_data_loads(matcher):
    assert len(matcher.drivers) >= 20
    assert len(matcher.teams) >= 10
    assert len(matcher.circuits) >= 20


@pytest.mark.parametrize("word", ["Who", "lap", "at", "of", "pit", "was", "am", "Show"])
def test_common_words_are_not_entities(matcher, word):
    assert matcher.extract_entities(word) == []


def test_built_in_prompts_extract_only_real_entities(matcher):
    found = {
        (e.canonical, e.entity_type)
        for prompt in BUILT_IN_PROMPTS
        for e in matcher.extract_entities(prompt)
    }
    assert found == {
        ("bahrain", "circuit"),
        ("VER", "driver"),
        ("NOR", "driver"),
        ("monaco", "circuit"),
        ("ferrari", "team"),
        ("silverstone", "circuit"),
    }


@pytest.mark.parametrize("prompt", BUILT_IN_PROMPTS)
def test_built_in_prompts_show_no_auto_corrections(preprocessor, prompt):
    assert preprocessor.process(prompt).corrections == []


@pytest.mark.parametrize(
    ("text", "canonical", "entity_type"),
    [
        ("Verstappen", "VER", "driver"),
        ("Norris", "NOR", "driver"),
        ("Monza", "monza", "circuit"),
    ],
)
def test_real_names_still_match(matcher, text, canonical, entity_type):
    [entity] = matcher.extract_entities(text)
    assert (entity.canonical, entity.entity_type) == (canonical, entity_type)
    assert entity.confidence == 1.0


def test_monza_prompt_names_only_the_drivers_and_circuit(preprocessor):
    result = preprocessor.process("Compare Verstappen and Norris tyre strategy at Monza 2024")
    assert result.drivers == ["VER", "NOR"]
    assert result.teams == []
    assert result.circuits == ["monza"]


def test_real_typos_are_still_corrected(preprocessor):
    result = preprocessor.process("what was verstapen pace at silverston")
    assert result.drivers == ["VER"]
    assert result.circuits == ["silverstone"]
    corrected = {c["original"]: c["corrected"] for c in result.corrections}
    assert set(corrected) == {"verstapen", "silverston"}
    assert all(c["confidence"] >= 0.85 for c in result.corrections)


def test_no_year_defaults_to_latest_season_with_data(preprocessor):
    result = preprocessor.process("Why did Ferrari's strategy fail at Silverstone?")
    assert result.year == 2024
