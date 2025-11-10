#!/bin/bash
#
# ТЕСТ #1: Простая проверка состояния позиций через psql
#

echo "=============================================================================="
echo "ТЕСТ #1: АНАЛИЗ СОСТОЯНИЯ ПОДПИСОК В БД (через psql)"
echo "=============================================================================="
echo "Дата: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# DB params from .env
source .env 2>/dev/null || true

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-tradingbot_db}
DB_USER=${DB_USER:-tradingbot}

echo "БД: $DB_HOST:$DB_PORT/$DB_NAME"
echo "=============================================================================="
echo ""

# Test connection
if ! PGPASSWORD="" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
    echo "❌ Не удалось подключиться к БД"
    exit 1
fi

echo "✅ Подключение к PostgreSQL успешно"
echo ""

# 1. Total open positions
echo "📊 Всего открытых позиций:"
PGPASSWORD="" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM positions WHERE status = 'open';"
echo ""

# 2. Positions with updates in last 5 minutes
echo "✅ Позиции с обновлениями за последние 5 минут:"
PGPASSWORD="" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM positions WHERE status = 'open' AND updated_at > NOW() - INTERVAL '5 minutes';"
echo ""

# 3. Stale positions (no updates >5 min)
echo "⚠️  Позиции БЕЗ обновлений >5 минут:"
STALE_COUNT=$(PGPASSWORD="" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM positions WHERE status = 'open' AND (updated_at < NOW() - INTERVAL '5 minutes' OR updated_at IS NULL OR current_price IS NULL);" | tr -d ' ')
echo "$STALE_COUNT"
echo ""

if [ "$STALE_COUNT" -gt 0 ]; then
    echo "ДЕТАЛИ ПРОБЛЕМНЫХ ПОЗИЦИЙ:"
    echo "------------------------------------------------------------------------------"
    PGPASSWORD="" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
        "SELECT 
            symbol,
            ROUND(current_price::numeric, 6) as price,
            TO_CHAR(opened_at, 'HH24:MI') as opened,
            CASE 
                WHEN updated_at IS NULL THEN 'НИКОГДА'
                ELSE ROUND(EXTRACT(EPOCH FROM (NOW() - updated_at))/60) || ' мин'
            END as last_update,
            CASE
                WHEN EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 < 1 
                    THEN ROUND(EXTRACT(EPOCH FROM (NOW() - opened_at))/60) || 'm'
                ELSE ROUND(EXTRACT(EPOCH FROM (NOW() - opened_at))/3600, 1) || 'h'
            END as age
        FROM positions
        WHERE status = 'open'
        AND (updated_at < NOW() - INTERVAL '5 minutes' OR updated_at IS NULL OR current_price IS NULL)
        ORDER BY updated_at ASC NULLS FIRST
        LIMIT 20;"
    echo ""
fi

# 4. Summary
echo "=============================================================================="
echo "ИТОГО:"
echo "=============================================================================="
PGPASSWORD="" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
    "WITH stats AS (
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN updated_at > NOW() - INTERVAL '5 minutes' THEN 1 ELSE 0 END) as healthy,
            SUM(CASE WHEN updated_at <= NOW() - INTERVAL '5 minutes' OR updated_at IS NULL THEN 1 ELSE 0 END) as stale
        FROM positions
        WHERE status = 'open'
    )
    SELECT 
        total as \"Всего позиций\",
        healthy as \"Здоровые (<5 мин)\",
        stale as \"Мертвые (>5 мин)\",
        ROUND((stale::numeric / NULLIF(total, 0) * 100), 1) as \"% мертвых\"
    FROM stats;"

echo "=============================================================================="
