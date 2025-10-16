# Age Detector - Baseline Before Fix

**Date:** 2025-10-15
**Branch:** fix/age-detector-order-proliferation
**Commit:** (initial)

## Files Backed Up

- `core/aged_position_manager.py` → `backups/age_detector_fix_20251015/`
- `core/exchange_manager_enhanced.py` → `backups/age_detector_fix_20251015/`

## Current Configuration

From `.env`:
- MAX_POSITION_AGE_HOURS=3
- AGED_GRACE_PERIOD_HOURS=8
- AGED_LOSS_STEP_PERCENT=0.5
- AGED_MAX_LOSS_PERCENT=10.0

## Known Issues

**Bug #1: Order Proliferation**
- Evidence: 7,165 "Creating initial exit order" in 23h
- Expected: ~14 (one per aged position)
- Cause: `_check_existing_exit_order()` called without `target_price` parameter

## Baseline Metrics (from logs)

Last 23 hours:
- "Creating initial exit order": 7,165
- "Updating exit order": 2,227
- "Exit order already exists": 0 (duplicate prevention NOT working)

## Fix Strategy

**Variant B (Minimal Changes):**
1. Add `create_or_update_exit_order()` to EnhancedExchangeManager
2. Replace call in `aged_position_manager.py` line 295-358
3. NO other changes to working code

## Rollback Plan

```bash
git reset --hard HEAD~1
# OR restore from backup:
cp backups/age_detector_fix_20251015/* core/
```
