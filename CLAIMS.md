# CLAIMS — F1 Racing Intelligence Agent
Updated 2026-11-11. Every quantitative/technical claim maps to a committed artifact + reproduce command.

| Claim | Status | Evidence artifact | Reproduce | Verified |
|---|---|---|---|---|
| Consolidated the agent's TimescaleDB tool surface **79 → 8** via a dispatch layer (originals unchanged) | VERIFIED | `backend/agent/tools/consolidated_tools.py`, `backend/tests/test_tools/test_consolidated.py` | `pytest tests/test_tools/test_consolidated.py` | 2026-09-07 |
| Cut tool-schema context cost **85% (13,487 → 2,014 tokens)** per request | VERIFIED | `backend/eval/measure_consolidation.py`, `backend/eval/results/consolidation.json` | `python eval/measure_consolidation.py` | 2026-09-07 |
| **All 79** underlying tools covered exactly once — no functionality dropped | VERIFIED | `test_every_timescale_tool_is_covered_exactly_once` | `pytest tests/test_tools/test_consolidated.py -k covered` | 2026-09-07 |
| Dispatch filters args to each underlying tool's signature (no signature changes) | VERIFIED | `test_dispatch_routes_and_filters_args`, `test_extra_params_reach_the_underlying_tool` | `pytest tests/test_tools/test_consolidated.py` | 2026-09-07 |
| Long tail reachable via a **guarded text-to-SQL** tool (read-only, validated) | VERIFIED (reuses existing) | `backend/agent/validation.py`, `backend/tests/test_tools/test_sql_validation.py` | `pytest tests/test_tools/test_sql_validation.py` | 2026-09-07 |
| Existing suite unbroken by the change | VERIFIED | pytest: 57 → **63 pass**; the 1 failure (`test_health`) is pre-existing and needs the DBs running | `pytest` | 2026-09-07 |
| Backend suite: **174 pass**, 1 known failure (`test_health_check`, needs the Docker DBs) | VERIFIED | `backend/tests/` | `cd backend && pytest -q` | 2026-11-11 |
| The runtime still binds the **full 92 tools** (79 TimescaleDB + 8 Neo4j + 5 vector); the 8 consolidated tools are measured, not bound | VERIFIED | `backend/agent/graph.py` (`_execute_node` passes `TIMESCALE_TOOLS`); backend log "Tool registry built with 92 tools" | run the API and send one message | 2026-11-11 |
| Ordinary words in the example prompts never resolve to drivers/teams ("Who", "lap", "at", "of", "pit"); "Verstappen", "Norris", "Monza" do | VERIFIED | `backend/tests/test_preprocessing/test_fuzzy_matcher.py` | `pytest tests/test_preprocessing` | 2026-11-11 |

**Scope:** consolidation applied to the 79 TimescaleDB tools (88% of the original token tax). Neo4j (8) + vector (5) not yet consolidated; the 8 dispatchers are not yet bound at runtime; switching the binding touches the execute wrapper and the planner's tool names and needs the DBs stood up to validate end-to-end. Measurement is DB-free (schema token cost).
