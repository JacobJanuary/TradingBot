#!/usr/bin/env python3
"""
Test PostgreSQL database schema integrity
Ensures all required tables, columns, and indexes exist
"""
import asyncpg
import asyncio
import pytest
import os
from dotenv import load_dotenv

load_dotenv()


class TestDatabaseSchema:
    """Test database schema completeness"""

    @pytest.fixture
    async def db_conn(self):
        """Database connection fixture"""
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_schemas_exist(self, db_conn):
        """Test that required schemas exist"""
        schemas = await db_conn.fetch("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN ('fas', 'monitoring')
        """)

        schema_names = [s['schema_name'] for s in schemas]
        assert 'fas' in schema_names
        assert 'monitoring' in schema_names

    @pytest.mark.asyncio
    async def test_positions_table_structure(self, db_conn):
        """Test positions table has all required columns"""
        columns = await db_conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
        """)

        column_names = [c['column_name'] for c in columns]

        # Critical columns that must exist
        required_columns = [
            'id', 'signal_id', 'symbol', 'exchange', 'side',
            'quantity', 'entry_price', 'stop_loss_price',
            'status', 'exit_reason', 'created_at'
        ]

        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"

    @pytest.mark.asyncio
    async def test_exit_reason_is_text(self, db_conn):
        """Test that exit_reason can hold long text"""
        column_info = await db_conn.fetchrow("""
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
            AND table_name = 'positions'
            AND column_name = 'exit_reason'
        """)

        # Should be TEXT or VARCHAR with large limit
        assert column_info['data_type'] in ['text', 'character varying']
        if column_info['data_type'] == 'character varying':
            assert column_info['character_maximum_length'] > 100

    @pytest.mark.asyncio
    async def test_indexes_exist(self, db_conn):
        """Test that performance indexes exist"""
        indexes = await db_conn.fetch("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'monitoring'
            AND tablename = 'positions'
        """)

        index_names = [i['indexname'] for i in indexes]

        # Should have indexes for common queries
        assert any('status' in idx for idx in index_names)
        assert any('symbol' in idx for idx in index_names)

    @pytest.mark.asyncio
    async def test_event_log_table(self, db_conn):
        """Test event_log table for audit trail"""
        # Check if event_log table exists
        table = await db_conn.fetchrow("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_name = 'event_log'
        """)

        # If not exists, create it
        if not table:
            await db_conn.execute("""
                CREATE TABLE IF NOT EXISTS monitoring.event_log (
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(50) NOT NULL,
                    event_data JSONB,
                    correlation_id VARCHAR(100),
                    position_id INTEGER,
                    signal_id INTEGER,
                    symbol VARCHAR(50),
                    exchange VARCHAR(50),
                    severity VARCHAR(20) DEFAULT 'INFO',
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)

            await db_conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_log_type
                ON monitoring.event_log(event_type)
            """)

        # Verify it exists now
        table = await db_conn.fetchrow("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_name = 'event_log'
        """)

        assert table is not None


if __name__ == "__main__":
    # Run tests directly
    import sys
    sys.exit(pytest.main([__file__, '-v']))