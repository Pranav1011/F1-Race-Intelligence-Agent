"""PLAN node - Create data retrieval execution plan."""

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.schemas.query import QueryUnderstanding, DataPlan, ToolCall
from agent.prompts.plan import PLAN_SYSTEM, PLAN_PROMPT, TOOL_DESCRIPTIONS
from agent.llm import LLMRouter

logger = logging.getLogger(__name__)


async def plan_data_retrieval(state: dict, llm_router: LLMRouter) -> dict[str, Any]:
    """
    PLAN node: Create an execution plan for data retrieval.

    The LLM decides which tools to call based on the query understanding,
    organizing them into parallel groups for efficient execution.

    Args:
        state: Current agent state with query_understanding
        llm_router: LLM router for inference

    Returns:
        Updated state with data_plan
    """
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))

    # Include feedback from EVALUATE if we're looping
    previous_feedback = ""
    if state.get("evaluation_feedback"):
        previous_feedback = f"\n\nPREVIOUS ATTEMPT FEEDBACK:\n{state['evaluation_feedback']}\n\nPlease adjust the plan to fetch the missing data."

    prompt = PLAN_PROMPT.format(
        understanding=json.dumps(understanding.model_dump(), indent=2),
        available_tools=TOOL_DESCRIPTIONS,
        previous_feedback=previous_feedback,
    )

    try:
        llm = llm_router.get_llm()
        response = await llm.ainvoke([
            SystemMessage(content=PLAN_SYSTEM),
            HumanMessage(content=prompt),
        ])

        # Parse JSON response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())

        # Build ToolCall objects
        tool_calls = []
        for tc in parsed.get("tool_calls", []):
            tool_calls.append(ToolCall(
                id=tc.get("id", f"tool_{len(tool_calls)}"),
                tool_name=tc.get("tool_name", ""),
                parameters=tc.get("parameters", {}),
                depends_on=tc.get("depends_on", []),
                purpose=tc.get("purpose", ""),
            ))

        plan = DataPlan(
            tool_calls=tool_calls,
            parallel_groups=parsed.get("parallel_groups", []),
            expected_data_points=parsed.get("expected_data_points", 0),
            reasoning=parsed.get("reasoning", ""),
        )

        logger.info(
            f"Plan created: {len(plan.tool_calls)} tools, "
            f"{len(plan.parallel_groups)} parallel groups"
        )

        return {"data_plan": plan.model_dump()}

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse plan response: {e}")
        # Fallback to basic plan based on understanding
        return {"data_plan": _create_fallback_plan(understanding).model_dump()}
    except Exception as e:
        logger.error(f"Error in plan_data_retrieval: {e}")
        return {
            "data_plan": _create_fallback_plan(understanding).model_dump(),
            "error": str(e),
        }


def _create_fallback_plan(understanding: QueryUnderstanding) -> DataPlan:
    """Create a basic fallback plan when LLM planning fails."""
    tool_calls = []

    # Always try to get session results
    if understanding.seasons:
        year = understanding.seasons[0]
        tool_calls.append(ToolCall(
            id="results",
            tool_name="get_session_results",
            parameters={"year": year},
            purpose="Get race results",
        ))

    # Get lap times for mentioned drivers
    for i, driver in enumerate(understanding.drivers[:2]):  # Limit to 2 drivers
        tool_calls.append(ToolCall(
            id=f"laps_{driver}",
            tool_name="get_lap_times",
            parameters={
                "driver_id": driver,
                "year": understanding.seasons[0] if understanding.seasons else 2024,
            },
            purpose=f"Get lap times for {driver}",
        ))

    # Build parallel groups (all lap time fetches can run in parallel)
    parallel_groups = []
    lap_ids = [tc.id for tc in tool_calls if tc.id.startswith("laps_")]
    if lap_ids:
        parallel_groups.append(lap_ids)

    return DataPlan(
        tool_calls=tool_calls,
        parallel_groups=parallel_groups,
        expected_data_points=100,
        reasoning="Fallback plan: fetch results and lap times for mentioned drivers",
    )
