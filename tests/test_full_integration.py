#!/usr/bin/env python3
"""
Full Integration Test Suite
Tests complete workflow: DB -> Exchange -> Sync -> Monitoring
"""
import asyncio
import pytest
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime

from database.repository import Repository
from core.postgres_position_importer import PostgresPositionImporter
from core.exchange_response_adapter import ExchangeResponseAdapter
from services.position_sync_service import PositionSyncService

load_dotenv()


class TestFullIntegration:
    """Test complete system integration"""

    @pytest.fixture
    async def db_conn(self):
        """Database connection fixture"""
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        await conn.execute("SET search_path TO monitoring, fas, public")
        yield conn
        await conn.close()

    @pytest.fixture
    async def repository(self):
        """Repository fixture"""
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'trading_bot'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD')
        }
        repo = Repository(db_config)
        await repo.initialize()
        yield repo
        await repo.close()

    @pytest.mark.asyncio
    async def test_database_connectivity(self, db_conn):
        """Test database connection and schema"""
        # Test connection
        version = await db_conn.fetchval("SELECT version()")
        assert version is not None

        # Test schemas exist
        schemas = await db_conn.fetch("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name IN ('fas', 'monitoring')
        """)
        assert len(schemas) == 2

        # Test critical tables exist
        tables = await db_conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_name IN ('positions', 'orders', 'event_log', 'sync_status')
        """)
        assert len(tables) >= 3  # At minimum these should exist

    @pytest.mark.asyncio
    async def test_position_import(self, db_conn):
        """Test position import functionality"""
        importer = PostgresPositionImporter()

        # Connect to DB
        await importer.connect_database()

        # Test position exists check
        exists = await importer.check_position_exists('BTC/USDT:USDT', 'test')
        assert exists is None  # Should not exist

        # Test import (without actual exchange connection)
        test_position = {
            'symbol': 'TEST/USDT:USDT',
            'exchange': 'test',
            'side': 'long',
            'contracts': 1.0,
            'markPrice': 50000,
            'entryPrice': 49500,
            'unrealizedPnl': 500,
            'stopLossPrice': 49000,
            'stopLossOrderId': 'test-sl-123'
        }

        # Import position
        success = await importer.import_position_to_db(test_position)
        assert success is True

        # Verify it was imported
        exists = await importer.check_position_exists('TEST/USDT:USDT', 'test')
        assert exists is not None

        # Clean up
        await db_conn.execute("""
            DELETE FROM monitoring.positions
            WHERE symbol = 'TEST/USDT:USDT' AND exchange = 'test'
        """)

        await importer.conn.close()

    @pytest.mark.asyncio
    async def test_exchange_adapter(self):
        """Test exchange response adapter"""
        # Test Bybit response normalization
        bybit_response = {
            'id': 'test123',
            'info': {
                'orderId': 'test123',
                'orderStatus': 'Filled',
                'side': 'Buy',
                'qty': '1.5',
                'cumExecQty': '1.5',
                'avgPrice': '45000'
            }
        }

        order = ExchangeResponseAdapter.normalize_order(bybit_response, 'bybit')
        assert order.id == 'test123'
        assert order.status == 'closed'
        assert order.side == 'buy'
        assert order.amount == 1.5
        assert order.filled == 1.5
        assert ExchangeResponseAdapter.is_order_filled(order) is True

    @pytest.mark.asyncio
    async def test_event_logging(self, db_conn):
        """Test event logging functionality"""
        # Create test event
        await db_conn.execute("""
            INSERT INTO monitoring.event_log (
                event_type, event_data, symbol, exchange, severity
            ) VALUES ($1, $2, $3, $4, $5)
        """,
            'TEST_EVENT',
            '{"test": "data"}',
            'BTC/USDT',
            'binance',
            'INFO'
        )

        # Verify event was logged
        events = await db_conn.fetch("""
            SELECT * FROM monitoring.event_log
            WHERE event_type = 'TEST_EVENT'
        """)

        assert len(events) == 1
        assert events[0]['symbol'] == 'BTC/USDT'

        # Clean up
        await db_conn.execute("""
            DELETE FROM monitoring.event_log WHERE event_type = 'TEST_EVENT'
        """)

    @pytest.mark.asyncio
    async def test_sync_service_health(self):
        """Test sync service health check"""
        service = PositionSyncService(sync_interval=60)

        # Get health status
        health = await service.get_health_status()

        assert health['status'] in ['healthy', 'unhealthy']
        assert 'active_positions' in health
        assert health['sync_count'] == 0  # Haven't run yet

    @pytest.mark.asyncio
    async def test_repository_operations(self, repository):
        """Test repository CRUD operations"""
        # Create position
        position_data = {
            'signal_id': 999,
            'symbol': 'PYTEST/USDT',
            'exchange': 'test',
            'side': 'long',
            'quantity': 2.5,
            'entry_price': 100.0,
            'status': 'active'
        }

        position_id = await repository.create_position(position_data)
        assert position_id is not None

        # Update position
        success = await repository.update_position(
            position_id,
            current_price=105.0,
            unrealized_pnl=12.5
        )
        assert success is True

        # Get position
        position = await repository.get_position(position_id)
        assert position is not None
        assert position['symbol'] == 'PYTEST/USDT'
        assert position['current_price'] == 105.0

        # Delete test data
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        await conn.execute("""
            DELETE FROM monitoring.positions WHERE id = $1
        """, position_id)
        await conn.close()

    @pytest.mark.asyncio
    async def test_migration_tracking(self, db_conn):
        """Test migration tracking system"""
        # Check migrations table exists
        table = await db_conn.fetchrow("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_name = 'schema_migrations'
        """)

        if table:
            # Check if critical migrations were applied
            migrations = await db_conn.fetch("""
                SELECT migration_name FROM monitoring.schema_migrations
                WHERE migration_name IN (
                    '001_expand_exit_reason',
                    '002_add_event_log',
                    '003_add_sync_tracking'
                )
            """)

            # At least exit_reason migration should be applied
            migration_names = [m['migration_name'] for m in migrations]
            assert '001_expand_exit_reason' in migration_names

    @pytest.mark.asyncio
    async def test_positions_without_sl_detection(self, db_conn):
        """Test detection of positions without stop-loss"""
        # Create test position without SL
        await db_conn.execute("""
            INSERT INTO monitoring.positions (
                symbol, exchange, side, quantity, entry_price, status
            ) VALUES ('NOSL/TEST', 'test', 'long', 1.0, 100.0, 'active')
        """)

        # Query positions without SL
        no_sl = await db_conn.fetch("""
            SELECT symbol FROM monitoring.positions
            WHERE status = 'active' AND stop_loss_price IS NULL
        """)

        assert len(no_sl) > 0
        assert any(pos['symbol'] == 'NOSL/TEST' for pos in no_sl)

        # Clean up
        await db_conn.execute("""
            DELETE FROM monitoring.positions
            WHERE symbol = 'NOSL/TEST'
        """)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])