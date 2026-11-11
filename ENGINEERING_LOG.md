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
context-budget problem, not a feature.
The fix cut the surface 90% and schema cost 85%, with a coverage test proving
nothing was lost.

## 2026-11-11 — Product-readiness pass (entity matching, defaults, UI)
**Goal:** a fresh clone should run, the example prompts should be understood correctly,
and every README claim should match what runs.

**Changes and why:**
- **Entity matching precision.** The built-in prompts produced "Understood as: Zhou
  Guanyu, Liam Lawson, Oscar Piastri" ("Who", "lap", "pit", "at" and "of" matched names),
  and those entities reached the agent. Added a stopword list, a 4-character minimum for
  typo matching, and a 0.85 similarity floor (1 - edits / length). Only real typo fixes
  are shown as corrections. A question with no year now means 2024, the last ingested
  season. 20 tests pin it, including all four example prompts.
- **Entity data committed.** `backend/data/{drivers,teams,circuits}.json` were ignored
  with the rest of `data/`, so a fresh clone loaded 0 drivers.
- **One default model.** `make setup` pulled llama3.2 while the code defaulted to
  deepseek-r1:8b. Everything now says llama3.1:8b (tested model); outside Docker the
  Ollama URL defaults to localhost.
- **Dead LLM named as the cause.** With every provider down, the no-data reply blamed
  Qdrant; it now says the language model was unreachable and how to fix it.
- **UI:** generic decoration removed from the empty state, AA text contrast, reduced
  motion, mobile drawer closed by default, a reason shown when sending is paused.

- **Years read against the data.** "this season" / "last season" count back from 2024
  instead of the calendar year (2026, no data); a follow-up keeps the chat's previous year;
  any year the user didn't type is shown on the interpretation card.
- **Fail fast on dead services.** With the databases down, evaluate re-planned twice more,
  each a 35-50 s llama3.1:8b call, so the honest notice took about 5 minutes. Now an
  iteration whose failures are all unreachable services (including services that never
  connected at startup) goes straight to the no-data reply; other no-data cases re-plan once.
- **Disconnects cancel the agent** and log one line instead of an ASGI traceback;
  SessionState reads REDIS_URL.
- **Missing dependency.** `agent/llm.py` imports `langchain_ollama`, which neither
  `pyproject.toml` nor the Docker image installed, so a fresh install failed at import.

**Not done:** binding the 8 consolidated tools at runtime (the agent still binds 92);
the README now says so.

**Result:** backend 110 → 174 passing (+ the known DB-dependent `test_health_check`).
