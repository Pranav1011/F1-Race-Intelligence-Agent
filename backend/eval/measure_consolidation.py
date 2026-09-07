"""Before/after tool-schema token cost, measured the same way for both sets.

Serializes each tool to the exact OpenAI function schema the model receives
(langchain `convert_to_openai_tool`) and counts tokens with tiktoken. Compares the
original 79 TimescaleDB tools against the 8 consolidated dispatchers.

    .venv/bin/python eval/measure_consolidation.py
"""

from __future__ import annotations

import json
from pathlib import Path

import tiktoken
from langchain_core.utils.function_calling import convert_to_openai_tool

from agent.tools.consolidated_tools import CONSOLIDATED_TIMESCALE_TOOLS
from agent.tools.timescale_tools import TIMESCALE_TOOLS

_ENC = tiktoken.encoding_for_model("gpt-4o")


def _tokens(tools) -> int:
    schemas = [convert_to_openai_tool(t) for t in tools]
    return len(_ENC.encode(json.dumps(schemas)))


def main() -> None:
    before_tools, after_tools = len(TIMESCALE_TOOLS), len(CONSOLIDATED_TIMESCALE_TOOLS)
    before_tok, after_tok = _tokens(TIMESCALE_TOOLS), _tokens(CONSOLIDATED_TIMESCALE_TOOLS)
    result = {
        "scope": "TimescaleDB tool surface (the 79 that dominate the tax)",
        "method": "langchain convert_to_openai_tool + tiktoken(gpt-4o)",
        "before": {"tools": before_tools, "schema_tokens": before_tok},
        "after": {"tools": after_tools, "schema_tokens": after_tok},
        "tools_reduction_pct": round(100 * (before_tools - after_tools) / before_tools, 1),
        "token_reduction_pct": round(100 * (before_tok - after_tok) / before_tok, 1),
    }
    out = Path(__file__).resolve().parent / "results" / "consolidation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
