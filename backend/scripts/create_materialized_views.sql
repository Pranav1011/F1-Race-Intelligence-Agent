-- F1 Race Intelligence Agent - Materialized Views
-- Pre-computed aggregations for fast query performance
-- Run with: docker compose exec timescaledb psql -U f1 -d f1_telemetry -f /app/scripts/create_materialized_views.sql

-- ============================================================
-- 1. DRIVER RACE SUMMARY
-- Per-driver, per-race aggregated statistics
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_driver_race_summary CASCADE;

CREATE MATERIALIZED VIEW mv_driver_race_summary AS
SELECT
    l.session_id,
    s.year,
    s.round_number,
    s.event_name,
    s.circuit,
    l.driver_id,
    l.team,
    -- Lap statistics
    COUNT(*) as total_laps,
    MIN(l.lap_time_seconds) FILTER (WHERE l.lap_time_seconds > 60) as fastest_lap,
    AVG(l.lap_time_seconds) FILTER (WHERE l.lap_time_seconds > 60 AND l.lap_time_seconds < 200) as avg_lap_time,
    STDDEV(l.lap_time_seconds) FILTER (WHERE l.lap_time_seconds > 60 AND l.lap_time_seconds < 200) as consistency,
    -- Sector bests
    MIN(l.sector_1_seconds) as best_s1,
    MIN(l.sector_2_seconds) as best_s2,
    MIN(l.sector_3_seconds) as best_s3,
    AVG(l.sector_1_seconds) as avg_s1,
    AVG(l.sector_2_seconds) as avg_s2,
    AVG(l.sector_3_seconds) as avg_s3,
    -- Stint info
    MAX(l.stint) as total_stints,
    -- Position
    MIN(l.position) as best_position,
    MAX(l.position) as worst_position
FROM lap_times l
JOIN sessions s ON l.session_id = s.session_id
WHERE s.session_type = 'R'  -- Race sessions only
GROUP BY l.session_id, s.year, s.round_number, s.event_name, s.circuit, l.driver_id, l.team;

CREATE UNIQUE INDEX idx_mv_driver_race_summary
ON mv_driver_race_summary(session_id, driver_id);

CREATE INDEX idx_mv_driver_race_year ON mv_driver_race_summary(year);
CREATE INDEX idx_mv_driver_race_driver ON mv_driver_race_summary(driver_id);


-- ============================================================
-- 2. RACE STATISTICS
-- Per-race summary with winner, fastest lap holder, etc.
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_race_statistics CASCADE;

CREATE MATERIALIZED VIEW mv_race_statistics AS
WITH race_winner AS (
    SELECT session_id, driver_id as winner, team as winning_team
    FROM results
    WHERE position = 1
),
fastest_lap AS (
    SELECT DISTINCT ON (session_id)
        session_id,
        driver_id as fastest_lap_driver,
        MIN(lap_time_seconds) FILTER (WHERE lap_time_seconds > 60) as fastest_lap_time
    FROM lap_times
    GROUP BY session_id, driver_id
    ORDER BY session_id, MIN(lap_time_seconds) FILTER (WHERE lap_time_seconds > 60)
)
SELECT
    s.session_id,
    s.year,
    s.round_number,
    s.event_name,
    s.circuit,
    s.session_date,
    rw.winner,
    rw.winning_team,
    fl.fastest_lap_driver,
    fl.fastest_lap_time,
    COUNT(DISTINCT l.driver_id) as drivers_finished,
    AVG(l.lap_time_seconds) FILTER (WHERE l.lap_time_seconds > 60 AND l.lap_time_seconds < 200) as avg_race_pace,
    MAX(l.lap_number) as total_race_laps
FROM sessions s
LEFT JOIN race_winner rw ON s.session_id = rw.session_id
LEFT JOIN fastest_lap fl ON s.session_id = fl.session_id
LEFT JOIN lap_times l ON s.session_id = l.session_id
WHERE s.session_type = 'R'
GROUP BY s.session_id, s.year, s.round_number, s.event_name, s.circuit, s.session_date,
         rw.winner, rw.winning_team, fl.fastest_lap_driver, fl.fastest_lap_time;

CREATE UNIQUE INDEX idx_mv_race_statistics ON mv_race_statistics(session_id);
CREATE INDEX idx_mv_race_stats_year ON mv_race_statistics(year);


-- ============================================================
-- 3. HEAD-TO-HEAD STATISTICS
-- Pre-computed driver comparisons for common matchups
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_head_to_head CASCADE;

CREATE MATERIALIZED VIEW mv_head_to_head AS
WITH driver_pairs AS (
    SELECT DISTINCT
        l1.session_id,
        LEAST(l1.driver_id, l2.driver_id) as driver_1,
        GREATEST(l1.driver_id, l2.driver_id) as driver_2
    FROM lap_times l1
    JOIN lap_times l2 ON l1.session_id = l2.session_id AND l1.driver_id < l2.driver_id
),
driver_stats AS (
    SELECT
        session_id,
        driver_id,
        AVG(lap_time_seconds) FILTER (WHERE lap_time_seconds > 60 AND lap_time_seconds < 200) as avg_pace,
        MIN(lap_time_seconds) FILTER (WHERE lap_time_seconds > 60) as fastest_lap,
        MIN(sector_1_seconds) as best_s1,
        MIN(sector_2_seconds) as best_s2,
        MIN(sector_3_seconds) as best_s3,
        COUNT(*) as laps
    FROM lap_times
    GROUP BY session_id, driver_id
)
SELECT
    dp.session_id,
    s.year,
    s.event_name,
    dp.driver_1,
    dp.driver_2,
    ds1.avg_pace as driver_1_pace,
    ds2.avg_pace as driver_2_pace,
    ds1.avg_pace - ds2.avg_pace as pace_delta,  -- Negative = driver_1 faster
    ds1.fastest_lap as driver_1_fastest,
    ds2.fastest_lap as driver_2_fastest,
    ds1.fastest_lap - ds2.fastest_lap as fastest_delta,
    ds1.best_s1 - ds2.best_s1 as s1_delta,
    ds1.best_s2 - ds2.best_s2 as s2_delta,
    ds1.best_s3 - ds2.best_s3 as s3_delta,
    LEAST(ds1.laps, ds2.laps) as comparable_laps
FROM driver_pairs dp
JOIN sessions s ON dp.session_id = s.session_id
JOIN driver_stats ds1 ON dp.session_id = ds1.session_id AND dp.driver_1 = ds1.driver_id
JOIN driver_stats ds2 ON dp.session_id = ds2.session_id AND dp.driver_2 = ds2.driver_id
WHERE s.session_type = 'R';

CREATE UNIQUE INDEX idx_mv_h2h ON mv_head_to_head(session_id, driver_1, driver_2);
CREATE INDEX idx_mv_h2h_drivers ON mv_head_to_head(driver_1, driver_2);
CREATE INDEX idx_mv_h2h_year ON mv_head_to_head(year);


-- ============================================================
-- 4. STINT SUMMARY
-- Pre-computed stint statistics per driver per race
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_stint_summary CASCADE;

CREATE MATERIALIZED VIEW mv_stint_summary AS
SELECT
    l.session_id,
    s.year,
    s.event_name,
    l.driver_id,
    l.stint,
    l.compound,
    MIN(l.lap_number) as start_lap,
    MAX(l.lap_number) as end_lap,
    COUNT(*) as stint_laps,
    AVG(l.lap_time_seconds) FILTER (WHERE l.lap_time_seconds > 60 AND l.lap_time_seconds < 200) as avg_pace,
    MIN(l.lap_time_seconds) FILTER (WHERE l.lap_time_seconds > 60) as best_lap,
    MAX(l.tire_life) as max_tire_age,
    -- Calculate degradation (simplified: last 5 laps avg - first 5 laps avg)
    (
        SELECT AVG(lap_time_seconds)
        FROM lap_times l2
        WHERE l2.session_id = l.session_id
          AND l2.driver_id = l.driver_id
          AND l2.stint = l.stint
          AND l2.lap_number > (MAX(l.lap_number) - 5)
          AND l2.lap_time_seconds > 60 AND l2.lap_time_seconds < 200
    ) - (
        SELECT AVG(lap_time_seconds)
        FROM lap_times l3
        WHERE l3.session_id = l.session_id
          AND l3.driver_id = l.driver_id
          AND l3.stint = l.stint
          AND l3.lap_number < (MIN(l.lap_number) + 5)
          AND l3.lap_time_seconds > 60 AND l3.lap_time_seconds < 200
    ) as estimated_degradation
FROM lap_times l
JOIN sessions s ON l.session_id = s.session_id
WHERE s.session_type = 'R' AND l.stint IS NOT NULL
GROUP BY l.session_id, s.year, s.event_name, l.driver_id, l.stint, l.compound;

CREATE UNIQUE INDEX idx_mv_stint ON mv_stint_summary(session_id, driver_id, stint);
CREATE INDEX idx_mv_stint_driver ON mv_stint_summary(driver_id);
CREATE INDEX idx_mv_stint_compound ON mv_stint_summary(compound);


-- ============================================================
-- 5. SEASON STANDINGS (Calculated from results)
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_season_standings CASCADE;

CREATE MATERIALIZED VIEW mv_season_standings AS
SELECT
    s.year,
    r.driver_id,
    r.driver_name,
    r.team,
    COUNT(*) as races,
    SUM(r.points) as total_points,
    COUNT(*) FILTER (WHERE r.position = 1) as wins,
    COUNT(*) FILTER (WHERE r.position <= 3) as podiums,
    COUNT(*) FILTER (WHERE r.position <= 10) as points_finishes,
    AVG(r.position) as avg_position,
    MIN(r.position) as best_finish
FROM results r
JOIN sessions s ON r.session_id = s.session_id
WHERE s.session_type = 'R'
GROUP BY s.year, r.driver_id, r.driver_name, r.team;

CREATE UNIQUE INDEX idx_mv_standings ON mv_season_standings(year, driver_id);
CREATE INDEX idx_mv_standings_year ON mv_season_standings(year);


-- ============================================================
-- 6. LAP TIME PERCENTILES (for outlier detection)
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_lap_percentiles CASCADE;

CREATE MATERIALIZED VIEW mv_lap_percentiles AS
SELECT
    session_id,
    driver_id,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY lap_time_seconds)
        FILTER (WHERE lap_time_seconds > 60 AND lap_time_seconds < 200) as p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY lap_time_seconds)
        FILTER (WHERE lap_time_seconds > 60 AND lap_time_seconds < 200) as median,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY lap_time_seconds)
        FILTER (WHERE lap_time_seconds > 60 AND lap_time_seconds < 200) as p75,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY lap_time_seconds)
        FILTER (WHERE lap_time_seconds > 60 AND lap_time_seconds < 200) as p90
FROM lap_times
GROUP BY session_id, driver_id;

CREATE UNIQUE INDEX idx_mv_percentiles ON mv_lap_percentiles(session_id, driver_id);


-- ============================================================
-- ADDITIONAL INDEXES ON BASE TABLES
-- ============================================================

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_lap_times_composite
ON lap_times(session_id, driver_id, lap_number);

-- Index for filtering by compound
CREATE INDEX IF NOT EXISTS idx_lap_times_compound_stint
ON lap_times(session_id, compound, stint);

-- Index for year-based queries via session
CREATE INDEX IF NOT EXISTS idx_sessions_year_type
ON sessions(year, session_type);

-- Index for results queries
CREATE INDEX IF NOT EXISTS idx_results_composite
ON results(session_id, position);


-- ============================================================
-- REFRESH FUNCTION (call after new data is loaded)
-- ============================================================
CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_driver_race_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_race_statistics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_head_to_head;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_stint_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_season_standings;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_lap_percentiles;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- INITIAL REFRESH
-- ============================================================
SELECT 'Creating materialized views... This may take a few minutes.' as status;

-- Views are created with data on first creation, no refresh needed
SELECT 'Materialized views created successfully!' as status;

-- Show view stats
SELECT
    schemaname,
    matviewname,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || matviewname)) as size
FROM pg_matviews
WHERE schemaname = 'public'
ORDER BY matviewname;
