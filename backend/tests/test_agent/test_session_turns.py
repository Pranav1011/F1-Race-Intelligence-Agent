"""
Tests for F1Agent session handling: per-turn state reset, per-session
serialization, and the bounded session cache.

The compiled LangGraph is replaced with a scripted fake so these tests need
no LLM, Redis, TimescaleDB, Neo4j or Qdrant.
"""

import asyncio
from typing import get_type_hints

import pytest
from langchain_core.messages import HumanMessage

from agent.graph import F1Agent
from agent.state import (
    PER_SESSION_FIELDS,
    PER_TURN_FIELDS,
    EnhancedAgentState,
    create_initial_state,
    reset_turn_state,
)


class ScriptedGraph:
    """Stand-in for the compiled graph that replays scripted node updates."""

    def __init__(self, turns: list[list[dict]] | None = None, delay: float = 0.0):
        self.turns = list(turns or [])
        self.delay = delay
        self.seen_states: list[dict] = []
        self.active = 0
        self.max_active = 0
        self.active_by_session: dict[str, int] = {}
        self.max_same_session = 0

    async def astream(self, state, config=None, stream_mode=None):
        self.seen_states.append(dict(state))
        session_id = state["session_id"]
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.active_by_session[session_id] = self.active_by_session.get(session_id, 0) + 1
        self.max_same_session = max(self.max_same_session, self.active_by_session[session_id])
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            updates = self.turns.pop(0) if self.turns else [{"generate": {"analysis_result": "ok"}}]
            for update in updates:
                if isinstance(update, Exception):
                    raise update
                if callable(update):
                    update()
                    continue
                yield update
        finally:
            self.active -= 1
            self.active_by_session[session_id] -= 1


def make_agent(graph: ScriptedGraph, max_sessions: int = 500) -> F1Agent:
    agent = F1Agent(enable_memory=False, max_sessions=max_sessions)
    agent.graph = graph
    return agent


LOOPING_TURN = [
    {"execute": {"raw_data": {"t1": {"error": "timeout"}}}},
    {"evaluate": {"iteration_count": 1, "evaluation_feedback": "missing laps"}},
    {"evaluate": {"iteration_count": 2, "evaluation_feedback": "still missing"}},
    {"generate": {"analysis_result": "partial", "error": "generate failed"}},
    {"validate": {"validation_result": {"score": 0.2, "issues": ["thin"]}}},
]


def test_every_state_field_is_classified():
    fields = set(get_type_hints(EnhancedAgentState, include_extras=True))
    assert set(PER_TURN_FIELDS) | set(PER_SESSION_FIELDS) == fields
    assert not set(PER_TURN_FIELDS) & set(PER_SESSION_FIELDS)


def test_reset_turn_state_keeps_session_fields():
    state = create_initial_state("s1", "u1")
    state["messages"].append(HumanMessage(content="hi"))
    state["iteration_count"] = 2
    state["error"] = "boom"
    state["raw_data"] = {"x": 1}

    reset_turn_state(state)

    assert state["iteration_count"] == 0
    assert state["error"] is None
    assert state["raw_data"] == {}
    assert [m.content for m in state["messages"]] == ["hi"]
    assert state["user_id"] == "u1"


async def test_memory_context_is_refreshed_every_turn():
    graph = ScriptedGraph()
    agent = make_agent(graph)
    contexts = iter(["likes Verstappen", "asked about Ferrari"])
    session_contexts = iter([{"drivers": ["VER"]}, {"drivers": ["LEC"]}])

    class FakeUserMemory:
        async def get_user_context(self, user_id, message):
            return next(contexts)

        async def add_memory(self, **kwargs):
            pass

    class FakeSessionState:
        async def get_context(self, session_id):
            return next(session_contexts)

        async def add_message(self, *args):
            pass

        async def update_context(self, *args):
            pass

    agent.enable_memory = True
    agent._user_memory = FakeUserMemory()
    agent._session_state = FakeSessionState()

    await agent.chat("q1", session_id="s1", user_id="u1")
    await agent.chat("q2", session_id="s1", user_id="u1")

    assert graph.seen_states[1]["user_context"] == "asked about Ferrari"
    assert graph.seen_states[1]["session_context"] == {"drivers": ["LEC"]}


async def test_second_turn_starts_with_fresh_per_turn_state():
    graph = ScriptedGraph(turns=[LOOPING_TURN, [{"generate": {"analysis_result": "fine"}}]])
    agent = make_agent(graph)

    first = await agent.chat("compare VER and NOR", session_id="s1")
    second = await agent.chat("and at Monza?", session_id="s1")

    assert first["iterations"] == 2
    assert first["error"] == "generate failed"

    turn2_input = graph.seen_states[1]
    assert turn2_input["iteration_count"] == 0
    assert turn2_input["evaluation_feedback"] == ""
    assert turn2_input["raw_data"] == {}
    assert turn2_input["error"] is None
    assert turn2_input["validation_result"] is None
    assert [m.content for m in turn2_input["messages"]] == [
        "compare VER and NOR",
        "and at Monza?",
    ]

    assert second["iterations"] == 0
    assert second["error"] is None
    assert second["validation_issues"] == []


async def test_preprocessed_hints_do_not_leak_into_next_turn():
    graph = ScriptedGraph()
    agent = make_agent(graph)

    await agent.chat("q1", session_id="s1", preprocessed={"intent": "comparison"})
    await agent.chat("q2", session_id="s1")

    assert graph.seen_states[1]["preprocessed_query"] == {}


async def test_concurrent_messages_on_one_session_are_serialized():
    graph = ScriptedGraph(delay=0.02)
    agent = make_agent(graph)

    await asyncio.gather(
        agent.chat("a", session_id="same"),
        agent.chat("b", session_id="same"),
    )

    assert graph.max_active == 1


async def test_different_sessions_run_concurrently():
    graph = ScriptedGraph(delay=0.02)
    agent = make_agent(graph)

    await asyncio.gather(
        agent.chat("a", session_id="s1"),
        agent.chat("b", session_id="s2"),
    )

    assert graph.max_active == 2


async def test_session_cache_evicts_least_recently_used():
    agent = make_agent(ScriptedGraph(), max_sessions=2)

    await agent.chat("a", session_id="s1")
    await agent.chat("b", session_id="s2")
    await agent.chat("c", session_id="s1")
    await agent.chat("d", session_id="s3")

    assert agent.get_session_history("s2") == []
    assert [m["content"] for m in agent.get_session_history("s1")] == ["a", "c"]
    assert len(agent._sessions) == 2
    assert set(agent._session_locks) <= set(agent._sessions)


async def test_session_waiting_for_its_lock_is_not_evicted():
    graph = ScriptedGraph(delay=0.02)
    agent = make_agent(graph, max_sessions=1)

    def create_other_session_after_release():
        # call_soon from the first turn's last step runs after that turn
        # releases the lock but before the queued second turn resumes: the
        # hand-off window in which "busy" looks unlocked.
        asyncio.get_running_loop().call_soon(agent.get_or_create_session, "other")

    graph.turns = [[{"generate": {"analysis_result": "ok"}}, create_other_session_after_release]]

    await asyncio.gather(
        agent.chat("a", session_id="busy"),
        agent.chat("b", session_id="busy"),
    )

    assert graph.max_same_session == 1
    assert [m["content"] for m in agent.get_session_history("busy")] == ["a", "b"]
    assert "busy" in agent._session_locks


async def test_session_cleared_mid_turn_is_not_restored():
    graph = ScriptedGraph(delay=0.02)
    agent = make_agent(graph)

    turn = asyncio.create_task(agent.chat("a", session_id="s1"))
    await asyncio.sleep(0.01)
    agent.clear_session("s1")
    await turn

    assert "s1" not in agent._sessions


async def test_graph_failure_names_the_failing_step():
    graph = ScriptedGraph(
        turns=[
            [
                {"understand": {"query_understanding": {}}},
                RuntimeError("connection refused"),
            ]
        ]
    )
    agent = make_agent(graph)

    response = await agent.chat("q", session_id="s1")

    assert response["query_type"] == "error"
    assert "understand" in response["error"]
    assert "connection refused" in response["error"]


@pytest.mark.parametrize("bad_size", [0, -1])
def test_max_sessions_must_be_positive(bad_size):
    with pytest.raises(ValueError, match="max_sessions"):
        F1Agent(enable_memory=False, max_sessions=bad_size)
