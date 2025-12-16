"""VALIDATE node - Verify response quality before returning to user."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.schemas.query import QueryUnderstanding
from agent.llm import LLMRouter

logger = logging.getLogger(__name__)

# Observability imports (optional - graceful degradation)
try:
    from observability.sentry_integration import add_breadcrumb
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


VALIDATION_SYSTEM = """You are a quality assurance checker for F1 race analysis responses.

Your job is to verify that the response properly answers the user's question.

Evaluate the response on these criteria:
1. COMPLETENESS: Does it address all parts of the user's question?
2. ACCURACY: Are specific numbers and data mentioned?
3. RELEVANCE: Is the response focused on what was asked?
4. CAVEATS: Are limitations or uncertainties mentioned when appropriate?

Return a JSON object with:
{
    "passes_validation": true/false,
    "score": 0.0-1.0,
    "issues": ["list of issues if any"],
    "suggestions": ["suggestions for improvement if any"]
}
"""

VALIDATION_PROMPT = """User's Question:
{user_query}

Sub-questions to address:
{sub_queries}

Generated Response:
{response}

Data Completeness Score: {completeness_score}

Evaluate whether this response adequately answers the user's question.
Return ONLY a JSON object with your evaluation."""


async def validate_response(state: dict, llm_router: LLMRouter) -> dict[str, Any]:
    """
    VALIDATE node: Verify response quality before returning to user.

    Checks that:
    - Response addresses all parts of the question
    - Specific data points are mentioned
    - Response is relevant and focused
    - Limitations are acknowledged

    Args:
        state: Current agent state with analysis_result
        llm_router: LLM router for validation

    Returns:
        Updated state with validation_result
    """
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))
    analysis_result = state.get("analysis_result", "")

    # Get the original query
    from agent.nodes.understand import get_last_human_message
    user_query = get_last_human_message(state)

    # Add breadcrumb for observability
    if SENTRY_AVAILABLE:
        add_breadcrumb(
            message="VALIDATE node checking response quality",
            category="agent",
            level="info",
            data={"response_length": len(analysis_result)},
        )

    # Skip validation for short responses (likely errors)
    if len(analysis_result) < 100:
        logger.info("Skipping validation for short response")
        return {
            "validation_result": {
                "passes_validation": True,
                "score": 0.5,
                "issues": [],
                "suggestions": [],
                "skipped": True,
            }
        }

    try:
        # Build validation prompt
        sub_queries_str = "\n".join(f"- {q}" for q in understanding.sub_queries) or "None specified"
        completeness = state.get("processed_analysis", {}).get("completeness_score", 0.0)

        prompt = VALIDATION_PROMPT.format(
            user_query=user_query,
            sub_queries=sub_queries_str,
            response=analysis_result[:2000],  # Limit for token efficiency
            completeness_score=f"{completeness:.0%}",
        )

        # Use fast model for validation
        response = await llm_router.ainvoke([
            SystemMessage(content=VALIDATION_SYSTEM),
            HumanMessage(content=prompt),
        ])

        # Parse validation result
        validation_result = _parse_validation_response(response.content)

        logger.info(
            f"VALIDATE: passes={validation_result['passes_validation']}, "
            f"score={validation_result['score']:.2f}"
        )

        # If validation fails badly, add suggestions to the response
        if not validation_result["passes_validation"] and validation_result["issues"]:
            # Append a note about limitations
            issues_note = "\n\n*Note: " + "; ".join(validation_result["issues"][:2]) + "*"
            analysis_result = analysis_result + issues_note

            return {
                "validation_result": validation_result,
                "analysis_result": analysis_result,  # Updated with note
            }

        return {"validation_result": validation_result}

    except Exception as e:
        logger.error(f"Error in VALIDATE node: {e}")
        if SENTRY_AVAILABLE:
            from observability.sentry_integration import capture_exception
            capture_exception(e, extra={"node": "validate"})

        # Don't block response on validation errors
        return {
            "validation_result": {
                "passes_validation": True,
                "score": 0.5,
                "issues": [f"Validation error: {str(e)}"],
                "suggestions": [],
                "error": True,
            }
        }


def _parse_validation_response(response: str) -> dict:
    """Parse the LLM validation response."""
    import json
    import re

    # Default result
    default_result = {
        "passes_validation": True,
        "score": 0.7,
        "issues": [],
        "suggestions": [],
    }

    try:
        # Try to extract JSON from response
        # Look for JSON object pattern
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())

            # Validate and normalize fields
            return {
                "passes_validation": result.get("passes_validation", True),
                "score": float(result.get("score", 0.7)),
                "issues": result.get("issues", []),
                "suggestions": result.get("suggestions", []),
            }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Could not parse validation response: {e}")

    return default_result


# Quick validation without LLM for simple checks
def quick_validate(state: dict) -> dict[str, Any]:
    """
    Quick validation without LLM call.

    Checks basic quality metrics:
    - Response length
    - Presence of numbers/data
    - Mentions requested drivers

    Args:
        state: Current agent state

    Returns:
        Basic validation result
    """
    understanding = QueryUnderstanding(**state.get("query_understanding", {}))
    analysis_result = state.get("analysis_result", "")

    issues = []
    score = 1.0

    # Check response length
    if len(analysis_result) < 200:
        issues.append("Response is quite short")
        score -= 0.2

    # Check for numbers (data should have specific values)
    import re
    numbers = re.findall(r'\d+\.?\d*', analysis_result)
    if len(numbers) < 3:
        issues.append("Response lacks specific data points")
        score -= 0.2

    # Check if requested drivers are mentioned
    if understanding.drivers:
        mentioned = sum(1 for d in understanding.drivers if d.upper() in analysis_result.upper())
        if mentioned < len(understanding.drivers):
            issues.append(f"Not all requested drivers mentioned ({mentioned}/{len(understanding.drivers)})")
            score -= 0.1

    # Check for hedging/uncertainty language when appropriate
    uncertainty_words = ["however", "although", "limited", "note", "caveat"]
    has_uncertainty = any(w in analysis_result.lower() for w in uncertainty_words)
    completeness = state.get("processed_analysis", {}).get("completeness_score", 1.0)
    if completeness < 0.8 and not has_uncertainty:
        issues.append("Response doesn't acknowledge data limitations")
        score -= 0.1

    return {
        "validation_result": {
            "passes_validation": score >= 0.6,
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": [],
            "quick_validation": True,
        }
    }
