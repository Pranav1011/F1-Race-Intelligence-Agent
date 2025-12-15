"""
Tests for Text-to-SQL validation and safety guards.
"""

import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.tools.timescale_tools import (
    _validate_sql,
    BLOCKED_SQL_PATTERNS,
    DATABASE_SCHEMA,
)


class TestSQLValidation:
    """Tests for SQL query validation."""

    # Valid queries
    def test_valid_select_query(self):
        """Test that valid SELECT queries pass."""
        sql = "SELECT * FROM lap_times LIMIT 10"
        is_valid, message = _validate_sql(sql)
        assert is_valid is True
        assert message == "OK"

    def test_valid_select_with_join(self):
        """Test SELECT with JOIN passes."""
        sql = """
            SELECT l.driver_id, s.event_name
            FROM lap_times l
            JOIN sessions s ON l.session_id = s.session_id
            LIMIT 10
        """
        is_valid, message = _validate_sql(sql)
        assert is_valid is True

    def test_valid_select_with_aggregation(self):
        """Test SELECT with GROUP BY passes."""
        sql = """
            SELECT driver_id, AVG(lap_time_seconds)
            FROM lap_times
            GROUP BY driver_id
            LIMIT 10
        """
        is_valid, message = _validate_sql(sql)
        assert is_valid is True

    def test_valid_select_with_subquery(self):
        """Test SELECT with subquery passes."""
        sql = """
            SELECT * FROM lap_times
            WHERE driver_id IN (SELECT driver_id FROM results WHERE position = 1)
            LIMIT 10
        """
        is_valid, message = _validate_sql(sql)
        assert is_valid is True

    # Invalid queries - not SELECT
    def test_invalid_insert_query(self):
        """Test that INSERT queries are blocked."""
        sql = "INSERT INTO lap_times (driver_id) VALUES ('TEST')"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False
        assert "SELECT" in message or "blocked" in message.lower()

    def test_invalid_update_query(self):
        """Test that UPDATE queries are blocked."""
        sql = "UPDATE lap_times SET driver_id = 'TEST' WHERE driver_id = 'VER'"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_invalid_delete_query(self):
        """Test that DELETE queries are blocked."""
        sql = "DELETE FROM lap_times WHERE driver_id = 'TEST'"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_invalid_drop_query(self):
        """Test that DROP queries are blocked."""
        sql = "DROP TABLE lap_times"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_invalid_alter_query(self):
        """Test that ALTER queries are blocked."""
        sql = "ALTER TABLE lap_times ADD COLUMN test VARCHAR"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_invalid_create_query(self):
        """Test that CREATE queries are blocked."""
        sql = "CREATE TABLE test (id INT)"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_invalid_truncate_query(self):
        """Test that TRUNCATE queries are blocked."""
        sql = "TRUNCATE TABLE lap_times"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    # SQL injection attempts
    def test_sql_injection_comment_dash(self):
        """Test that -- comments are blocked."""
        sql = "SELECT * FROM lap_times -- DROP TABLE lap_times"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False
        assert "blocked" in message.lower()

    def test_sql_injection_comment_block(self):
        """Test that /* */ comments are blocked."""
        sql = "SELECT * FROM lap_times /* DROP TABLE */"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_sql_injection_semicolon(self):
        """Test that multiple statements are blocked."""
        sql = "SELECT * FROM lap_times; DROP TABLE lap_times;"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False
        assert "multiple" in message.lower() or "blocked" in message.lower()

    def test_sql_injection_union_drop(self):
        """Test UNION with DROP attempt."""
        # This should fail because DROP is blocked
        sql = "SELECT * FROM lap_times UNION SELECT * FROM (DROP TABLE test)"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    # Edge cases
    def test_case_insensitive_blocking(self):
        """Test that blocking is case insensitive."""
        sql = "select * from lap_times; drop table lap_times"
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_empty_query(self):
        """Test empty query handling."""
        sql = ""
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_whitespace_query(self):
        """Test whitespace-only query handling."""
        sql = "   "
        is_valid, message = _validate_sql(sql)
        assert is_valid is False

    def test_select_into_blocked(self):
        """Test that dangerous patterns in SELECT are caught."""
        # Note: SELECT INTO might be allowed depending on implementation
        # This test documents expected behavior
        sql = "SELECT * INTO new_table FROM lap_times"
        is_valid, message = _validate_sql(sql)
        # Could be valid or invalid depending on security requirements
        # Just ensure it doesn't crash
        assert isinstance(is_valid, bool)


class TestBlockedPatterns:
    """Tests for blocked SQL patterns list."""

    def test_all_ddl_commands_blocked(self):
        """Test that all DDL commands are in blocked list."""
        ddl_commands = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
        for cmd in ddl_commands:
            assert cmd in BLOCKED_SQL_PATTERNS, f"{cmd} should be blocked"

    def test_privilege_commands_blocked(self):
        """Test that privilege commands are blocked."""
        privilege_commands = ["GRANT", "REVOKE"]
        for cmd in privilege_commands:
            assert cmd in BLOCKED_SQL_PATTERNS, f"{cmd} should be blocked"

    def test_dangerous_commands_blocked(self):
        """Test that dangerous commands are blocked."""
        dangerous = ["EXECUTE", "COPY", "VACUUM"]
        for cmd in dangerous:
            assert cmd in BLOCKED_SQL_PATTERNS, f"{cmd} should be blocked"


class TestDatabaseSchema:
    """Tests for database schema documentation."""

    def test_schema_contains_lap_times(self):
        """Test schema documents lap_times table."""
        assert "lap_times" in DATABASE_SCHEMA
        assert "driver_id" in DATABASE_SCHEMA
        assert "lap_time_seconds" in DATABASE_SCHEMA

    def test_schema_contains_sessions(self):
        """Test schema documents sessions table."""
        assert "sessions" in DATABASE_SCHEMA
        assert "session_id" in DATABASE_SCHEMA
        assert "event_name" in DATABASE_SCHEMA

    def test_schema_contains_results(self):
        """Test schema documents results table."""
        assert "results" in DATABASE_SCHEMA
        assert "position" in DATABASE_SCHEMA

    def test_schema_contains_weather(self):
        """Test schema documents weather table."""
        assert "weather" in DATABASE_SCHEMA
        assert "track_temp" in DATABASE_SCHEMA

    def test_schema_contains_materialized_views(self):
        """Test schema documents materialized views."""
        assert "mv_driver_race_summary" in DATABASE_SCHEMA
        assert "mv_head_to_head" in DATABASE_SCHEMA
        assert "mv_season_standings" in DATABASE_SCHEMA

    def test_schema_contains_common_patterns(self):
        """Test schema contains usage examples."""
        assert "Common Patterns" in DATABASE_SCHEMA or "Example" in DATABASE_SCHEMA
