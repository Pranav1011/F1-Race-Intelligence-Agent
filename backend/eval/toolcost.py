"""Tool-schema token cost (WO F1 2f, DB-free measurement).

Every request to the model carries the JSON schema of every bound tool. With 92
narrow tools that is a large, fixed context tax paid on *every* turn. This script
measures that tax directly from the tool definitions — no DB, no model, no venv —
so the 92 -> ~20 consolidation can be reported as a real before/after number.

Method: parse each `@tool`-decorated function (name, docstring, typed args) with
the AST, build the OpenAI function-schema each tool serializes to, and count
tokens with tiktoken (gpt-4o encoding). The SAME method is used before and after,
so the delta is faithful even though it approximates langchain's exact bytes.

    python3 backend/eval/toolcost.py
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import tiktoken

BACKEND = Path(__file__).resolve().parents[1]
TOOL_FILES = {
    "timescale": BACKEND / "agent/tools/timescale_tools.py",
    "neo4j": BACKEND / "agent/tools/neo4j_tools.py",
    "vector": BACKEND / "agent/tools/vector_tools.py",
}

_TYPE_MAP = {"int": "integer", "float": "number", "bool": "boolean", "str": "string"}


def _is_tool(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        if isinstance(d, ast.Name) and d.id == "tool":
            return True
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "tool":
            return True
        if isinstance(d, ast.Attribute) and d.attr == "tool":
            return True
    return False


def _arg_type(annotation: ast.expr | None) -> str:
    if annotation is None:
        return "string"
    try:
        txt = ast.unparse(annotation)
    except Exception:
        return "string"
    for py, js in _TYPE_MAP.items():
        if py in txt:
            return js
    return "string"


def _tool_schema(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    doc = ast.get_docstring(fn) or ""
    props: dict[str, dict] = {}
    required: list[str] = []
    for a in fn.args.args:
        if a.arg in ("self", "cls"):
            continue
        props[a.arg] = {"type": _arg_type(a.annotation), "description": ""}
    n_defaults = len(fn.args.defaults)
    names = [a.arg for a in fn.args.args if a.arg not in ("self", "cls")]
    required = names[: len(names) - n_defaults] if n_defaults else names
    return {
        "type": "function",
        "function": {
            "name": fn.name,
            "description": doc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


def collect(path: Path) -> list[dict]:
    tree = ast.parse(path.read_text())
    return [
        _tool_schema(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_tool(node)
    ]


def main() -> None:
    enc = tiktoken.encoding_for_model("gpt-4o")
    per_cat: dict[str, dict] = {}
    all_schemas: list[dict] = []
    for cat, path in TOOL_FILES.items():
        if not path.exists():
            continue
        schemas = collect(path)
        all_schemas += schemas
        toks = len(enc.encode(json.dumps(schemas)))
        per_cat[cat] = {"tools": len(schemas), "tokens": toks}
    total_tools = sum(c["tools"] for c in per_cat.values())
    total_tokens = len(enc.encode(json.dumps(all_schemas)))
    result = {
        "measured": "tool-schema token cost (before consolidation)",
        "per_category": per_cat,
        "total_tools": total_tools,
        "total_schema_tokens": total_tokens,
        "tokens_per_tool_avg": round(total_tokens / total_tools, 1) if total_tools else 0,
    }
    out = BACKEND / "eval" / "results" / "toolcost_before.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nwrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
