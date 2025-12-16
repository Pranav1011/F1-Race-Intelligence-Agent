"""Prompts for the PLAN node."""

TOOL_DESCRIPTIONS = """
Available tools for F1 data retrieval:

## TimescaleDB Tools (Lap Times & Telemetry)

1. get_lap_times(driver_id, year, event_name, session_id, limit)
   - Returns: All lap times, sector times, tire compounds, positions for a driver
   - Use when: Need lap-by-lap performance data
   - IMPORTANT: Use event_name (e.g. "United States", "Monaco") to filter by race name
   - Note: Don't set limit, or set limit=200 to get ALL laps

2. get_head_to_head(driver_1, driver_2, year, event_name)
   - Returns: Pre-computed head-to-head comparison with pace delta, fastest laps, sector deltas
   - Use when: Comparing two drivers (BEST TOOL for driver vs driver comparisons!)
   - ALWAYS use this for "X vs Y" or "compare X to Y" queries
   - Uses materialized views for instant results

3. get_session_results(year, session_id, driver_id)
   - Returns: Race/qualifying results with positions, points, grid positions
   - Use when: Need final standings or race outcome

4. get_driver_stint_summary(session_id, driver_id)
   - Returns: Aggregated stint data (avg pace, tire life, laps per stint)
   - Use when: Analyzing tire strategy or stint performance

5. compare_driver_pace(session_id, driver_ids, stint)
   - Returns: Head-to-head pace comparison between multiple drivers
   - Use when: Need stint-specific pace analysis

6. get_tire_degradation(session_id, driver_id, compound)
   - Returns: Lap-by-lap pace delta showing tire wear
   - Use when: Analyzing tire performance

7. get_available_sessions(year)
   - Returns: List of available sessions with session_id, event_name, round_number
   - Use when: Need to find correct session_id for a race

8. get_race_summary(year, event_name, round_number)
   - Returns: Race statistics including winner, fastest lap, average pace
   - Use when: Need race overview without detailed lap data

9. get_stint_analysis(year, event_name, driver_id)
   - Returns: Detailed stint data with compound, laps, pace, degradation
   - Use when: Analyzing tire strategy for a specific race

## Neo4j Tools (Knowledge Graph)

10. get_driver_info(driver_id)
    - Returns: Driver profile, team history, career stats
    - Use when: Need driver background

11. get_race_info(race_name, year)
    - Returns: Race details, circuit info, date, winner
    - Use when: Need race context

12. get_driver_stints_graph(driver_id, race_id)
    - Returns: Detailed pit strategy with exact pit laps
    - Use when: Analyzing pit stop timing

13. find_similar_situations(scenario)
    - Returns: Historical races matching a scenario
    - Use when: What-if analysis or finding precedents

## Vector Search Tools (RAG - Race Reports & Regulations)

14. search_race_reports(query, race_id, season, drivers, limit)
    - Returns: Relevant race reports, articles, and analysis
    - Use when: Need race summaries, winner info, or qualitative context
    - Best for: "Who won X race?", race outcomes, general race info

15. search_regulations(query, document_type, year, limit)
    - Returns: FIA regulation excerpts (sporting or technical)
    - Use when: Answering rules questions or explaining regulations
    - document_type: "sporting" or "technical"

16. search_reddit_discussions(query, race_id, min_score, limit)
    - Returns: Fan discussions from r/formula1
    - Use when: Need community opinions or popular narratives

17. search_past_analyses(query, query_type, limit)
    - Returns: Similar past analyses from this agent
    - Use when: Similar questions were asked before

## Session ID Format
Session IDs follow the pattern: {year}_{round}_{type}
- year: 2018-2024
- round: Race number (1-24)
- type: R (race), Q (qualifying), S (sprint), FP1/FP2/FP3 (practice)

Example: "2024_6_R" = 2024 Monaco GP Race (round 6)

## Race Round Numbers (2024)
1: Bahrain, 2: Saudi Arabia, 3: Australia, 4: Japan, 5: China,
6: Miami, 7: Emilia Romagna, 8: Monaco, 9: Canada, 10: Spain,
11: Austria, 12: Britain, 13: Hungary, 14: Belgium, 15: Netherlands,
16: Italy, 17: Azerbaijan, 18: Singapore, 19: USA, 20: Mexico,
21: Brazil, 22: Las Vegas, 23: Qatar, 24: Abu Dhabi
"""

PLAN_SYSTEM = """You are an F1 data retrieval planner. Given a query understanding, decide which tools to call to gather the necessary data.

Output a JSON object with:
- tool_calls: List of tool calls, each with:
  - id: Unique identifier (e.g., "lap_times_ver")
  - tool_name: Name of the tool
  - parameters: Dict of parameters
  - depends_on: List of tool IDs this depends on (for sequential execution)
  - purpose: Why this tool is being called
- parallel_groups: List of lists grouping tool IDs that can run concurrently
- expected_data_points: Estimated number of data points
- reasoning: Why you chose these tools

IMPORTANT RULES:
1. For DRIVER COMPARISON queries (e.g., "compare HAM vs VER"), ALWAYS use get_head_to_head - it provides pre-computed pace delta, sector deltas, and comparable laps
2. For "who won" or race outcome questions, ALWAYS use search_race_reports first
3. For regulations/rules questions, ALWAYS use search_regulations
4. When using get_lap_times, ALWAYS include event_name parameter (e.g., "United States", "Monaco") to filter by race
5. Group independent calls (e.g., lap times for different drivers) in parallel
6. Put dependent calls (e.g., get session_id first, then use it) in sequence
7. Include context tools (race_info, driver_info, search_race_reports) for comprehensive analysis
8. For strategy analysis, include both stint_summary and stints_graph
9. Use year and event_name to filter data - don't rely only on session_id
"""

PLAN_PROMPT = """Create a data retrieval plan for this F1 query:

Query Understanding:
{understanding}

{previous_feedback}

Available Tools:
{available_tools}

Create an execution plan that:
1. Fetches all necessary data (not limited samples)
2. Groups parallel operations for efficiency
3. Orders dependent operations correctly

JSON Response:"""
