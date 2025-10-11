# 📚 Trading Bot PostgreSQL Deployment Guide

## 🎯 Overview
Complete guide for deploying all recommended fixes and integrations for the Trading Bot with PostgreSQL.

## 📋 Prerequisites

1. **PostgreSQL Database** (v12+)
2. **Python 3.8+**
3. **Exchange API Keys** (Binance/Bybit)
4. **Linux server** (for production deployment)

## 🚀 Quick Start

```bash
# Make deployment script executable
chmod +x deploy.sh

# Run full deployment
./deploy.sh

# Optional: Install as system service
./deploy.sh --install-service

# Optional: Setup backup cron
./deploy.sh --setup-cron
```

## 📝 Step-by-Step Manual Deployment

### Phase 1: Database Setup

```bash
# 1. Apply schema
python database/apply_schema.py

# 2. Run migrations
python database/migrations/apply_migrations.py

# 3. Verify schema
pytest tests/test_database_schema.py -v
```

### Phase 2: Exchange Integration

```bash
# 1. Test exchange adapter
pytest tests/test_exchange_adapter.py -v

# 2. Import existing positions
python core/postgres_position_importer.py
```

### Phase 3: Monitoring Setup

```bash
# 1. Start sync service (development)
python services/position_sync_service.py

# 2. Or install as systemd service (production)
sudo cp deploy/position-sync.service /etc/systemd/system/
sudo systemctl enable position-sync
sudo systemctl start position-sync
```

## 🔍 Health Checks

### Check Database Status
```sql
-- Connect to PostgreSQL
psql $DATABASE_URL

-- Check active positions
SELECT symbol, exchange, side, quantity, stop_loss_price
FROM monitoring.positions
WHERE status = 'active';

-- Check positions without stop-loss
SELECT symbol, exchange
FROM monitoring.positions
WHERE status = 'active' AND stop_loss_price IS NULL;

-- Check recent sync status
SELECT * FROM monitoring.sync_status
ORDER BY last_sync_at DESC LIMIT 5;

-- Check event log
SELECT event_type, COUNT(*)
FROM monitoring.event_log
GROUP BY event_type;
```

### Check Service Status
```bash
# If using systemd
sudo systemctl status position-sync

# Check logs
sudo journalctl -u position-sync -f

# Manual health check
python -c "
from services.position_sync_service import PositionSyncService
import asyncio
service = PositionSyncService()
health = asyncio.run(service.get_health_status())
print(health)
"
```

## 🐛 Troubleshooting

### Issue: Database Connection Failed
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check .env file
grep DATABASE_URL .env
```

### Issue: Exchange API Errors
```bash
# Test exchange connection
python test_check_positions.py

# Check API keys
grep -E "BINANCE|BYBIT" .env | head -4
```

### Issue: Positions Not Syncing
```bash
# Run manual sync
python core/postgres_position_importer.py

# Check sync logs
tail -f logs/sync.log

# Force sync with verbose output
python services/position_sync_service.py --once
```

## 🔒 Security Checklist

- [ ] `.env` file has restrictive permissions (`chmod 600 .env`)
- [ ] PostgreSQL uses SSL connection
- [ ] API keys have minimal required permissions
- [ ] Systemd service runs as non-root user
- [ ] Logs don't contain sensitive data
- [ ] Regular backups configured

## 📊 Monitoring Dashboard

Create monitoring queries:

```sql
-- Create view for dashboard
CREATE VIEW monitoring.dashboard AS
SELECT
    (SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active') as active_positions,
    (SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active' AND stop_loss_price IS NULL) as positions_without_sl,
    (SELECT SUM(unrealized_pnl) FROM monitoring.positions WHERE status = 'active') as total_unrealized_pnl,
    (SELECT MAX(last_sync_at) FROM monitoring.sync_status) as last_sync,
    (SELECT COUNT(*) FROM monitoring.event_log WHERE timestamp > NOW() - INTERVAL '1 hour') as events_last_hour;

-- Query dashboard
SELECT * FROM monitoring.dashboard;
```

## 🔄 Maintenance Tasks

### Daily
- Check for positions without stop-loss
- Review error logs
- Verify sync is running

### Weekly
- Backup database
- Review performance metrics
- Update exchange API rate limits if needed

### Monthly
- Rotate logs
- Review and optimize slow queries
- Update dependencies

## 📈 Performance Optimization

### Database Indexes
```sql
-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'monitoring'
ORDER BY idx_scan DESC;

-- Add missing indexes if needed
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_positions_composite
ON monitoring.positions(exchange, symbol, status)
WHERE status = 'active';
```

### Connection Pool Tuning
```python
# In database/repository.py
pool_config = {
    'min_size': 10,      # Increase for high load
    'max_size': 50,      # Maximum connections
    'max_queries': 50000,  # Queries before reconnect
    'max_inactive_connection_lifetime': 300  # Seconds
}
```

## 🆘 Emergency Procedures

### Stop All Positions
```python
# emergency_stop.py
import asyncio
from core.postgres_position_importer import PostgresPositionImporter

async def emergency_stop():
    importer = PostgresPositionImporter()
    await importer.connect_database()

    # Close all positions
    await importer.conn.execute("""
        UPDATE monitoring.positions
        SET status = 'closed',
            closed_at = NOW(),
            exit_reason = 'EMERGENCY STOP'
        WHERE status = 'active'
    """)

    print("⛔ All positions marked as closed")

asyncio.run(emergency_stop())
```

### Rollback Migrations
```bash
# Keep backup before migrations
pg_dump $DATABASE_URL > backup_before_migration.sql

# If rollback needed
psql $DATABASE_URL < backup_before_migration.sql
```

## 📞 Support Contacts

- **Database Issues**: DBA team
- **Exchange API**: Exchange support
- **Bot Logic**: Development team
- **Critical Alerts**: On-call engineer

## ✅ Deployment Checklist

- [ ] Database schema applied
- [ ] Migrations completed
- [ ] Tests passing
- [ ] Positions imported
- [ ] No positions without stop-loss
- [ ] Sync service running
- [ ] Monitoring configured
- [ ] Backups scheduled
- [ ] Documentation updated
- [ ] Team notified

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-10-11 | Initial PostgreSQL integration |
| 1.1.0 | 2024-10-11 | Added Bybit adapter |
| 1.2.0 | 2024-10-11 | Added position sync service |

---

*Last Updated: October 11, 2024*