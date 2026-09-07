"""WO F1 2f: the consolidated dispatcher layer must cover every underlying tool
and route calls correctly, without altering the originals."""

from __future__ import annotations

import pytest

from agent.tools import ALL_TOOLS
from agent.tools import consolidated_tools as c
from agent.tools.timescale_tools import TIMESCALE_TOOLS


def test_every_timescale_tool_is_covered_exactly_once():
    names = {t.name for t in TIMESCALE_TOOLS}
    mapped: list[str] = []
    for members in c._GROUP_MEMBERS.values():
        mapped += list(members)
    assert len(mapped) == len(set(mapped)), "a tool is mapped into two groups"
    missing = names - set(mapped)
    extra = set(mapped) - names
    assert not missing, f"unmapped underlying tools: {sorted(missing)}"
    assert not extra, f"mapped names that don't exist: {sorted(extra)}"


def test_exposed_surface_shrinks_79_to_8():
    assert len(c.CONSOLIDATED_TIMESCALE_TOOLS) == 8
    assert len(TIMESCALE_TOOLS) == 79  # originals untouched


def test_originals_untouched():
    # The 92-tool ALL_TOOLS is unchanged; consolidation is additive.
    assert len(ALL_TOOLS) == 92


class _FakeTool:
    """Stand-in for a StructuredTool: exposes `.args` (accepted params) and records
    what `.ainvoke` received. Used because StructuredTool is a frozen pydantic model."""

    def __init__(self, accepted: set[str]):
        self.args = {k: {} for k in accepted}
        self.received: dict | None = None

    async def ainvoke(self, payload: dict):
        self.received = payload
        return "rows"


@pytest.mark.asyncio
async def test_dispatch_routes_and_filters_args(monkeypatch):
    # race_analysis(metric=get_lap_times) must call the underlying tool with only
    # the args it accepts (session_id, driver_id here), dropping None / non-accepted.
    fake = _FakeTool({"session_id", "driver_id", "year", "event_name", "limit"})
    monkeypatch.setitem(c._TS, "get_lap_times", fake)

    out = await c.race_analysis.ainvoke(
        {"metric": "get_lap_times", "session_id": "S1", "driver_id": "VER", "year": None}
    )

    assert out == "rows"
    assert fake.received == {"session_id": "S1", "driver_id": "VER"}


@pytest.mark.asyncio
async def test_extra_params_reach_the_underlying_tool(monkeypatch):
    # tool-specific args (compound) travel via `extra` and are kept if accepted.
    fake = _FakeTool({"session_id", "driver_id", "compound"})
    monkeypatch.setitem(c._TS, "get_tire_degradation", fake)

    await c.race_analysis.ainvoke(
        {"metric": "get_tire_degradation", "session_id": "S1", "extra": {"compound": "SOFT"}}
    )
    assert fake.received == {"session_id": "S1", "compound": "SOFT"}


@pytest.mark.asyncio
async def test_unknown_metric_is_handled():
    out = await c._dispatch("get_nonexistent")
    assert isinstance(out, dict) and "error" in out
