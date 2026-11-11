"""
With every data service down, the agent answers at once without any LLM call;
with at least one up, it runs as usual.
"""

import asyncio
import socket

import pytest

import agent.graph as graph_module
from agent import preflight
from agent.graph import F1Agent
from agent.preflight import DataService, DataServicePreflight

# Bound at import, before conftest's autouse fixture swaps in a stub
from agent.preflight import probe_service as real_probe


def set_reachable(monkeypatch, up: set[str]):
    calls = []

    async def probe(service, timeout=None):
        calls.append(service.label)
        return service.label in up

    monkeypatch.setattr(preflight, "probe_service", probe)
    return calls


class CountingNodes:
    def __init__(self):
        self.understand_calls = 0
        self.plan_calls = 0

    async def understand(self, state, llm_router):
        self.understand_calls += 1
        return {"query_understanding": {}}

    async def plan(self, state, llm_router):
        self.plan_calls += 1
        return {"data_plan": {"tool_calls": [], "parallel_groups": []}}


@pytest.fixture
def make_agent(monkeypatch):
    def build() -> tuple[F1Agent, CountingNodes]:
        nodes = CountingNodes()
        monkeypatch.setattr(graph_module, "understand_query", nodes.understand)
        monkeypatch.setattr(graph_module, "plan_data_retrieval", nodes.plan)
        return F1Agent(enable_memory=False), nodes

    return build


async def test_all_services_down_answers_without_any_llm_call(monkeypatch, make_agent):
    set_reachable(monkeypatch, up=set())
    agent, nodes = make_agent()

    response = await agent.chat("Compare Verstappen and Norris at Monza 2024", session_id="s1")

    assert nodes.understand_calls == 0
    assert nodes.plan_calls == 0
    assert response["message"] == (
        "I couldn't reach the race data, so I can't answer with data right now. "
        "Failed: the race database (TimescaleDB), the knowledge graph (Neo4j), "
        "race report search (Qdrant). Check that these services are running, then ask again."
    )
    assert response["error"] == response["message"]
    assert response["confidence"] == 0.0
    assert response["visualization"] is None


async def test_one_service_up_runs_the_agent(monkeypatch, make_agent):
    set_reachable(monkeypatch, up={"the race database (TimescaleDB)"})
    agent, nodes = make_agent()

    await agent.chat("Compare Verstappen and Norris at Monza 2024", session_id="s1")

    assert nodes.understand_calls == 1
    assert nodes.plan_calls >= 1


async def test_result_is_cached_between_turns(monkeypatch):
    calls = set_reachable(monkeypatch, up=set())
    check = DataServicePreflight(ttl_s=30)

    first = await check.all_unreachable()
    second = await check.all_unreachable()

    assert len(first) == 3 and first == second
    assert len(calls) == 3  # one probe per service, not per turn


async def test_probes_run_concurrently_with_a_short_timeout(monkeypatch):
    async def slow(service, timeout=None):
        await asyncio.sleep(0.2)
        return False

    monkeypatch.setattr(preflight, "probe_service", slow)
    loop = asyncio.get_running_loop()
    start = loop.time()

    await DataServicePreflight().unreachable_services()

    assert loop.time() - start < 0.5


async def test_real_probe_sees_an_open_and_a_closed_port():
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    open_port = server.sockets[0].getsockname()[1]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
    try:
        assert await real_probe(DataService("open", "127.0.0.1", open_port))
        assert not await real_probe(DataService("closed", "127.0.0.1", closed_port), timeout=0.5)
    finally:
        server.close()
        await server.wait_closed()
