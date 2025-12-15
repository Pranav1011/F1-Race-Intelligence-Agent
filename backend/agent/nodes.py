"""
Agent Nodes

LangGraph nodes for query classification, retrieval, and response generation.
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.state import AgentStateDict, QueryType, ResponseType
from agent.llm import LLMRouter

logger = logging.getLogger(__name__)

# System prompts
CLASSIFIER_PROMPT = """You are an F1 race analysis query classifier. Analyze the user's query and determine:

1. Query Type (choose one):
   - historical_analysis: Questions about past races, performance, results
   - what_if_simulation: Hypothetical scenarios ("what if X had done Y")
   - live_insights: Questions about recent/current races or events
   - comparison: Comparing drivers, teams, or performance
   - general_knowledge: F1 rules, regulations, history facts

2. Extract Context:
   - drivers: List of driver names/abbreviations mentioned
   - teams: List of teams mentioned
   - races: List of race names/circuits mentioned
   - seasons: List of years mentioned
   - metrics: What data is being asked about (lap_time, tire_deg, pit_stops, etc.)

Respond in JSON format only:
{
  "query_type": "string",
  "confidence": 0.0-1.0,
  "context": {
    "drivers": [],
    "teams": [],
    "races": [],
    "seasons": [],
    "metrics": []
  }
}"""

ANALYST_PROMPT = """You are an expert F1 race engineer and analyst. Your role is to provide insightful,
data-driven analysis of F1 races, strategies, and performance.

Guidelines:
1. Be precise with data - cite specific lap times, positions, and statistics
2. Explain technical concepts clearly for fans of all levels
3. Consider multiple factors: tires, weather, track position, strategy
4. Acknowledge uncertainty in predictions and simulations
5. Reference historical patterns when relevant

When analyzing:
- Lap times: Consider tire compound, fuel load, traffic
- Strategy: Discuss undercuts, overcuts, safety car impact
- Driver performance: Compare to teammates and expectations
- Team tactics: Analyze pit stop timing and execution

Format responses with clear structure using markdown when helpful."""


async def classify_query(state: AgentStateDict, llm_router: LLMRouter) -> AgentStateDict:
    """
    Classify the user's query to determine how to handle it.

    Args:
        state: Current agent state
        llm_router: LLM router for inference

    Returns:
        Updated state with query classification
    """
    logger.info("Classifying query")

    # Get the last user message
    messages = state["messages"]
    user_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break

    if not user_message:
        state["error"] = "No user message found"
        return state

    try:
        # Use LLM to classify
        classification_messages = [
            SystemMessage(content=CLASSIFIER_PROMPT),
            HumanMessage(content=f"Classify this query: {user_message}"),
        ]

        response = await llm_router.ainvoke(classification_messages)

        # Parse JSON response
        try:
            # Extract JSON from response
            response_text = response.content
            # Handle potential markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            classification = json.loads(response_text.strip())

            state["query_type"] = QueryType(classification.get("query_type", "unknown"))
            state["confidence"] = classification.get("confidence", 0.5)
            state["query_context"] = classification.get("context", {})

            logger.info(f"Query classified as {state['query_type']} with confidence {state['confidence']}")

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse classification: {e}")
            state["query_type"] = QueryType.UNKNOWN
            state["confidence"] = 0.0
            state["query_context"] = {}

    except Exception as e:
        logger.error(f"Classification error: {e}")
        state["error"] = str(e)

    return state


async def retrieve_data(
    state: AgentStateDict,
    timescale_tools: list,
    neo4j_tools: list,
    vector_tools: list,
) -> AgentStateDict:
    """
    Retrieve relevant data based on query classification.

    Args:
        state: Current agent state
        timescale_tools: TimescaleDB tools
        neo4j_tools: Neo4j tools
        vector_tools: Vector search tools

    Returns:
        Updated state with retrieved data
    """
    logger.info(f"Retrieving data for {state['query_type']}")

    query_type = state["query_type"]
    context = state["query_context"]
    retrieved = {"timescale": [], "neo4j": [], "vector": []}

    try:
        # Get data based on query type and context
        drivers = context.get("drivers", [])
        seasons = context.get("seasons", [])
        races = context.get("races", [])

        # Historical analysis or comparison - need lap data and results
        if query_type in [QueryType.HISTORICAL_ANALYSIS, QueryType.COMPARISON]:
            # Get lap times for mentioned drivers
            for driver in drivers[:2]:  # Limit to 2 drivers
                for tool in timescale_tools:
                    if tool.name == "get_lap_times":
                        year = seasons[0] if seasons else None
                        result = await tool.ainvoke({
                            "driver_id": driver,
                            "year": year,
                            "limit": 50,
                        })
                        if result and not isinstance(result, dict) or not result.get("error"):
                            retrieved["timescale"].append({
                                "tool": "get_lap_times",
                                "driver": driver,
                                "data": result[:20] if isinstance(result, list) else result,
                            })

            # Get driver info from knowledge graph
            for driver in drivers[:2]:
                for tool in neo4j_tools:
                    if tool.name == "get_driver_info":
                        result = await tool.ainvoke({"driver_id": driver})
                        if result and not result.get("error"):
                            retrieved["neo4j"].append({
                                "tool": "get_driver_info",
                                "data": result,
                            })

        # What-if simulation - need historical context
        elif query_type == QueryType.WHAT_IF_SIMULATION:
            # Search for similar past situations
            for tool in vector_tools:
                if tool.name == "search_past_analyses":
                    user_msg = state["messages"][-1].content if state["messages"] else ""
                    result = await tool.ainvoke({
                        "query": user_msg,
                        "limit": 3,
                    })
                    if result:
                        retrieved["vector"].append({
                            "tool": "search_past_analyses",
                            "data": result,
                        })

        # General knowledge - search regulations
        elif query_type == QueryType.GENERAL_KNOWLEDGE:
            for tool in vector_tools:
                if tool.name == "search_regulations":
                    user_msg = state["messages"][-1].content if state["messages"] else ""
                    result = await tool.ainvoke({
                        "query": user_msg,
                        "limit": 5,
                    })
                    if result:
                        retrieved["vector"].append({
                            "tool": "search_regulations",
                            "data": result,
                        })

        state["retrieved_data"] = retrieved
        logger.info(f"Retrieved data from {len(retrieved['timescale'])} timescale, "
                    f"{len(retrieved['neo4j'])} neo4j, {len(retrieved['vector'])} vector sources")

    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        state["error"] = str(e)

    return state


async def generate_response(state: AgentStateDict, llm_router: LLMRouter) -> AgentStateDict:
    """
    Generate the final response based on retrieved data.

    Args:
        state: Current agent state
        llm_router: LLM router for inference

    Returns:
        Updated state with generated response
    """
    logger.info("Generating response")

    try:
        # Build context from retrieved data
        context_parts = []
        retrieved = state.get("retrieved_data", {})

        if retrieved.get("timescale"):
            context_parts.append("## Telemetry & Timing Data")
            for item in retrieved["timescale"]:
                context_parts.append(f"From {item['tool']}:")
                # Summarize data
                data = item.get("data", [])
                if isinstance(data, list) and data:
                    context_parts.append(f"  {len(data)} records retrieved")
                    # Show sample
                    if len(data) > 0:
                        context_parts.append(f"  Sample: {json.dumps(data[0], default=str)[:200]}...")

        if retrieved.get("neo4j"):
            context_parts.append("\n## Knowledge Graph Data")
            for item in retrieved["neo4j"]:
                context_parts.append(f"From {item['tool']}:")
                context_parts.append(f"  {json.dumps(item.get('data', {}), default=str)[:300]}")

        if retrieved.get("vector"):
            context_parts.append("\n## Reference Documents")
            for item in retrieved["vector"]:
                data = item.get("data", [])
                if isinstance(data, list):
                    for doc in data[:2]:
                        if isinstance(doc, dict):
                            context_parts.append(f"  {doc.get('content', '')[:200]}...")

        context = "\n".join(context_parts) if context_parts else "No specific data retrieved."

        # Get user message
        user_message = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break

        # Generate response
        generation_messages = [
            SystemMessage(content=ANALYST_PROMPT),
            SystemMessage(content=f"Available context data:\n{context}"),
            HumanMessage(content=user_message),
        ]

        response = await llm_router.ainvoke(generation_messages)
        state["analysis_result"] = response.content

        # Determine response type
        if any(kw in user_message.lower() for kw in ["chart", "graph", "visualize", "plot"]):
            state["response_type"] = ResponseType.CHART
        elif any(kw in user_message.lower() for kw in ["table", "list", "compare"]):
            state["response_type"] = ResponseType.TABLE
        else:
            state["response_type"] = ResponseType.TEXT

        logger.info(f"Generated {state['response_type']} response")

    except Exception as e:
        logger.error(f"Generation error: {e}")
        state["error"] = str(e)
        state["analysis_result"] = f"I apologize, but I encountered an error generating the response: {str(e)}"

    return state


def should_retrieve(state: AgentStateDict) -> str:
    """
    Determine if retrieval is needed based on query type.

    Returns:
        "retrieve" if retrieval needed, "generate" to skip to generation
    """
    query_type = state.get("query_type", QueryType.UNKNOWN)
    confidence = state.get("confidence", 0.0)

    # Skip retrieval for very low confidence (might be chitchat)
    if confidence < 0.3:
        return "generate"

    # Most query types benefit from retrieval
    if query_type in [
        QueryType.HISTORICAL_ANALYSIS,
        QueryType.WHAT_IF_SIMULATION,
        QueryType.COMPARISON,
        QueryType.GENERAL_KNOWLEDGE,
    ]:
        return "retrieve"

    return "generate"


def format_final_response(state: AgentStateDict) -> AgentStateDict:
    """
    Format the final response message.

    Args:
        state: Current agent state

    Returns:
        Updated state with formatted response as AI message
    """
    analysis = state.get("analysis_result", "I couldn't generate a response.")

    # Add the AI response to messages
    state["messages"].append(AIMessage(content=analysis))

    # Increment iteration count
    state["iteration_count"] = state.get("iteration_count", 0) + 1

    return state
