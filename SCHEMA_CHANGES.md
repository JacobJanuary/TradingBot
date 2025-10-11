# 📋 Schema Changes Summary

## 🎯 Why These Changes?

### Problem 1: **Error Messages Truncated**
- **Current**: `exit_reason VARCHAR(100)` - cuts off error messages
- **Example**: "Failed to place stop-loss after 3 attempts: bybit {'retCode':10003,'retMsg':'API key is invalid....'" → Cut at 100 chars
- **Solution**: Change to `TEXT` type for unlimited length

### Problem 2: **No Audit Trail**
- **Current**: No event logging
- **Solution**: Add `event_log` table for complete audit trail

### Problem 3: **No Sync Tracking**
- **Current**: Can't tell when position was last synced
- **Solution**: Add sync tracking fields and status table

### Problem 4: **Missing Order References**
- **Current**: No link between positions and exchange orders
- **Solution**: Add `exchange_order_id` and `sl_order_id` fields

## 📊 Changes to `monitoring.positions` Table

| Field | Current | New | Reason |
|-------|---------|-----|---------|
| exit_reason | VARCHAR(100) | TEXT | Full error messages |
| error_details | - | JSONB | Structured error data |
| retry_count | - | INTEGER | Track retry attempts |
| last_error_at | - | TIMESTAMP | Error timestamp |
| last_sync_at | - | TIMESTAMP | Sync tracking |
| sync_status | - | VARCHAR(50) | Sync state |
| exchange_order_id | - | VARCHAR(100) | Order reference |
| sl_order_id | - | VARCHAR(100) | Stop-loss reference |

## 📋 New Tables

### 1. `monitoring.event_log`
Track all important events for debugging and audit:
- Position created/updated/closed
- Stop-loss placed/triggered
- Sync performed
- Errors occurred

### 2. `monitoring.schema_migrations`
Track which database migrations have been applied:
- Prevents running same migration twice
- Allows rollback if needed

### 3. `monitoring.sync_status`
Monitor synchronization health:
- Last sync time per exchange
- Number of positions synced
- Discrepancies found and fixed

## ✅ Safety Guarantees

1. **NO DATA LOSS**
   - All changes are ADDITIVE only
   - No columns removed
   - No data deleted

2. **IDEMPOTENT MIGRATIONS**
   - Can run multiple times safely
   - Each migration tracked
   - Won't apply same change twice

3. **ROLLBACK POSSIBLE**
   - Backup created before changes
   - Can restore in ~2 minutes
   - Code and DB can be reverted

4. **NO DOWNTIME**
   - Changes can be applied while system runs
   - Backward compatible
   - Existing code continues to work

## 📐 Size Impact

```sql
-- Check current data size:
SELECT
    pg_size_pretty(pg_database_size('trading_bot')) as total_db_size,
    pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint) as monitoring_size
FROM pg_tables
WHERE schemaname = 'monitoring';
```

Expected impact:
- Additional storage: ~10-20% of current positions table
- Backup size: ~20% of monitoring schema size (compressed)
- Migration time: < 1 second per 1000 positions

## 🚀 How to Apply

### Option 1: Automated (Recommended)
```bash
./deploy.sh
# Shows changes, asks confirmation, creates backup, applies changes
```

### Option 2: Manual
```bash
# 1. Check what will change
python database/check_schema_changes.py

# 2. Backup monitoring schema only
./database/backup_monitoring.sh

# 3. Apply migrations
python database/migrations/apply_migrations.py

# 4. Verify
psql $DATABASE_URL -c "SELECT * FROM monitoring.schema_migrations;"
```

## 🔄 Rollback Plan

If anything goes wrong:

```bash
# 1. Stop services
systemctl stop position-sync

# 2. Restore monitoring schema from backup
pg_restore -d $DATABASE_URL --clean --schema=monitoring backups/*/monitoring_*.backup

# 3. Restart services
systemctl start position-sync
```

## 📊 Verification After Changes

```sql
-- Check migration was applied:
SELECT * FROM monitoring.schema_migrations;

-- Check exit_reason is TEXT:
SELECT data_type
FROM information_schema.columns
WHERE table_schema = 'monitoring'
  AND table_name = 'positions'
  AND column_name = 'exit_reason';
-- Should return: 'text'

-- Check new tables exist:
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'monitoring'
  AND table_name IN ('event_log', 'sync_status');
-- Should return 2 rows
```

## ❓ FAQ

**Q: Will this break existing code?**
A: No, all changes are additive. Existing code continues to work.

**Q: How long will migration take?**
A: Typically < 5 seconds for up to 10,000 positions.

**Q: What if migration fails?**
A: Restore from backup (created automatically) in ~2 minutes.

**Q: Do I need to stop the bot during migration?**
A: No, but recommended for consistency. Migration works with running bot.

**Q: How much disk space needed?**
A: ~20MB additional for typical setup with 1000 positions.

## 🔍 Questions to Answer Before Proceeding

1. How many active positions do you have?
   ```sql
   SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active';
   ```

2. How big is your monitoring schema?
   ```sql
   SELECT pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint)
   FROM pg_tables WHERE schemaname = 'monitoring';
   ```

3. Any positions with exactly 100-char exit_reason?
   ```sql
   SELECT COUNT(*) FROM monitoring.positions WHERE LENGTH(exit_reason) = 100;
   ```

---

*Generated: October 2024*