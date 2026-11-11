"""
Years the user didn't state are read against the data (2018-2024), shown to the
user, and carried across follow-up questions in the same chat.
"""

import pytest

from preprocessing import query_expander
from preprocessing.query_expander import LATEST_DATA_SEASON
from preprocessing.query_preprocessor import QueryPreprocessor


@pytest.fixture
def preprocessor(monkeypatch) -> QueryPreprocessor:
    # Pin the calendar year past the data so relative years must be capped
    monkeypatch.setattr(query_expander, "CURRENT_YEAR", 2026)
    return QueryPreprocessor()


def test_explicit_year_is_used_and_not_annotated(preprocessor):
    result = preprocessor.process("Who won Monza 2021?")
    assert result.year == 2021
    assert result.year_note is None
    assert "year_inferred" not in result.hints


def test_missing_year_defaults_to_latest_season_and_says_so(preprocessor):
    result = preprocessor.process("Who won Monza?")
    assert result.year == LATEST_DATA_SEASON == 2024
    assert result.hints["year_inferred"] is True
    assert result.year_note == "assumed 2024 (latest season with data)"


@pytest.mark.parametrize(
    ("query", "year"),
    [
        ("Who won the most races this season?", 2024),
        ("How did Ferrari do this year?", 2024),
        ("Ferrari's pace last season", 2023),
        ("Who won last year?", 2023),
        ("Ferrari's pace 2 years ago", 2022),
    ],
)
def test_relative_years_count_back_from_the_latest_season_with_data(preprocessor, query, year):
    result = preprocessor.process(query)
    assert result.year == year
    assert result.hints["year_source"] == "relative"
    assert result.year_note == f"read as {year} (data runs to the 2024 season)"


def test_follow_up_keeps_the_year_of_the_earlier_question(preprocessor):
    preprocessor.process("Compare Verstappen and Norris at Monaco 2021", session_id="s1")

    follow_up = preprocessor.process("what about Hamilton?", session_id="s1")

    assert follow_up.drivers == ["HAM"]
    assert follow_up.year == 2021
    assert follow_up.year_note == "kept 2021 from your earlier question"


def test_follow_up_in_another_chat_does_not_inherit_the_year(preprocessor):
    preprocessor.process("Compare Verstappen and Norris at Monaco 2021", session_id="s1")

    other = preprocessor.process("what about Hamilton?", session_id="s2")

    assert other.year == 2024
    assert other.year_note == "assumed 2024 (latest season with data)"


def test_a_new_explicit_year_replaces_the_carried_one(preprocessor):
    preprocessor.process("Monaco 2021 winner?", session_id="s1")
    preprocessor.process("And Monaco 2019?", session_id="s1")

    assert preprocessor.process("what about Hamilton?", session_id="s1").year == 2019


def test_year_note_reaches_the_interpreted_event_payload(preprocessor):
    assert preprocessor.process("Who won Monza?").to_dict()["year_note"] == (
        "assumed 2024 (latest season with data)"
    )
