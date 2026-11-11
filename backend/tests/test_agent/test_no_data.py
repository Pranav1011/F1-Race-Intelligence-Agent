"""
Tests for the no-data path: when no tool returns usable data the agent must
not generate an answer, and must say which data sources failed.

The real compiled graph runs with the real PROCESS and EVALUATE nodes; the
LLM-backed nodes and the tools are replaced with scripted fakes, so these
tests need no LLM, TimescaleDB, Neo4j or Qdrant.
"""

import pytest
from ollama import ResponseError as OllamaResponseError

import agent.graph as graph_module
from agent.graph import F1Agent
from agent.llm import LLMConfig, LLMProvider, LLMRouter, LLMUnavailableError, ModelNotPulledError
from agent.nodes.evaluate import (
    MAX_NO_DATA_RETRIES,
    is_connection_failure,
    is_failed_result,
    is_usable_result,
)
from agent.schemas.query import AnalysisScope, AnalysisType, QueryUnderstanding

REFUSED = "[Errno 61] Connect call failed ('127.0.0.1', 5432)"

PLAN = {
    "tool_calls": [
        {"id": "laps_VER", "tool_name": "get_lap_times", "parameters": {}},
        {"id": "stints", "tool_name": "get_stint_analysis", "parameters": {}},
        {"id": "reports", "tool_name": "search_race_reports", "parameters": {}},
    ],
    "parallel_groups": [["laps_VER", "stints", "reports"]],
}

ALL_FAILED = {
    "laps_VER": [{"error": REFUSED, "code": "DATABASE_QUERY_ERROR"}],
    "stints": {"error": REFUSED, "rows": []},
    "reports": [{"error": "Connection refused"}],
}

NO_LAPS = [{
    "error": "No lap time data found for the specified criteria",
    "code": "NO_TELEMETRY_DATA",
}]
NO_PITS = [{
    "error": "No pit stop data found for the specified criteria",
    "code": "NO_PIT_STOP_DATA",
}]

VER_LAPS = [
    {"lap_number": n, "lap_time_seconds": 82.0 + n / 10, "compound": "HARD"}
    for n in range(1, 61)
]


class FakeNodes:
    """Scripted stand-ins for the LLM nodes and the tool executor."""

    def __init__(self, raw_data: dict | list[dict], understand_error: str | None = None):
        # One raw_data per attempt; the last one repeats
        self.attempts = list(raw_data) if isinstance(raw_data, list) else [raw_data]
        self.understand_error = understand_error
        self.plan_calls = 0
        self.generate_calls = 0
        self.validate_calls = 0

    async def understand(self, state, llm_router):
        understanding = QueryUnderstanding(
            query_type=AnalysisType.STRATEGY,
            scope=AnalysisScope.FULL_RACE,
            drivers=["VER", "NOR"],
            seasons=[2024],
            races=["Monza"],
        )
        update = {"query_understanding": understanding.model_dump()}
        if self.understand_error:
            update["error"] = self.understand_error
        return update

    async def plan(self, state, llm_router):
        self.plan_calls += 1
        return {"data_plan": PLAN}

    async def execute(self, state, **tools):
        attempt = self.attempts.pop(0) if len(self.attempts) > 1 else self.attempts[0]
        return {"raw_data": dict(attempt)}

    async def enrich(self, state):
        return {"enriched_context": {}}

    async def generate(self, state, llm_router):
        self.generate_calls += 1
        return {"analysis_result": "Verstappen ran one stop.", "response_type": "TEXT"}

    async def validate(self, state, llm_router):
        self.validate_calls += 1
        return {"validation_result": {"score": 0.9, "issues": []}}


@pytest.fixture
def make_agent(monkeypatch):
    def build(nodes: FakeNodes) -> F1Agent:
        monkeypatch.setattr(graph_module, "understand_query", nodes.understand)
        monkeypatch.setattr(graph_module, "plan_data_retrieval", nodes.plan)
        monkeypatch.setattr(graph_module, "execute_tools", nodes.execute)
        monkeypatch.setattr(graph_module, "enrich_context", nodes.enrich)
        monkeypatch.setattr(graph_module, "generate_response", nodes.generate)
        monkeypatch.setattr(graph_module, "validate_response", nodes.validate)
        return F1Agent(enable_memory=False)

    return build


async def test_zero_data_skips_generate_and_names_failed_sources(make_agent):
    nodes = FakeNodes(ALL_FAILED)
    agent = make_agent(nodes)

    response = await agent.chat(
        "Compare Verstappen and Norris tyre strategy at Monza 2024", session_id="s1"
    )

    assert nodes.generate_calls == 0
    assert nodes.validate_calls == 0
    # Every source refused the connection: no re-plan, the notice comes at once
    assert nodes.plan_calls == 1
    assert response["message"].startswith("I couldn't reach the race data")
    assert "the race database (TimescaleDB)" in response["message"]
    assert "race report search (Qdrant)" in response["message"]
    assert response["error"] == response["message"]
    assert response["confidence"] == 0.0
    assert response["visualization"] is None
    assert agent.get_session_analysis("s1")["evaluation"]["is_sufficient"] is False


async def test_zero_data_reports_an_earlier_model_error_first(make_agent):
    missing = str(ModelNotPulledError("deepseek-r1:8b"))
    nodes = FakeNodes(ALL_FAILED, understand_error=missing)
    agent = make_agent(nodes)

    response = await agent.chat("Who won Monza 2024?", session_id="s1")

    assert nodes.generate_calls == 0
    assert response["error"].startswith(
        "Agent error: model deepseek-r1:8b is not pulled; "
        "run `ollama pull deepseek-r1:8b` or set OLLAMA_MODEL."
    )
    assert "I couldn't reach the race data" in response["error"]


async def test_zero_data_blames_the_unreachable_llm_not_the_data(make_agent):
    nodes = FakeNodes(ALL_FAILED, understand_error=str(LLMUnavailableError()))
    agent = make_agent(nodes)

    response = await agent.chat("Who won Monza 2024?", session_id="s1")

    assert nodes.generate_calls == 0
    assert response["error"].startswith("I couldn't reach a language model")
    assert "OLLAMA_BASE_URL" in response["error"]
    assert "All LLM providers failed" not in response["error"]
    assert "The data lookups also failed:" in response["error"]


@pytest.mark.parametrize(
    "message",
    [
        "All LLM providers failed",
        "Agent error: All LLM providers failed",
        "plan failed: All LLM providers failed (after 3 attempts)",
    ],
)
def test_llm_unavailable_matches_wrapped_messages(message):
    assert LLMUnavailableError.matches(message)


@pytest.mark.parametrize("message", [None, "", "2 validation errors for QueryUnderstanding"])
def test_llm_unavailable_ignores_other_errors(message):
    assert not LLMUnavailableError.matches(message)


async def test_zero_data_blames_the_llm_for_a_wrapped_error_too(make_agent):
    nodes = FakeNodes(ALL_FAILED, understand_error=f"Agent error: {LLMUnavailableError()}")
    agent = make_agent(nodes)

    response = await agent.chat("Who won Monza 2024?", session_id="s1")

    assert response["error"].startswith("I couldn't reach a language model")


async def test_zero_data_leaves_out_unrelated_earlier_errors(make_agent):
    nodes = FakeNodes(ALL_FAILED, understand_error="2 validation errors for QueryUnderstanding")
    agent = make_agent(nodes)

    response = await agent.chat("Who won Monza 2024?", session_id="s1")

    assert response["error"].startswith("I couldn't reach the race data")
    assert "QueryUnderstanding" not in response["error"]


async def test_empty_results_say_no_data_was_found(make_agent):
    nodes = FakeNodes({"laps_VER": [], "stints": {"rows": []}, "reports": []})
    agent = make_agent(nodes)

    response = await agent.chat("Monza 2031 strategy?", session_id="s1")

    assert nodes.generate_calls == 0
    assert response["message"].startswith(
        "I couldn't find data for that in the race database (TimescaleDB) "
        "or race report search (Qdrant)"
    )
    assert "Check that these services" not in response["message"]


async def test_not_found_errors_are_not_reported_as_dead_services(make_agent):
    nodes = FakeNodes({"laps_VER": NO_LAPS, "stints": NO_PITS})
    agent = make_agent(nodes)

    response = await agent.chat("Pit stops at Monza 2024?", session_id="s1")

    assert nodes.generate_calls == 0
    assert response["message"].startswith(
        "I couldn't find data for that in the race database (TimescaleDB)"
    )
    assert "Failed" not in response["message"]
    assert "Check that these services" not in response["message"]


async def test_only_the_unreachable_source_is_named_as_failed(make_agent):
    nodes = FakeNodes({"laps_VER": NO_LAPS, "reports": [{"error": "Connection refused"}]})
    agent = make_agent(nodes)

    response = await agent.chat("Monza 2024 strategy?", session_id="s1")

    assert "Failed: race report search (Qdrant)." in response["message"]
    assert "TimescaleDB" not in response["message"]


CONNECTION_REFUSED = {
    "laps_VER": [{"error": "Database connection not initialized", "code": "DATABASE_CONNECTION_ERROR"}],
    "stints": {"error": "[Errno 61] Connection refused"},
    "reports": [{"error": "Connection refused"}],
}


async def test_unreachable_services_stop_without_any_re_plan(make_agent):
    nodes = FakeNodes(CONNECTION_REFUSED)
    agent = make_agent(nodes)

    response = await agent.chat("Compare Verstappen and Norris at Monza 2024", session_id="s1")

    assert nodes.plan_calls == 1
    assert nodes.generate_calls == 0
    assert response["message"].startswith("I couldn't reach the race data")


async def test_nothing_found_re_plans_at_most_once(make_agent):
    nodes = FakeNodes({"laps_VER": NO_LAPS, "stints": {"rows": []}, "reports": []})
    agent = make_agent(nodes)

    await agent.chat("Monza 2031 strategy?", session_id="s1")

    assert nodes.plan_calls == MAX_NO_DATA_RETRIES + 1 == 2
    assert nodes.generate_calls == 0


async def test_a_mix_of_dead_and_empty_sources_still_gets_one_re_plan(make_agent):
    nodes = FakeNodes({"laps_VER": NO_LAPS, "reports": [{"error": "Connection refused"}]})
    agent = make_agent(nodes)

    await agent.chat("Monza 2024 strategy?", session_id="s1")

    assert nodes.plan_calls == 2


@pytest.mark.parametrize(
    ("result", "unreachable"),
    [
        ([{"error": "Database connection not initialized", "code": "DATABASE_CONNECTION_ERROR"}], True),
        ({"error": "[Errno 61] Connect call failed ('127.0.0.1', 5432)", "code": "DATABASE_QUERY_ERROR"}, True),
        ([{"error": "[Errno 8] nodename nor servname provided, or not known"}], True),
        ([{"error": "syntax error at or near SELECT", "code": "DATABASE_QUERY_ERROR"}], False),
        (NO_LAPS, False),
        ([], False),
        ({"rows": [1]}, False),
    ],
)
def test_is_connection_failure(result, unreachable):
    assert is_connection_failure(result) is unreachable


async def test_failed_retry_keeps_the_earlier_usable_data(make_agent):
    standings = {"results": [{"position": 1, "driver": "NOR"}]}
    nodes = FakeNodes([standings, ALL_FAILED])
    agent = make_agent(nodes)

    response = await agent.chat("Monza 2024 strategy?", session_id="s1")

    # The retry hit dead services, so it stops there and answers from attempt 1
    assert nodes.plan_calls == 2
    assert nodes.generate_calls == 1
    assert response["message"] == "Verstappen ran one stop."
    session = agent._sessions["s1"]
    assert session["data_outcome"] == "ok"
    assert session["raw_data"] == standings


async def test_partial_data_takes_the_normal_path(make_agent):
    nodes = FakeNodes({**ALL_FAILED, "laps_VER": VER_LAPS})
    agent = make_agent(nodes)

    response = await agent.chat("Verstappen strategy at Monza 2024", session_id="s1")

    assert nodes.generate_calls == 1
    assert nodes.validate_calls == 1
    assert response["message"] == "Verstappen ran one stop."
    assert response["error"] is None
    assert agent._sessions["s1"]["data_outcome"] == "ok"


@pytest.mark.parametrize(
    ("result", "usable"),
    [
        (None, False),
        ([], False),
        ({}, False),
        ({"error": REFUSED}, False),
        ({"error": REFUSED, "rows": []}, False),
        ([{"error": REFUSED}], False),
        ([{"error": REFUSED}, {"lap_number": 1}], True),
        ([{"lap_number": 1}], True),
        ({"rows": []}, False),
        ({"rows": [{"lap_number": 1}]}, True),
        ("race report text", True),
    ],
)
def test_is_usable_result(result, usable):
    assert is_usable_result(result) is usable


@pytest.mark.parametrize(
    ("result", "failed"),
    [
        ([{"error": REFUSED, "code": "DATABASE_QUERY_ERROR"}], True),
        ({"error": "Database connection not initialized", "code": "DATABASE_CONNECTION_ERROR"}, True),
        ({"error": "RAG service not initialized"}, True),
        ([{"error": "Connection refused"}], True),
        (NO_LAPS, False),
        (NO_PITS, False),
        ({"error": "Session '2031_1_R' not found", "code": "SESSION_NOT_FOUND"}, False),
        ([{"error": "No race data found for 2031"}], False),
        ({"error": "Circuit Atlantis not found"}, False),
        ([*NO_LAPS, {"error": REFUSED, "code": "DATABASE_TIMEOUT"}], True),
        ([], False),
        ([{"lap_number": 1}], False),
    ],
)
def test_is_failed_result(result, failed):
    assert is_failed_result(result) is failed


class Ollama404:
    def __init__(self, body: str):
        self.body = body

    async def ainvoke(self, messages, **kwargs):
        raise OllamaResponseError(self.body, 404)


async def test_missing_ollama_model_says_how_to_fix_it(caplog):
    router = LLMRouter(LLMConfig(ollama_model="llama-missing:1b"))
    router._providers[LLMProvider.OLLAMA] = Ollama404('{"error":"model \'llama-missing:1b\' not found"}')

    with pytest.raises(ModelNotPulledError) as raised:
        await router.ainvoke([])

    expected = (
        "model llama-missing:1b is not pulled; run `ollama pull llama-missing:1b` "
        "or set OLLAMA_MODEL"
    )
    assert str(raised.value) == expected
    assert expected in caplog.text


async def test_wrong_ollama_url_is_not_reported_as_a_missing_model():
    router = LLMRouter(LLMConfig(ollama_model="llama3.1:8b"))
    router._providers[LLMProvider.OLLAMA] = Ollama404("404 page not found")

    with pytest.raises(RuntimeError) as raised:
        await router.ainvoke([])

    assert not isinstance(raised.value, ModelNotPulledError)
    assert str(raised.value) == "All LLM providers failed"


def test_ollama_model_comes_from_the_environment(monkeypatch):
    from api.routers import chat

    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setattr(chat, "_agent", None)
    monkeypatch.setattr(graph_module, "_agent", None)

    agent = chat.get_chat_agent()

    assert agent.config.ollama_model == "llama3.1:8b"
