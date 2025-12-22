"""Prompts for the PLAN node."""

TOOL_DESCRIPTIONS = """
Available tools for F1 data retrieval:

## TimescaleDB Tools (Lap Times, Pit Stops & Telemetry)

1. get_lap_times(driver_id, year, event_name, session_id, limit)
   - Returns: All lap times, sector times, tire compounds, positions for a driver
   - Use when: Need lap-by-lap performance data
   - IMPORTANT: Use event_name (e.g. "United States", "Monaco") to filter by race name
   - Note: Don't set limit, or set limit=200 to get ALL laps

2. get_pit_stops(year, event_name, driver_id, limit)
   - Returns: Pit stop times with ranking, lap number, tire compounds, team
   - Use when: "Fastest pit stops", "pit stop times", "best pit stop", "pit crew performance"
   - ALWAYS use this for ANY pit stop related queries!
   - Returns pit stops sorted by duration (fastest first)
   - Example: get_pit_stops(year=2024) returns fastest pit stops of 2024

3. get_head_to_head(driver_1, driver_2, year, event_name)
   - Returns: Pre-computed head-to-head comparison with pace delta, fastest laps, sector deltas
   - Use when: Comparing two drivers (BEST TOOL for driver vs driver comparisons!)
   - ALWAYS use this for "X vs Y" or "compare X to Y" queries
   - Uses materialized views for instant results

4. get_session_results(year, session_id, driver_id)
   - Returns: Race/qualifying results with positions, points, grid positions
   - Use when: Need final standings or race outcome

5. get_driver_stint_summary(session_id, driver_id)
   - Returns: Aggregated stint data (avg pace, tire life, laps per stint)
   - Use when: Analyzing tire strategy or stint performance

6. compare_driver_pace(session_id, driver_ids, stint)
   - Returns: Head-to-head pace comparison between multiple drivers
   - Use when: Need stint-specific pace analysis

7. get_tire_degradation(session_id, driver_id, compound)
   - Returns: Lap-by-lap pace delta showing tire wear
   - Use when: Analyzing tire performance

8. get_available_sessions(year)
   - Returns: List of available sessions with session_id, event_name, round_number
   - Use when: Need to find correct session_id for a race

9. get_race_summary(year, event_name, round_number)
   - Returns: Race statistics including winner, fastest lap, average pace
   - Use when: Need race overview without detailed lap data

10. get_stint_analysis(year, event_name, driver_id)
    - Returns: Detailed stint data with compound, laps, pace, degradation
    - Use when: Analyzing tire strategy for a specific race

## Advanced Analytical Tools (Season-Wide & Field Comparisons)

11. get_driver_vs_field(driver_ids, year, metric)
    - Returns: Driver(s) stats compared to field average with dominance metrics
    - Use when: "How dominant was X", "X vs the field", "X compared to everyone"
    - metric options: "pace", "positions", "points_per_race"
    - PERFECT FOR: Dominance analysis, field comparisons!

12. get_season_pace_ranking(year, top_n)
    - Returns: All drivers ranked by season-average pace
    - Use when: "Fastest drivers of 2024", "pace rankings", "who was quickest"
    - Includes gap to field average

13. get_performance_trend(driver_id, year, window_size)
    - Returns: Race-by-race performance with rolling averages and trend
    - Use when: "Was X improving?", "performance trend", "getting better or worse"
    - Shows IMPROVING, DECLINING, or STABLE trend

14. compare_teams(team_1, team_2, year)
    - Returns: Head-to-head team comparison (pace, points, wins)
    - Use when: "Mercedes vs Red Bull", "team comparison", "constructor battle"

15. get_qualifying_race_delta(year, driver_id)
    - Returns: Position gained/lost from grid to finish for all drivers
    - Use when: "Who gains most positions", "qualifying vs race", "race craft"
    - Shows race craft rating: EXCELLENT, GOOD, POOR

## Specialized Analytical Tools (Overtaking, Sectors, Consistency)

16. get_overtaking_analysis(year, event_name, driver_id)
    - Returns: Positions gained/lost during races, overtake counts, net gains
    - Use when: "Most overtakes", "who passes the most", "best overtaker", "position changes"
    - PERFECT FOR: Overtaking analysis and wheel-to-wheel racing stats!

17. get_sector_performance(year, event_name, sector)
    - Returns: Driver rankings by sector, best sector times, sector dominance
    - Use when: "Who is fastest in sector 3", "sector dominance", "best sectors"
    - Can filter by specific sector (1, 2, or 3)

18. get_consistency_ranking(year, min_races)
    - Returns: Drivers ranked by lap time consistency (lowest variance)
    - Use when: "Most consistent driver", "who is most reliable", "least variance"
    - Shows consistency rating: VERY_CONSISTENT, CONSISTENT, INCONSISTENT

19. get_reliability_stats(year, by_team)
    - Returns: DNFs, mechanical failures, finish rate by driver or team
    - Use when: "Most reliable team", "DNF stats", "who retires most", "reliability"
    - Set by_team=true for constructor reliability

20. get_wet_weather_performance(year, driver_id)
    - Returns: Performance in wet/intermediate conditions, rain race results
    - Use when: "Best in the rain", "wet weather specialist", "rain master"
    - Shows rain_rating: EXCELLENT, GOOD, AVERAGE, POOR

21. get_lap1_performance(year, driver_id)
    - Returns: First lap position changes, average lap 1 gain/loss
    - Use when: "Best starter", "lap 1 gains", "first lap performance", "opening lap"
    - Shows start_rating based on positions gained

22. get_fastest_lap_stats(year, driver_id)
    - Returns: Fastest lap frequency, race pace excellence metrics
    - Use when: "Most fastest laps", "who sets fastest laps", "pace kings"
    - Tracks fastest lap count and percentage

23. get_teammate_battle(year, team)
    - Returns: Comprehensive season-long teammate comparison
    - Use when: "Teammate battle", "intra-team comparison", "who beat their teammate"
    - Includes qualifying H2H, race H2H, points comparison

24. get_points_finish_rate(year)
    - Returns: Percentage of races each driver scores points
    - Use when: "Points percentage", "scoring rate", "most consistent scorer"
    - Good for evaluating midfield consistency

## Circuit & Historical Tools

25. get_track_specialist(event_name, year, top_n)
    - Returns: Drivers ranked by performance at a specific circuit
    - Use when: "Who is best at Monaco?", "Silverstone specialist", "track kings"
    - Shows win rate, podium rate, avg finish at that circuit

26. get_championship_evolution(year, driver_ids)
    - Returns: Race-by-race cumulative points and gaps throughout season
    - Use when: "Points gap over season", "championship battle", "title race"
    - Shows when title was mathematically clinched

27. get_career_stats(driver_id, start_year, end_year)
    - Returns: Multi-season career statistics (wins, poles, podiums, points)
    - Use when: "All-time wins", "career poles", "total points", "legacy"
    - Includes season-by-season breakdown

28. get_qualifying_stats(year, driver_id)
    - Returns: Qualifying performance - poles, front row, avg grid position
    - Use when: "Most poles", "qualifying specialist", "average grid"
    - Shows quali_tier: ELITE, STRONG, MIDFIELD, BACKMARKER

29. get_podium_stats(year, driver_id, top_n)
    - Returns: Podium counts, percentages, win-to-podium ratio
    - Use when: "Most podiums", "podium percentage", "podium machine"
    - Can be filtered by year or show career stats

30. get_race_dominance(year, event_name)
    - Returns: Winning margins, dominant victories, led-from-start stats
    - Use when: "Biggest winning margin", "dominant win", "crushing victory"
    - Shows dominance_rating: CRUSHING, DOMINANT, COMFORTABLE, CLOSE

31. get_compound_performance(year, event_name, driver_id)
    - Returns: Pace analysis by tire compound (soft/medium/hard)
    - Use when: "Soft vs Medium pace", "best on hards", "tire performance"
    - Shows compound preference and degradation

## Streaks, Sprints & Special Analysis Tools

32. get_sprint_performance(year, driver_id)
    - Returns: Sprint race statistics vs main race performance
    - Use when: "Sprint specialist", "sprint vs race", "best in sprints"
    - Shows sprint_specialist: YES, SIMILAR, RACE_STRONGER

33. get_winning_streaks(year, driver_id, streak_type)
    - Returns: Consecutive wins, podiums, or points streaks
    - Use when: "Consecutive wins", "longest streak", "unbeaten run"
    - streak_type: "wins", "podiums", or "points"

34. get_constructor_evolution(year, team_names)
    - Returns: Race-by-race constructor championship points battle
    - Use when: "Constructor battle", "team points gap", "constructor championship"
    - Like championship_evolution but for teams

35. get_home_race_performance(driver_id, year)
    - Returns: Performance at home GP vs away races
    - Use when: "Home race advantage", "Hamilton at Silverstone", "home GP"
    - Shows home_performance: DOMINANT, STRONG, SIMILAR, STRUGGLES

36. get_comeback_drives(year, min_positions_gained, top_n)
    - Returns: Best recovery drives - positions gained from poor starts
    - Use when: "Best recovery", "from back of grid", "great drives"
    - Shows comeback_rating: LEGENDARY, INCREDIBLE, GREAT, SOLID

37. get_grid_penalty_impact(year, driver_id)
    - Returns: How grid penalties affected race results
    - Use when: "Grid penalty effect", "penalty impact", "starting from back"
    - Shows damage_limitation rating

38. get_finishing_streaks(year, driver_id)
    - Returns: Consecutive race finishes (no DNFs) - reliability streaks
    - Use when: "Consecutive finishes", "no DNF streak", "reliability streak"
    - Shows reliability_rating: BULLETPROOF, RELIABLE, AVERAGE, FRAGILE

## Advanced Race Analysis Tools

39. get_gap_to_leader(year, event_name, driver_id)
    - Returns: Finishing gaps to race winner, margin analysis
    - Use when: "How far behind was P2?", "gap to winner", "winning margin"
    - Shows gap in seconds for each position

40. get_strategy_effectiveness(year, event_name)
    - Returns: 1-stop vs 2-stop vs 3-stop strategy outcomes
    - Use when: "Which strategy worked?", "1-stop vs 2-stop", "optimal strategy"
    - Shows effectiveness rating per strategy

41. get_safety_car_impact(year, driver_id)
    - Returns: How drivers perform in races with vs without safety cars
    - Use when: "Safety car luck", "SC beneficiary", "who benefits from safety cars"
    - Shows sc_luck_rating: VERY_LUCKY, LUCKY, NEUTRAL, UNLUCKY

42. get_tire_life_masters(year, compound)
    - Returns: Drivers ranked by tire management - longest stints
    - Use when: "Tire whisperer", "who makes tires last", "longest stints"
    - Shows tire_management: EXCEPTIONAL, EXCELLENT, GOOD, AVERAGE

43. get_championship_momentum(year, last_n_races)
    - Returns: Recent form analysis - points in last N races
    - Use when: "Hot streak", "momentum", "form last 5 races", "who's on fire"
    - Shows form: ON_FIRE, HOT, CONSISTENT, COOLING, COLD

44. get_head_to_head_career(driver_1, driver_2, start_year, end_year)
    - Returns: All-time head-to-head record between two drivers
    - Use when: "All-time Hamilton vs Verstappen", "career H2H", "lifetime record"
    - Shows race H2H, qualifying H2H, total points

45. get_rookie_comparison(year)
    - Returns: Rookie performance vs veterans in a season
    - Use when: "Rookie of the year", "best rookie", "rookie vs veteran"
    - Shows rookie rating and rankings

46. get_team_lockouts(year, team)
    - Returns: 1-2 finishes and front row lockouts by teams
    - Use when: "1-2 finishes", "front row lockout", "team dominance"
    - Shows dominance_rating for teams

47. get_undercut_success(year, event_name)
    - Returns: Position changes from pit stop timing (undercut/overcut)
    - Use when: "Undercut effectiveness", "pit strategy moves", "overcut worked"
    - Shows pit_strategy_rating

48. get_points_per_start(year, min_races)
    - Returns: Points efficiency - average points per race
    - Use when: "Points efficiency", "average points per race", "best scorer"
    - Shows efficiency_tier: ELITE, EXCELLENT, GOOD, AVERAGE, LOW

49. get_final_lap_heroics(year, top_n)
    - Returns: Dramatic final lap position changes
    - Use when: "Last lap overtake", "final lap drama", "clutch performance"
    - Shows drama_rating: LEGENDARY, DRAMATIC, EXCITING

50. get_clean_weekend_rate(year, driver_id)
    - Returns: Incident-free race rates - clean execution
    - Use when: "Clean weekends", "no mistakes", "incident-free"
    - Shows execution_rating: FLAWLESS, EXCELLENT, GOOD, INCONSISTENT

## Neo4j Tools (Knowledge Graph)

51. get_driver_info(driver_id)
    - Returns: Driver profile, team history, career stats
    - Use when: Need driver background

52. get_race_info(race_name, year)
    - Returns: Race details, circuit info, date, winner
    - Use when: Need race context

53. get_driver_stints_graph(driver_id, race_id)
    - Returns: Detailed pit strategy with exact pit laps
    - Use when: Analyzing pit stop timing

54. find_similar_situations(scenario)
    - Returns: Historical races matching a scenario
    - Use when: What-if analysis or finding precedents

## Vector Search Tools (RAG - Race Reports & Regulations)

55. search_race_reports(query, race_id, season, drivers, limit)
    - Returns: Relevant race reports, articles, and analysis
    - Use when: Need race summaries, winner info, or qualitative context
    - Best for: "Who won X race?", race outcomes, general race info

56. search_regulations(query, document_type, year, limit)
    - Returns: FIA regulation excerpts (sporting or technical)
    - Use when: Answering rules questions or explaining regulations
    - document_type: "sporting" or "technical"

57. search_reddit_discussions(query, race_id, min_score, limit)
    - Returns: Fan discussions from r/formula1
    - Use when: Need community opinions or popular narratives

58. search_past_analyses(query, query_type, limit)
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

## CRITICAL ROUTING RULES - ALWAYS FOLLOW THESE:

### Query Pattern -> Tool Mapping (MANDATORY):
- "pit stop" / "fastest pit" / "pit times" / "pit crew" -> get_pit_stops()
- "compare X vs Y" / "X versus Y" (2 drivers) -> get_head_to_head()
- "dominant" / "vs the field" / "vs everyone" / "rest of field" -> get_driver_vs_field()
- "fastest drivers" / "pace ranking" / "quickest" -> get_season_pace_ranking()
- "improving" / "trend" / "getting better/worse" -> get_performance_trend()
- "Mercedes vs Red Bull" / "team battle" / "constructor" -> compare_teams()
- "gains positions" / "qualifying vs race" / "race craft" -> get_qualifying_race_delta()
- "lap times" / "pace" / "fastest lap" -> get_lap_times()
- "strategy" / "tire strategy" / "stint" -> get_stint_analysis() + get_driver_stint_summary()
- "who won" / "race winner" / "podium" -> get_session_results() OR search_race_reports()
- "standings" / "championship" / "points" -> get_season_standings()
- "regulations" / "rules" / "legal" -> search_regulations()
- "overtakes" / "passes" / "position changes" / "wheel to wheel" -> get_overtaking_analysis()
- "sector" / "S1" / "S2" / "S3" / "sector time" -> get_sector_performance()
- "consistent" / "consistency" / "variance" / "steady" -> get_consistency_ranking()
- "reliability" / "DNF" / "retired" / "mechanical failure" -> get_reliability_stats()
- "rain" / "wet" / "intermediate" / "changeable conditions" -> get_wet_weather_performance()
- "lap 1" / "first lap" / "start" / "opening lap" / "lights out" -> get_lap1_performance()
- "fastest lap count" / "most fastest laps" / "purple sectors" -> get_fastest_lap_stats()
- "teammate" / "intra-team" / "partner" / "same team" -> get_teammate_battle()
- "points percentage" / "scoring rate" / "points finish" -> get_points_finish_rate()
- "best at Monaco" / "Silverstone specialist" / "track record" / "circuit king" -> get_track_specialist()
- "championship battle" / "title fight" / "points gap" / "clinched" -> get_championship_evolution()
- "career stats" / "all-time wins" / "career poles" / "total points" -> get_career_stats()
- "qualifying performance" / "most poles" / "average grid" / "quali specialist" -> get_qualifying_stats()
- "most podiums" / "podium percentage" / "podium streak" -> get_podium_stats()
- "winning margin" / "dominant win" / "crushing victory" / "laps led" -> get_race_dominance()
- "soft vs medium" / "tire compound" / "best on hards" / "compound pace" -> get_compound_performance()
- "sprint" / "sprint race" / "sprint specialist" -> get_sprint_performance()
- "consecutive wins" / "winning streak" / "unbeaten" / "streak" -> get_winning_streaks()
- "constructor battle" / "team championship" / "constructor evolution" -> get_constructor_evolution()
- "home race" / "home GP" / "home advantage" -> get_home_race_performance()
- "comeback" / "recovery drive" / "from back" / "great drive" -> get_comeback_drives()
- "grid penalty" / "penalty impact" / "engine penalty" -> get_grid_penalty_impact()
- "finishing streak" / "consecutive finishes" / "no DNF" -> get_finishing_streaks()
- "gap to leader" / "how far behind" / "winning margin" / "margin of victory" -> get_gap_to_leader()
- "1-stop vs 2-stop" / "strategy effectiveness" / "optimal strategy" -> get_strategy_effectiveness()
- "safety car" / "SC impact" / "SC luck" / "VSC" -> get_safety_car_impact()
- "tire management" / "makes tires last" / "longest stint" / "tire whisperer" -> get_tire_life_masters()
- "momentum" / "hot streak" / "form" / "last 5 races" / "on fire" -> get_championship_momentum()
- "all-time H2H" / "career head to head" / "lifetime record" -> get_head_to_head_career()
- "rookie" / "rookie of year" / "best rookie" / "rookie vs veteran" -> get_rookie_comparison()
- "1-2 finish" / "team lockout" / "front row lockout" -> get_team_lockouts()
- "undercut" / "overcut" / "pit timing" / "strategy move" -> get_undercut_success()
- "points per race" / "points efficiency" / "average points" -> get_points_per_start()
- "last lap" / "final lap" / "last lap overtake" / "clutch" -> get_final_lap_heroics()
- "clean weekend" / "incident free" / "no mistakes" / "clean execution" -> get_clean_weekend_rate()
- "pole to win" / "converting poles" / "pole conversion" / "pole sitter wins" -> get_pole_to_win_conversion()
- "front row advantage" / "win from P3" / "grid position advantage" / "start position" -> get_grid_position_advantage()
- "street circuit" / "Monaco specialist" / "power track" / "downforce track" -> get_circuit_type_performance()
- "Q3 specialist" / "qualifying shootout" / "Q3 performance" / "last Q3 lap" -> get_q3_shootout_performance()
- "race driver" / "Sunday driver" / "qualifying vs race pace" / "quali pace vs race pace" -> get_race_pace_vs_quali_pace()
- "most battles" / "wheel to wheel" / "position battles" / "racing incidents" -> get_position_battle_stats()
- "average running position" / "mean race position" / "where they run" -> get_average_race_position()
- "career points" / "points trajectory" / "career milestones" / "points over time" -> get_points_trajectory()
- "DRS effectiveness" / "DRS train" / "DRS overtakes" / "DRS zone" -> get_drs_effectiveness()
- "tire warm-up" / "outlap pace" / "cold tires" / "tire prep" -> get_tire_warmup_specialist()
- "Q1 to Q3" / "qualifying improvement" / "peaks in Q3" / "quali progression" -> get_qualifying_improvement()
- "theoretical best" / "best sectors combined" / "potential pole" / "ultimate lap" -> get_theoretical_best_lap()
- "pace degradation" / "tire drop-off" / "pace through race" -> get_race_pace_degradation()
- "red flag restart" / "standing restart" / "restart performance" -> get_red_flag_restart_performance()
- "early season" / "late season" / "season phases" / "mid-season form" -> get_season_phase_performance()
- "back to back" / "double header" / "triple header" / "consecutive races" -> get_back_to_back_performance()
- "championship pressure" / "title fight" / "pressure handling" / "clutch driver" -> get_championship_pressure_performance()
- "pit exit" / "out-lap pace" / "getting up to speed" -> get_pit_exit_performance()
- "defensive driving" / "position defense" / "holding position" / "defending" -> get_defensive_driving_stats()
- "traffic management" / "lapped cars" / "blue flags" / "backmarkers" -> get_traffic_management()
- "fuel effect" / "heavy fuel" / "light fuel" / "fuel load pace" -> get_fuel_adjusted_pace()
- "tire cliff" / "sudden drop-off" / "tire degradation spike" -> get_tire_cliff_analysis()

### IMPORTANT RULES:
1. **DOMINANCE / FIELD COMPARISON queries**: Use get_driver_vs_field() - compares driver(s) to all others!
2. **SEASON-WIDE pace analysis**: Use get_season_pace_ranking() for full grid rankings
3. **TREND analysis**: Use get_performance_trend() for race-by-race with rolling averages
4. **TEAM comparison**: Use compare_teams() for constructor battles
5. **QUALIFYING vs RACE**: Use get_qualifying_race_delta() for position gain/loss analysis
6. **PIT STOP queries**: Use get_pit_stops() - the ONLY tool for pit stop times!
7. **2-DRIVER COMPARISON queries**: Use get_head_to_head() for pace delta, sector deltas
8. **Race outcome questions**: Use get_session_results or search_race_reports
9. **OVERTAKING queries**: Use get_overtaking_analysis() for passes, position changes
10. **SECTOR queries**: Use get_sector_performance() for S1/S2/S3 dominance
11. **CONSISTENCY queries**: Use get_consistency_ranking() for variance analysis
12. **RELIABILITY queries**: Use get_reliability_stats() for DNFs and mechanical issues
13. **WET WEATHER queries**: Use get_wet_weather_performance() for rain specialists
14. **LAP 1 / START queries**: Use get_lap1_performance() for opening lap analysis
15. **FASTEST LAP queries**: Use get_fastest_lap_stats() for purple sector kings
16. **TEAMMATE queries**: Use get_teammate_battle() for intra-team comparisons
17. **CIRCUIT SPECIALIST queries**: Use get_track_specialist() for track-specific performance
18. **CHAMPIONSHIP EVOLUTION queries**: Use get_championship_evolution() for title battles
19. **CAREER / HISTORICAL queries**: Use get_career_stats() for multi-season aggregates
20. **QUALIFYING STATS queries**: Use get_qualifying_stats() for poles, grid positions
21. **PODIUM queries**: Use get_podium_stats() for podium counts and percentages
22. **RACE DOMINANCE queries**: Use get_race_dominance() for winning margins
23. **COMPOUND/TIRE queries**: Use get_compound_performance() for soft vs medium vs hard
24. **SPRINT queries**: Use get_sprint_performance() for sprint race analysis
25. **STREAK queries**: Use get_winning_streaks() for consecutive wins/podiums/points
26. **CONSTRUCTOR CHAMPIONSHIP queries**: Use get_constructor_evolution() for team title battles
27. **HOME RACE queries**: Use get_home_race_performance() for home GP advantage analysis
28. **COMEBACK queries**: Use get_comeback_drives() for recovery from bad grid positions
29. **PENALTY queries**: Use get_grid_penalty_impact() for grid penalty effects
30. **FINISHING STREAK queries**: Use get_finishing_streaks() for reliability streaks
31. **GAP TO LEADER queries**: Use get_gap_to_leader() for finishing margins
32. **STRATEGY COMPARISON queries**: Use get_strategy_effectiveness() for 1-stop vs 2-stop
33. **SAFETY CAR queries**: Use get_safety_car_impact() for SC luck analysis
34. **TIRE MANAGEMENT queries**: Use get_tire_life_masters() for stint length rankings
35. **MOMENTUM queries**: Use get_championship_momentum() for recent form analysis
36. **CAREER H2H queries**: Use get_head_to_head_career() for all-time driver comparisons
37. **ROOKIE queries**: Use get_rookie_comparison() for rookie season analysis
38. **TEAM LOCKOUT queries**: Use get_team_lockouts() for 1-2 finishes
39. **UNDERCUT queries**: Use get_undercut_success() for pit timing effectiveness
40. **POINTS EFFICIENCY queries**: Use get_points_per_start() for average points per race
41. **FINAL LAP queries**: Use get_final_lap_heroics() for last lap drama
42. **CLEAN WEEKEND queries**: Use get_clean_weekend_rate() for incident-free execution
43. **POLE CONVERSION queries**: Use get_pole_to_win_conversion() for pole-to-win statistics
44. **GRID ADVANTAGE queries**: Use get_grid_position_advantage() for win rate by grid slot
45. **CIRCUIT TYPE queries**: Use get_circuit_type_performance() for street vs power vs downforce tracks
46. **Q3 SHOOTOUT queries**: Use get_q3_shootout_performance() for qualifying shootout analysis
47. **RACE VS QUALI queries**: Use get_race_pace_vs_quali_pace() for Sunday driver analysis
48. **POSITION BATTLE queries**: Use get_position_battle_stats() for wheel-to-wheel statistics
49. **RUNNING POSITION queries**: Use get_average_race_position() for average position during race
50. **CAREER POINTS queries**: Use get_points_trajectory() for career milestones and trajectory
51. **DRS queries**: Use get_drs_effectiveness() for DRS zone overtakes and effectiveness
52. **TIRE WARMUP queries**: Use get_tire_warmup_specialist() for outlap pace and cold tire performance
53. **QUALIFYING IMPROVEMENT queries**: Use get_qualifying_improvement() for Q1 to Q3 progression
54. **THEORETICAL BEST queries**: Use get_theoretical_best_lap() for best sectors combined
55. **PACE DEGRADATION queries**: Use get_race_pace_degradation() for fuel/tire pace drop
56. **RED FLAG queries**: Use get_red_flag_restart_performance() for standing restart analysis
57. **SEASON PHASE queries**: Use get_season_phase_performance() for early/mid/late season form
58. **BACK-TO-BACK queries**: Use get_back_to_back_performance() for double/triple header analysis
59. **PRESSURE queries**: Use get_championship_pressure_performance() for title fight performance
60. **PIT EXIT queries**: Use get_pit_exit_performance() for out-lap and warmup performance
61. **DEFENSIVE queries**: Use get_defensive_driving_stats() for position defense analysis
62. **TRAFFIC queries**: Use get_traffic_management() for blue flag and backmarker handling
63. **FUEL LOAD queries**: Use get_fuel_adjusted_pace() for heavy vs light fuel pace
64. **TIRE CLIFF queries**: Use get_tire_cliff_analysis() for sudden degradation spikes
65. Group independent calls in parallel, put dependent calls in sequence
66. For strategy analysis, include both stint_summary and stints_graph

### NEVER DO THIS:
- DON'T say "data not available" - USE THE RIGHT TOOL!
- DON'T give vague responses - ALWAYS call a tool to get actual data
- DON'T use get_head_to_head for "vs field" - use get_driver_vs_field instead!
- DON'T skip tool calls because you think data might not exist
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
