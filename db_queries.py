"""
Prepared queries для мониторинга
"""

# Позиции созданные за период
GET_POSITIONS_BY_TIMERANGE = """
SELECT
    id, symbol, side, entry_price, stop_loss_price,
    status, created_at, opened_at, closed_at,
    realized_pnl, unrealized_pnl
FROM monitoring.positions
WHERE created_at BETWEEN $1 AND $2
ORDER BY created_at DESC
"""

# События за период
GET_EVENTS_BY_TIMERANGE = """
SELECT
    event_type, symbol, event_data, created_at
FROM monitoring.events
WHERE created_at BETWEEN $1 AND $2
ORDER BY created_at ASC
"""

# Текущие активные позиции
GET_ACTIVE_POSITIONS = """
SELECT
    id, symbol, side, entry_price, current_price,
    stop_loss_price, status,
    EXTRACT(EPOCH FROM (NOW() - opened_at))/3600 as age_hours,
    unrealized_pnl,
    CASE WHEN entry_price > 0 THEN (unrealized_pnl / (entry_price * quantity) * 100) ELSE 0 END as unrealized_pnl_percent
FROM monitoring.positions
WHERE status IN ('active', 'pending_entry', 'entry_placed', 'pending_sl')
ORDER BY created_at DESC
"""

# Trailing stop состояния
GET_TRAILING_STATES = """
SELECT
    position_id, state, activation_price,
    highest_price, current_stop_price,
    last_update, updates_count
FROM monitoring.trailing_stop_state
WHERE position_id = ANY($1::bigint[])
"""

# Статистика за период
GET_PERIOD_STATISTICS = """
SELECT
    COUNT(*) FILTER (WHERE status = 'active') as active_count,
    COUNT(*) FILTER (WHERE status = 'closed') as closed_count,
    COUNT(*) FILTER (WHERE status LIKE 'pending%') as pending_count,
    COALESCE(SUM(realized_pnl), 0) as total_realized_pnl,
    COALESCE(SUM(unrealized_pnl), 0) as total_unrealized_pnl,
    AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
    AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
    CASE
        WHEN COUNT(*) FILTER (WHERE status = 'closed') > 0
        THEN COUNT(*) FILTER (WHERE realized_pnl > 0) * 100.0 / COUNT(*) FILTER (WHERE status = 'closed')
        ELSE 0
    END as win_rate
FROM monitoring.positions
WHERE created_at >= $1
"""

# Недавние ошибки
GET_RECENT_ERRORS = """
SELECT
    event_type, symbol, event_data, created_at
FROM monitoring.events
WHERE event_type IN ('error', 'position_rollback', 'emergency_close')
    AND created_at >= $1
ORDER BY created_at DESC
"""

# Position creation timeline
GET_POSITION_TIMELINE = """
SELECT
    p.id, p.symbol, p.status, p.created_at as position_created_at,
    e.event_type, e.event_data, e.created_at as event_created_at
FROM monitoring.positions p
LEFT JOIN monitoring.events e ON e.symbol = p.symbol
WHERE p.id = $1
    AND e.created_at BETWEEN p.created_at - INTERVAL '1 minute'
                         AND p.created_at + INTERVAL '5 minutes'
ORDER BY e.created_at ASC
"""

# Все позиции (для snapshot)
GET_ALL_POSITIONS = """
SELECT
    id, symbol, side, entry_price, stop_loss_price,
    status, created_at, opened_at, closed_at,
    realized_pnl, unrealized_pnl, current_price,
    quantity, exchange_order_id, has_stop_loss
FROM monitoring.positions
ORDER BY created_at DESC
LIMIT 1000
"""

# Последние N событий
GET_RECENT_EVENTS = """
SELECT
    id, event_type, symbol, event_data, created_at
FROM monitoring.events
ORDER BY created_at DESC
LIMIT $1
"""
