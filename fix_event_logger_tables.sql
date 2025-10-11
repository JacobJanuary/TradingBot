-- Удалить старые таблицы если существуют
DROP TABLE IF EXISTS monitoring.performance_metrics CASCADE;
DROP TABLE IF EXISTS monitoring.transaction_log CASCADE;
DROP TABLE IF EXISTS monitoring.events CASCADE;

DROP TABLE IF EXISTS performance_metrics CASCADE;
DROP TABLE IF EXISTS transaction_log CASCADE;
DROP TABLE IF EXISTS events CASCADE;

-- Можно запустить бота, он создаст таблицы с правильной структурой