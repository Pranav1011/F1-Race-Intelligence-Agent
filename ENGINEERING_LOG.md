# Engineering Log — F1 Racing Intelligence Agent

## 2026-09-07 — Tool consolidation 79 → 8 (context-budget fix)
**Goal:** the agent bound 92 narrow tools (79 of them TimescaleDB `get_*` functions),
injecting ~14.6k tokens of schema into every request and making the model choose
among 79 near-identical options. Cut the surface without losing capability.

**Decisions:**
- **Facade, not rewrite.** Kept the 79 working query functions as-is; added a
  `consolidated_tools.py` that exposes 5 dispatchers + 3 standalone tools and routes
  by an enum (the exact underlying tool name) via `.ainvoke`. Reuses the working SQL,
  so correctness is unchanged and — crucially — I don't need the databases running
  to prove the change is safe.
- **Coverage as a test.** `test_every_timescale_tool_is_covered_exactly_once` asserts
  the union of dispatcher enums == the 79 tool names, with no duplicates. This is what
  guarantees "no functionality dropped" mechanically, not by inspection.
- **Arg filtering.** `_dispatch` inspects each target tool's `.args` and passes only
  accepted keys (common args + an `extra` dict), so heterogeneous signatures work
  through one interface without editing any underlying tool.
- **Measured before/after the same way** (langchain `convert_to_openai_tool` + tiktoken
  on both sets), not AST-vs-langchain, so the delta is honest.

**Incidental repo bugs fixed to get a green baseline (both broke a fresh install):**
- `pyproject.toml` had no `[tool.hatch.build.targets.wheel]` → `pip install -e .` / CI
  couldn't build. Added the package list.
- `agent/llm.py` imported `ChatOllama` from `langchain_community.chat_models`; current
  langchain moved it to `langchain_ollama`. Updated the import + added the dep.

**Result:** 79 → 8 tools (−90%); tool-schema tokens 13,487 → 2,014 (−85%). Existing
suite 57 → 63 pass, no new failures (the lone `test_health` failure needs the DBs and
predates this work).

**Why it matters:** tool definitions deserve the same care as prompts — 79 tools was a
context-budget problem, not a feature. "Cut the tool surface 90% and context cost 85%,
with a coverage test proving nothing was lost" is a concrete, defensible line.
