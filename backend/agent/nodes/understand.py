"""UNDERSTAND node - Parse query and extract intent."""

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.schemas.query import QueryUnderstanding, AnalysisType, AnalysisScope
from agent.prompts.understand import UNDERSTAND_SYSTEM, UNDERSTAND_PROMPT
from agent.llm import LLMRouter

logger = logging.getLogger(__name__)

# Observability imports (optional - graceful degradation)
try:
    from observability.sentry_integration import add_breadcrumb, capture_exception, span
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


def get_last_human_message(state: dict) -> str:
    """Extract the last human message from state."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
        if isinstance(msg, dict) and msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def format_conversation_history(state: dict, limit: int = 5) -> str:
    """Format recent conversation history."""
    messages = state.get("messages", [])[-limit:]
    history = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history.append(f"User: {msg.content}")
        elif hasattr(msg, "content"):
            role = "Assistant" if not isinstance(msg, HumanMessage) else "User"
            history.append(f"{role}: {msg.content[:200]}...")
    return "\n".join(history) if history else "No previous conversation"


async def understand_query(state: dict, llm_router: LLMRouter) -> dict[str, Any]:
    """
    UNDERSTAND node: Parse the user query and extract structured intent.

    Uses HyDE (Hypothetical Document Embeddings) to generate what an
    ideal answer would look like, guiding data retrieval.

    Now enhanced with preprocessing hints for faster, more accurate understanding.

    Args:
        state: Current agent state
        llm_router: LLM router for inference

    Returns:
        Updated state with query_understanding
    """
    user_message = get_last_human_message(state)
    conversation_history = format_conversation_history(state)
    user_context = state.get("user_context", "")
    preprocessed = state.get("preprocessed_query", {})

    # Add breadcrumb for observability
    if SENTRY_AVAILABLE:
        add_breadcrumb(
            message=f"UNDERSTAND node processing query: {user_message[:100]}...",
            category="agent",
            level="info",
            data={
                "user_context_length": len(user_context),
                "has_preprocessing": bool(preprocessed),
            },
        )

    # Build preprocessing hints for the LLM
    preprocessing_hints = ""
    if preprocessed:
        hints_parts = []
        if preprocessed.get("intent"):
            hints_parts.append(f"Detected intent: {preprocessed['intent']} (confidence: {preprocessed.get('intent_confidence', 0):.2f})")
        if preprocessed.get("drivers"):
            hints_parts.append(f"Detected drivers: {', '.join(preprocessed['drivers'])}")
        if preprocessed.get("teams"):
            hints_parts.append(f"Detected teams: {', '.join(preprocessed['teams'])}")
        if preprocessed.get("circuits"):
            hints_parts.append(f"Detected circuits: {', '.join(preprocessed['circuits'])}")
        if preprocessed.get("year"):
            hints_parts.append(f"Year: {preprocessed['year']}")
        if preprocessed.get("is_comparison"):
            hints_parts.append(f"This is a comparison query ({preprocessed.get('comparison_type', 'driver')} comparison)")
        if preprocessed.get("corrections"):
            corrections = preprocessed["corrections"]
            corrections_str = ", ".join([f"'{c['original']}' → '{c['corrected']}'" for c in corrections])
            hints_parts.append(f"Typo corrections applied: {corrections_str}")
        if preprocessed.get("suggested_tools"):
            hints_parts.append(f"Suggested tools: {', '.join(preprocessed['suggested_tools'][:3])}")

        if hints_parts:
            preprocessing_hints = "\n\nPREPROCESSING HINTS (use these to speed up understanding):\n" + "\n".join(f"- {h}" for h in hints_parts)

    prompt = UNDERSTAND_PROMPT.format(
        user_message=user_message,
        conversation_history=conversation_history,
        user_context=user_context,
    ) + preprocessing_hints

    try:
        # Use router's ainvoke for automatic fallback on rate limits
        response = await llm_router.ainvoke([
            SystemMessage(content=UNDERSTAND_SYSTEM),
            HumanMessage(content=prompt),
        ])

        # Parse JSON response
        content = response.content
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())

        # Validate and create QueryUnderstanding
        understanding = QueryUnderstanding(
            query_type=AnalysisType(parsed.get("query_type", "general")),
            scope=AnalysisScope(parsed.get("scope", "full_race")),
            drivers=parsed.get("drivers", []),
            teams=parsed.get("teams", []),
            races=parsed.get("races", []),
            seasons=parsed.get("seasons", []),
            metrics=parsed.get("metrics", []),
            sub_queries=parsed.get("sub_queries", []),
            hypothetical_answer=parsed.get("hypothetical_answer", ""),
            confidence=float(parsed.get("confidence", 0.5)),
        )

        logger.info(
            f"Query understood: type={understanding.query_type}, "
            f"scope={understanding.scope}, drivers={understanding.drivers}"
        )

        return {
            "query_understanding": understanding.model_dump(),
            "query_type": understanding.query_type,
            "confidence": understanding.confidence,
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse understanding response: {e}")
        if SENTRY_AVAILABLE:
            add_breadcrumb(
                message="JSON parse failed in UNDERSTAND node",
                category="agent",
                level="warning",
                data={"error": str(e)},
            )
        # Fallback to basic understanding
        return {
            "query_understanding": QueryUnderstanding(
                query_type=AnalysisType.GENERAL,
                scope=AnalysisScope.FULL_RACE,
                confidence=0.3,
            ).model_dump(),
            "query_type": AnalysisType.GENERAL,
            "confidence": 0.3,
        }
    except Exception as e:
        logger.error(f"Error in understand_query: {e}")
        if SENTRY_AVAILABLE:
            capture_exception(
                e,
                extra={"node": "understand", "query_preview": user_message[:100]},
                tags={"agent_node": "understand"},
            )
        return {
            "query_understanding": QueryUnderstanding(
                query_type=AnalysisType.GENERAL,
                scope=AnalysisScope.FULL_RACE,
                confidence=0.1,
            ).model_dump(),
            "query_type": AnalysisType.GENERAL,
            "confidence": 0.1,
            "error": str(e),
        }
