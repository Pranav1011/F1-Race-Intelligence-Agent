# Enhanced Agent Architecture Design

## Problem Statement

The current agent implementation has several limitations:
1. **Limited data retrieval** - Fetches only 50 records instead of full race data
2. **Manual tool selection** - Hardcoded logic decides which tools to call
3. **No data aggregation** - Raw data goes directly to LLM without preprocessing
4. **No query understanding** - Doesn't understand scope (single lap vs full race)
5. **No feedback loop** - Can't recover if data is insufficient

## Solution: Production-Grade Agent with CRAG Pattern

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                    PRODUCTION-GRADE F1 AGENT                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   [1] UNDERSTAND          Parse + Memory + HyDE + Decompose             │
│         │                 → Check Mem0 for user preferences             │
│         │                 → Generate hypothetical answer (HyDE)         │
│         │                 → Decompose complex queries                   │
│         ↓                 → Output: QueryUnderstanding (Pydantic)       │
│                                                                         │
│   [2] PLAN                LLM creates execution DAG                     │
│         │                 → Parallel groups + sequential deps           │
│         │                 → Output: DataPlan (Pydantic)                 │
│         ↓                                                               │
│                                                                         │
│   [3] EXECUTE             Run tools with asyncio.gather()               │
│         │                 → Parallel execution where possible           │
│         │                 → Error handling with fallbacks               │
│         ↓                                                               │
│                                                                         │
│   [4] PROCESS             Python aggregates (not LLM)                   │
│         │                 → Compute averages, deltas, trends            │
│         │                 → Output: ProcessedAnalysis (Pydantic)        │
│         ↓                                                               │
│                                                                         │
│   [5] EVALUATE ◄────────────────────────────────────┐                   │
│         │       Is completeness_score >= 0.7?       │                   │
│         ├── NO ──► Refine feedback ──► [2] PLAN ────┘                   │
│         │          (max 2 iterations)                                   │
│         ↓ YES                                                           │
│                                                                         │
│   [6] GENERATE + VIZ      Parallel: response + visualization            │
│         │                 → LLM generates text analysis                 │
│         │                 → VIZ decides & generates chart spec          │
│         ↓                                                               │
│                                                                         │
│   [7] STORE               Save insights to Mem0                         │
│         ↓                                                               │
│                                                                         │
│       END                                                               │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Patterns

| Pattern | Node | Purpose |
|---------|------|---------|
| **CRAG** | EVALUATE | Loop back if data insufficient |
| **HyDE** | UNDERSTAND | Guide planning for vague queries |
| **Query Decomposition** | UNDERSTAND | Handle multi-part questions |
| **Parallel Execution** | EXECUTE | 1.8-3.7x latency reduction |
| **Pydantic Validation** | All nodes | Schema conformance, auto-retry |

---

## Pydantic Schemas

### Query Understanding

```python
class AnalysisScope(str, Enum):
    SINGLE_LAP = "single_lap"
    STINT = "stint"
    FULL_RACE = "full_race"
    MULTI_RACE = "multi_race"

class AnalysisType(str, Enum):
    COMPARISON = "comparison"
    STRATEGY = "strategy"
    PACE = "pace"
    TELEMETRY = "telemetry"
    INCIDENT = "incident"
    PREDICTION = "prediction"

class QueryUnderstanding(BaseModel):
    query_type: AnalysisType
    scope: AnalysisScope
    drivers: list[str]              # Normalized 3-letter codes
    teams: list[str]
    races: list[str]                # e.g., ["Monaco 2024"]
    seasons: list[int]
    metrics: list[str]              # e.g., ["lap_time", "tire_deg"]
    sub_queries: list[str]          # Decomposed questions
    hypothetical_answer: str        # HyDE - ideal answer structure
    confidence: float
```

### Data Planning

```python
class ToolCall(BaseModel):
    id: str                         # Unique ID for dependency tracking
    tool_name: str
    parameters: dict
    depends_on: list[str] = []      # IDs of tools this depends on

class DataPlan(BaseModel):
    tool_calls: list[ToolCall]
    parallel_groups: list[list[str]]  # Groups that can run concurrently
    expected_data_points: int
    reasoning: str
```

### Processed Analysis

```python
class ProcessedAnalysis(BaseModel):
    summary: dict                     # Aggregated data
    key_insights: list[str]           # Pre-computed findings
    completeness_score: float         # 0-1
    confidence_score: float           # 0-1
    missing_data: list[str]
    recommended_viz: list[str]

class EvaluationResult(BaseModel):
    is_sufficient: bool
    score: float
    feedback: str                     # What to fetch if insufficient
    iteration: int
```

---

## Node Implementations

### 1. UNDERSTAND Node

```python
async def understand_query(state, llm):
    user_message = get_last_human_message(state)

    understanding = await llm.invoke_structured(
        prompt=UNDERSTAND_PROMPT,
        context={
            "user_message": user_message,
            "conversation_history": state["messages"][-5:],
        },
        output_schema=QueryUnderstanding
    )

    return {"query_understanding": understanding.model_dump()}
```

**UNDERSTAND_PROMPT includes:**
- Extract drivers, teams, races, seasons
- Determine analysis scope (single lap vs full race)
- Generate HyDE (hypothetical ideal answer)
- Decompose complex queries into sub-queries

### 2. PLAN Node

```python
async def plan_data_retrieval(state, llm):
    understanding = QueryUnderstanding(**state["query_understanding"])
    feedback = state.get("evaluation_feedback", "")

    plan = await llm.invoke_structured(
        prompt=PLANNER_PROMPT,
        context={
            "understanding": understanding.model_dump(),
            "available_tools": TOOL_DESCRIPTIONS,
            "previous_feedback": feedback,
        },
        output_schema=DataPlan
    )

    return {"data_plan": plan.model_dump()}
```

### 3. EXECUTE Node

```python
async def execute_tools(state, tools):
    plan = DataPlan(**state["data_plan"])
    results = {}

    for group in plan.parallel_groups:
        tasks = [
            tools[call.tool_name](**call.parameters)
            for call in plan.tool_calls if call.id in group
        ]
        group_results = await asyncio.gather(*tasks, return_exceptions=True)

        for tool_id, result in zip(group, group_results):
            results[tool_id] = result if not isinstance(result, Exception) else {"error": str(result)}

    return {"raw_data": results}
```

### 4. PROCESS Node

```python
async def process_data(state):
    raw_data = state["raw_data"]
    understanding = QueryUnderstanding(**state["query_understanding"])

    processed = ProcessedAnalysis(
        summary={},
        key_insights=[],
        completeness_score=0.0,
        confidence_score=0.0,
        missing_data=[],
        recommended_viz=[]
    )

    # Aggregate lap times
    if "lap_times" in raw_data:
        processed.summary["lap_analysis"] = aggregate_lap_times(raw_data["lap_times"])

    # Compute driver comparison
    if understanding.query_type == AnalysisType.COMPARISON:
        processed.summary["comparison"] = compute_driver_comparison(raw_data)
        processed.key_insights = extract_comparison_insights(processed.summary)
        processed.recommended_viz = ["lap_progression", "sector_comparison"]

    # Calculate completeness
    processed.completeness_score = calculate_completeness(raw_data, understanding)

    return {"processed_analysis": processed.model_dump()}
```

### 5. EVALUATE Node

```python
async def evaluate_data(state):
    processed = ProcessedAnalysis(**state["processed_analysis"])
    iteration = state.get("iteration_count", 0)

    if processed.completeness_score >= 0.7 or iteration >= 2:
        return {"evaluation": {"is_sufficient": True, "iteration": iteration}}

    # Generate feedback for PLAN node
    feedback = f"Missing data: {processed.missing_data}. Need to fetch additional data."

    return {
        "evaluation": {"is_sufficient": False, "iteration": iteration + 1},
        "evaluation_feedback": feedback,
        "iteration_count": iteration + 1
    }
```

### 6. GENERATE + VIZ Node

```python
async def generate_response(state, llm):
    processed = ProcessedAnalysis(**state["processed_analysis"])
    understanding = QueryUnderstanding(**state["query_understanding"])

    # Generate text response
    response = await llm.invoke(
        prompt=ANALYST_PROMPT,
        context={
            "processed_data": processed.summary,
            "key_insights": processed.key_insights,
            "user_query": get_last_human_message(state)
        }
    )

    # Generate visualization spec
    viz_spec = None
    if processed.recommended_viz:
        viz_spec = generate_viz_spec(
            viz_type=processed.recommended_viz[0],
            data=processed.summary,
            drivers=understanding.drivers
        )

    return {
        "analysis_result": response,
        "visualization_spec": viz_spec
    }
```

---

## Visualization System

### Supported Chart Types

| Type | Use Case | Data Required |
|------|----------|---------------|
| `lap_progression` | Lap time trends | lap_times per driver |
| `position_battle` | Race trace | positions per lap |
| `tire_strategy` | Strategy timeline | stints, pit_stops |
| `sector_comparison` | Sector breakdown | sector_times |
| `speed_trace` | Telemetry overlay | speed, distance |
| `gap_evolution` | Gap to leader | intervals per lap |

### Visualization Spec Schema

```python
class VisualizationSpec(BaseModel):
    type: str                       # Chart type
    title: str
    data: list[dict]                # Processed data points
    config: dict                    # Chart-specific config
    drivers: list[str]              # For color coding
    annotations: list[dict] = []    # Pit stops, incidents
```

---

## File Structure

```
backend/agent/
├── __init__.py
├── graph.py                    # LangGraph definition
├── state.py                    # State schema
├── schemas/
│   ├── __init__.py
│   ├── query.py               # QueryUnderstanding, DataPlan
│   └── analysis.py            # ProcessedAnalysis, EvaluationResult
├── nodes/
│   ├── __init__.py
│   ├── understand.py          # UNDERSTAND node
│   ├── plan.py                # PLAN node
│   ├── execute.py             # EXECUTE node
│   ├── process.py             # PROCESS node
│   ├── evaluate.py            # EVALUATE node
│   └── generate.py            # GENERATE + VIZ node
├── processors/
│   ├── __init__.py
│   ├── lap_analysis.py        # Lap time aggregation
│   ├── comparison.py          # Driver comparison logic
│   ├── strategy.py            # Strategy analysis
│   └── visualization.py       # Viz spec generation
├── prompts/
│   ├── __init__.py
│   ├── understand.py          # UNDERSTAND_PROMPT
│   ├── plan.py                # PLANNER_PROMPT
│   └── generate.py            # ANALYST_PROMPT
├── tools/                     # Keep existing tools
└── llm.py                     # Keep existing LLM router
```

---

## Implementation Order

1. **Schemas** - Create Pydantic models
2. **Prompts** - Write LLM prompts for each node
3. **Processors** - Data aggregation functions
4. **Nodes** - Individual node implementations
5. **Graph** - Wire up LangGraph with conditional routing
6. **Visualization** - Chart spec generation
7. **Testing** - Test with various query types

---

## Success Criteria

- [ ] "Compare lap times" fetches ALL laps, not just 50
- [ ] Response includes aggregated insights (avg pace, fastest lap, etc.)
- [ ] EVALUATE loop triggers when data is insufficient
- [ ] Visualization spec generated for comparison queries
- [ ] Response time < 10s for typical queries
