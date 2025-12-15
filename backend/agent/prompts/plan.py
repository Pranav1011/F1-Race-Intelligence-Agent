"""Prompts for the PLAN node."""

TOOL_DESCRIPTIONS = """
Available tools for F1 data retrieval:

## TimescaleDB Tools (Lap Times & Telemetry)

1. get_lap_times(driver_id, session_id, year)
   - Returns: All lap times, sector times, tire compounds, positions for a driver in a session
   - Use when: Need lap-by-lap performance data
   - Note: Set limit=None to get ALL laps, not just 50

2. get_session_results(year, session_id)
   - Returns: Race/qualifying results with positions, points, grid positions
   - Use when: Need final standings or race outcome

3. get_driver_stint_summary(session_id, driver_id)
   - Returns: Aggregated stint data (avg pace, tire life, laps per stint)
   - Use when: Analyzing tire strategy or stint performance

4. compare_driver_pace(session_id, driver_ids)
   - Returns: Head-to-head pace comparison between multiple drivers
   - Use when: Direct driver comparison requested

5. get_tire_degradation(session_id, driver_id, compound)
   - Returns: Lap-by-lap pace delta showing tire wear
   - Use when: Analyzing tire performance

6. get_available_sessions(year)
   - Returns: List of available sessions for a year
   - Use when: Need to find correct session_id

## Neo4j Tools (Knowledge Graph)

7. get_driver_info(driver_id)
   - Returns: Driver profile, team history, career stats
   - Use when: Need driver background

8. get_race_info(race_name, year)
   - Returns: Race details, circuit info, date, winner
   - Use when: Need race context

9. get_driver_stints_graph(driver_id, race_id)
   - Returns: Detailed pit strategy with exact pit laps
   - Use when: Analyzing pit stop timing

10. find_similar_situations(scenario)
    - Returns: Historical races matching a scenario
    - Use when: What-if analysis or finding precedents

## Vector Search Tools (RAG - Race Reports & Regulations)

11. search_race_reports(query, race_id, season, drivers, limit)
    - Returns: Relevant race reports, articles, and analysis
    - Use when: Need race summaries, winner info, or qualitative context
    - Best for: "Who won X race?", race outcomes, general race info

12. search_regulations(query, document_type, year, limit)
    - Returns: FIA regulation excerpts (sporting or technical)
    - Use when: Answering rules questions or explaining regulations
    - document_type: "sporting" or "technical"

13. search_reddit_discussions(query, race_id, min_score, limit)
    - Returns: Fan discussions from r/formula1
    - Use when: Need community opinions or popular narratives

14. search_past_analyses(query, query_type, limit)
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
1. For "who won" or race outcome questions, ALWAYS use search_race_reports first
2. For regulations/rules questions, ALWAYS use search_regulations
3. For "compare lap times" queries, get ALL laps (don't set limit, or set limit=None)
4. Group independent calls (e.g., lap times for different drivers) in parallel
5. Put dependent calls (e.g., get session_id first, then use it) in sequence
6. Include context tools (race_info, driver_info, search_race_reports) for comprehensive analysis
7. For strategy analysis, include both stint_summary and stints_graph
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
