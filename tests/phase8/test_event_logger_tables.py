"""
Test Phase 8: EventLogger Database Tables
Purpose: Verify database tables for EventLogger are created correctly
"""
import pytest
import asyncpg


@pytest.mark.asyncio
async def test_monitoring_events_table_exists():
    """Verify monitoring.events table exists"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    result = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'events'
    """)

    assert result == 1, "monitoring.events table does not exist"
    await conn.close()
    print("\n✅ monitoring.events table exists")


@pytest.mark.asyncio
async def test_monitoring_events_columns():
    """Verify monitoring.events has all required columns"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    columns = await conn.fetch("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'monitoring' AND table_name = 'events'
        ORDER BY ordinal_position
    """)

    column_names = [c['column_name'] for c in columns]

    required = ['id', 'event_type', 'event_data', 'correlation_id',
                'position_id', 'order_id', 'symbol', 'exchange',
                'severity', 'error_message', 'stack_trace', 'created_at']

    for col in required:
        assert col in column_names, f"Missing column: {col}"

    await conn.close()
    print(f"\n✅ monitoring.events has all {len(required)} required columns")


@pytest.mark.asyncio
async def test_monitoring_events_indexes():
    """Verify monitoring.events has all required indexes"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    indexes = await conn.fetch("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'monitoring' AND tablename = 'events'
    """)

    index_names = [i['indexname'] for i in indexes]

    required = ['idx_events_type', 'idx_events_correlation',
                'idx_events_position', 'idx_events_created']

    for idx in required:
        assert idx in index_names, f"Missing index: {idx}"

    await conn.close()
    print(f"\n✅ monitoring.events has {len(index_names)} indexes (required: {len(required)})")


@pytest.mark.asyncio
async def test_monitoring_transaction_log_exists():
    """Verify monitoring.transaction_log table exists"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    result = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'transaction_log'
    """)

    assert result == 1, "monitoring.transaction_log table does not exist"
    await conn.close()
    print("\n✅ monitoring.transaction_log table exists")


@pytest.mark.asyncio
async def test_monitoring_event_performance_metrics_exists():
    """Verify monitoring.event_performance_metrics table exists"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    result = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'event_performance_metrics'
    """)

    assert result == 1, "monitoring.event_performance_metrics table does not exist"
    await conn.close()
    print("\n✅ monitoring.event_performance_metrics table exists")


@pytest.mark.asyncio
async def test_old_performance_metrics_not_affected():
    """Verify old monitoring.performance_metrics was not dropped"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    # Check table exists
    table_exists = await conn.fetchval("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics'
    """)
    assert table_exists == 1, "Original performance_metrics table was dropped!"

    # Check data not lost
    record_count = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.performance_metrics
    """)
    assert record_count >= 32, f"Data lost! Expected >=32 records, got {record_count}"

    # Check structure is old structure (not EventLogger structure)
    columns = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'monitoring' AND table_name = 'performance_metrics'
    """)
    column_names = [c['column_name'] for c in columns]

    # Should have OLD structure
    assert 'period' in column_names, "Old structure missing - 'period' column not found"
    assert 'total_trades' in column_names, "Old structure missing - 'total_trades' column not found"

    # Should NOT have EventLogger structure
    assert 'metric_name' not in column_names, "EventLogger structure found in wrong table!"

    await conn.close()
    print(f"\n✅ Original monitoring.performance_metrics intact ({record_count} records)")


@pytest.mark.asyncio
async def test_events_table_can_insert():
    """Verify we can insert into monitoring.events"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    # Insert test event
    await conn.execute("""
        INSERT INTO monitoring.events (
            event_type, event_data, symbol, exchange, severity
        ) VALUES (
            'test_event', '{"test": true}'::jsonb, 'TESTUSDT', 'test_exchange', 'INFO'
        )
    """)

    # Verify it was inserted
    result = await conn.fetchval("""
        SELECT COUNT(*) FROM monitoring.events
        WHERE event_type = 'test_event' AND symbol = 'TESTUSDT'
    """)

    assert result >= 1, "Test event was not inserted"

    # Cleanup
    await conn.execute("""
        DELETE FROM monitoring.events
        WHERE event_type = 'test_event' AND symbol = 'TESTUSDT'
    """)

    await conn.close()
    print("\n✅ Can insert into monitoring.events")


@pytest.mark.asyncio
async def test_events_table_jsonb_queries():
    """Verify JSONB queries work on event_data"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    # Insert test event with complex JSONB
    await conn.execute("""
        INSERT INTO monitoring.events (
            event_type, event_data, severity
        ) VALUES (
            'jsonb_test',
            '{"stop_price": 50000.5, "method": "position_attached", "trigger_by": "LastPrice"}'::jsonb,
            'INFO'
        )
    """)

    # Test JSONB query
    result = await conn.fetchval("""
        SELECT event_data->>'stop_price'
        FROM monitoring.events
        WHERE event_type = 'jsonb_test'
        LIMIT 1
    """)

    assert result == '50000.5', f"JSONB query failed, got: {result}"

    # Cleanup
    await conn.execute("""
        DELETE FROM monitoring.events WHERE event_type = 'jsonb_test'
    """)

    await conn.close()
    print("\n✅ JSONB queries work on event_data")


@pytest.mark.asyncio
async def test_events_indexes_used():
    """Verify indexes are actually used in queries"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    # Test query plan uses index
    plan = await conn.fetch("""
        EXPLAIN SELECT * FROM monitoring.events
        WHERE event_type = 'test' LIMIT 1
    """)

    plan_text = '\n'.join([row['QUERY PLAN'] for row in plan])

    # Should use index scan
    assert 'idx_events_type' in plan_text or 'Index Scan' in plan_text, \
        f"Index not used in query plan: {plan_text}"

    await conn.close()
    print("\n✅ Indexes are used in queries")


@pytest.mark.asyncio
async def test_all_tables_summary():
    """Summary test: verify all 4 monitoring tables exist"""
    conn = await asyncpg.connect(
        user='elcrypto',
        database='fox_crypto',
        host='localhost',
        port=5433
    )

    tables = await conn.fetch("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'monitoring'
          AND table_name IN ('events', 'transaction_log', 'event_performance_metrics', 'performance_metrics')
        ORDER BY table_name
    """)

    table_names = [t['table_name'] for t in tables]

    assert len(table_names) == 4, f"Expected 4 tables, found {len(table_names)}: {table_names}"
    assert 'events' in table_names
    assert 'transaction_log' in table_names
    assert 'event_performance_metrics' in table_names
    assert 'performance_metrics' in table_names

    await conn.close()
    print(f"\n✅ All 4 monitoring tables exist: {table_names}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
