-- Task 0.1: Pre-flight checks для schema migration
-- Проверяем текущее состояние БД перед применением изменений

\echo '==================================================================='
\echo 'Task 0.1: Pre-flight Database Checks'
\echo '==================================================================='

\echo ''
\echo '1. Количество активных позиций:'
SELECT COUNT(*) as active_positions FROM monitoring.positions WHERE status = 'active';

\echo ''
\echo '2. Размер monitoring schema:'
SELECT pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint) as monitoring_size
FROM pg_tables WHERE schemaname = 'monitoring';

\echo ''
\echo '3. Позиции с обрезанным exit_reason (ровно 100 символов):'
SELECT COUNT(*) as truncated_exit_reasons
FROM monitoring.positions
WHERE LENGTH(exit_reason) = 100;

\echo ''
\echo '4. Текущий тип поля exit_reason:'
SELECT
    column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name = 'exit_reason';

\echo ''
\echo '5. Проверка существования новых полей:'
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name IN (
    'error_details', 'retry_count', 'last_error_at',
    'last_sync_at', 'sync_status', 'exchange_order_id', 'sl_order_id'
  );

\echo ''
\echo '6. Проверка существования новых таблиц:'
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'monitoring'
  AND table_name IN ('event_log', 'schema_migrations', 'sync_status');

\echo ''
\echo '7. Размер всей БД:'
SELECT pg_size_pretty(pg_database_size(current_database())) as total_db_size;

\echo ''
\echo '==================================================================='
\echo 'Pre-flight checks completed'
\echo '==================================================================='
