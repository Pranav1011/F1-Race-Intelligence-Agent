# CLAIMS — F1 Racing Intelligence Agent
Updated 2026-09-07. Every quantitative/technical claim maps to a committed artifact + reproduce command.

| Claim | Status | Evidence artifact | Reproduce | Verified |
|---|---|---|---|---|
| Consolidated the agent's TimescaleDB tool surface **79 → 8** via a dispatch layer (originals unchanged) | VERIFIED | `backend/agent/tools/consolidated_tools.py`, `backend/tests/test_tools/test_consolidated.py` | `pytest tests/test_tools/test_consolidated.py` | 2026-09-07 |
| Cut tool-schema context cost **85% (13,487 → 2,014 tokens)** per request | VERIFIED | `backend/eval/measure_consolidation.py`, `backend/eval/results/consolidation.json` | `python eval/measure_consolidation.py` | 2026-09-07 |
| **All 79** underlying tools covered exactly once — no functionality dropped | VERIFIED | `test_every_timescale_tool_is_covered_exactly_once` | `pytest tests/test_tools/test_consolidated.py -k covered` | 2026-09-07 |
| Dispatch filters args to each underlying tool's signature (no signature changes) | VERIFIED | `test_dispatch_routes_and_filters_args`, `test_extra_params_reach_the_underlying_tool` | `pytest tests/test_tools/test_consolidated.py` | 2026-09-07 |
| Long tail reachable via a **guarded text-to-SQL** tool (read-only, validated) | VERIFIED (reuses existing) | `backend/agent/validation.py`, `backend/tests/test_tools/test_sql_validation.py` | `pytest tests/test_tools/test_sql_validation.py` | 2026-09-07 |
| Existing suite unbroken by the change | VERIFIED | pytest: 57 → **63 pass**; the 1 failure (`test_health`) is pre-existing and needs the DBs running | `pytest` | 2026-09-07 |

**Scope:** consolidation applied to the 79 TimescaleDB tools (88% of the original token tax). Neo4j (8) + vector (5) not yet consolidated; wiring the 8 dispatchers into the agent's runtime binding is a 1-line follow-up (needs the DBs stood up to validate end-to-end). Measurement is DB-free (schema token cost).
