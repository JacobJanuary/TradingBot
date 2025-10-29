# Cleanup Archive - 2025-10-29

**Date**: 2025-10-29 15:36
**Reason**: Project cleanup - remove junk files and outdated scripts

---

## Contents

### Root Files (moved from /)
- `CCXT_RESEARCH_SUMMARY.md` - Research notes (outdated)
- `bot.log` - Old log file (564KB, from Oct 24)
- `data-*.csv` - Old analysis data
- `main.py` - Unused entry point (bot.py is used)
- `requirements_freeze_before_4.5.12.txt` - Old requirements snapshot
- `test_results_*.json` - Investigation test results (5 files)

### Backups (moved from /backups)
- `pre_utc_migration_20251024_165620.dump` (13MB)
- `pre_utc_migration_20251024_165623.sql` (123MB)
- **Total**: 136MB of DB backups

### Test Scripts (moved from /scripts)
- `test_aave_precision_deep.py`
- `test_bybit_balance_v5.py`
- `test_bybit_price_fetching.py`
- `test_can_open_position_performance.py`
- `test_db_fallback_comprehensive.py`
- `test_db_performance.py`
- `test_fetch_positions.py`
- `test_fix_amount_validation.py`
- `test_granular_lock_fix.py`
- `test_minimum_amount_fix.py`
- `test_minqty_fix.py`
- `test_multiple_symbols_max_notional.py`
- `test_newtusdt_max_notional.py`
- `test_position_not_found_solutions.py`
- **Total**: 14 test scripts

### Coverage Reports
- `htmlcov/` - HTML coverage reports (17MB)
- `.coverage` - Coverage data file

---

## Cleanup Actions

1. ✅ Moved junk files from root to archive
2. ✅ Moved database backups (136MB) to archive
3. ✅ Moved temporary test scripts to archive/test_scripts
4. ✅ Moved coverage reports to archive
5. ✅ Removed Python cache (__pycache__, *.pyc)
6. ✅ Removed pytest cache (.pytest_cache)
7. ✅ Removed benchmark cache (.benchmarks)

---

## Total Space Recovered

- Backups: ~136 MB
- Coverage: ~17 MB
- Test scripts: ~50 KB
- Cache files: ~1 MB
- **Total**: ~154 MB

---

## Notes

All archived files can be safely deleted if not needed. They are not used in production.

Current production uses:
- `bot.py` as entry point
- `logs/trading_bot.log` for current logs
- Current requirements in `requirements.txt`

---

END OF CLEANUP REPORT
