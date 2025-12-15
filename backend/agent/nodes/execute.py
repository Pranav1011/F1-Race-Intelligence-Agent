"""EXECUTE node - Run tool calls with parallel execution."""

import asyncio
import logging
from typing import Any

from agent.schemas.query import DataPlan, ToolCall

logger = logging.getLogger(__name__)


async def execute_tools(
    state: dict,
    timescale_tools: Any,
    neo4j_tools: Any,
    vector_tools: Any,
) -> dict[str, Any]:
    """
    EXECUTE node: Run tool calls with parallel execution where possible.

    Tools in the same parallel group are executed concurrently using
    asyncio.gather() for latency optimization.

    Args:
        state: Current agent state with data_plan
        timescale_tools: TimescaleDB tool functions
        neo4j_tools: Neo4j tool functions
        vector_tools: Vector DB tool functions

    Returns:
        Updated state with raw_data
    """
    plan = DataPlan(**state.get("data_plan", {}))

    # Build tool registry
    tool_registry = _build_tool_registry(timescale_tools, neo4j_tools, vector_tools)

    # Create mapping from tool_id to ToolCall
    tool_map = {tc.id: tc for tc in plan.tool_calls}

    results = {}
    executed_ids = set()

    # Execute each parallel group
    for group_idx, group in enumerate(plan.parallel_groups):
        logger.info(f"Executing parallel group {group_idx + 1}: {group}")

        # Filter to tools we haven't executed yet
        group_tools = [
            tool_map[tool_id]
            for tool_id in group
            if tool_id in tool_map and tool_id not in executed_ids
        ]

        if not group_tools:
            continue

        # Execute all tools in this group concurrently
        tasks = []
        task_ids = []
        for tool_call in group_tools:
            task = _execute_single_tool(tool_call, tool_registry)
            tasks.append(task)
            task_ids.append(tool_call.id)

        # Wait for all tasks in group to complete
        group_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Store results
        for tool_id, result in zip(task_ids, group_results):
            if isinstance(result, Exception):
                logger.error(f"Tool {tool_id} failed: {result}")
                results[tool_id] = {"error": str(result)}
            else:
                results[tool_id] = result
            executed_ids.add(tool_id)

    # Execute any remaining tools not in parallel groups
    for tool_call in plan.tool_calls:
        if tool_call.id not in executed_ids:
            logger.info(f"Executing sequential tool: {tool_call.id}")
            try:
                result = await _execute_single_tool(tool_call, tool_registry)
                results[tool_call.id] = result
            except Exception as e:
                logger.error(f"Tool {tool_call.id} failed: {e}")
                results[tool_call.id] = {"error": str(e)}

    logger.info(f"Execution complete: {len(results)} tools executed")

    return {"raw_data": results}


async def _execute_single_tool(tool_call: ToolCall, tool_registry: dict) -> Any:
    """Execute a single tool call."""
    tool_name = tool_call.tool_name
    params = tool_call.parameters

    if tool_name not in tool_registry:
        return {"error": f"Unknown tool: {tool_name}"}

    tool_func = tool_registry[tool_name]

    try:
        # Check if tool is async
        if asyncio.iscoroutinefunction(tool_func):
            result = await tool_func(**params)
        else:
            result = tool_func(**params)
        return result
    except Exception as e:
        logger.error(f"Error executing {tool_name}: {e}")
        raise


def _build_tool_registry(
    timescale_tools: Any,
    neo4j_tools: Any,
    vector_tools: Any,
) -> dict:
    """Build a registry mapping tool names to callable functions.

    Handles both:
    - List of LangChain StructuredTool objects
    - Objects with tool methods as attributes
    """
    registry = {}

    def add_tools_from_list(tools_list: list):
        """Add tools from a list of LangChain tools."""
        for tool in tools_list:
            # LangChain tools have .name and .coroutine or ._run
            if hasattr(tool, "name"):
                if hasattr(tool, "coroutine") and tool.coroutine:
                    registry[tool.name] = tool.coroutine
                elif hasattr(tool, "_run"):
                    registry[tool.name] = tool._run
                elif hasattr(tool, "invoke"):
                    # For newer LangChain tools
                    registry[tool.name] = tool.ainvoke

    def add_tools_from_object(tools_obj: Any, tool_names: list[str]):
        """Add tools from an object with tool methods."""
        for name in tool_names:
            if hasattr(tools_obj, name):
                registry[name] = getattr(tools_obj, name)

    # TimescaleDB tools
    if timescale_tools:
        if isinstance(timescale_tools, list):
            add_tools_from_list(timescale_tools)
        else:
            add_tools_from_object(timescale_tools, [
                "get_lap_times",
                "get_session_results",
                "get_driver_stint_summary",
                "compare_driver_pace",
                "get_tire_degradation",
                "get_available_sessions",
            ])

    # Neo4j tools
    if neo4j_tools:
        if isinstance(neo4j_tools, list):
            add_tools_from_list(neo4j_tools)
        else:
            add_tools_from_object(neo4j_tools, [
                "get_driver_info",
                "get_race_info",
                "get_driver_stints_graph",
                "find_similar_situations",
            ])

    # Vector tools
    if vector_tools:
        if isinstance(vector_tools, list):
            add_tools_from_list(vector_tools)
        else:
            add_tools_from_object(vector_tools, [
                "search_race_reports",
                "search_regulations",
                "search_reddit_discussions",
                "search_past_analyses",
                "store_analysis",
            ])

    logger.info(f"Tool registry built with {len(registry)} tools: {list(registry.keys())}")
    return registry
