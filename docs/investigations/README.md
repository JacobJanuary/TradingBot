# 🔍 Investigation Reports

This directory contains detailed investigation reports for bugs, issues, and system analysis.

---

## 📋 Naming Convention

All investigation reports should follow this format:

```
{TOPIC}_{YYYYMMDD}.md
or
{TOPIC}_{DESCRIPTION}_{YYYYMMDD}.md
```

**Examples:**
- `WAVE_22_49_FINAL_ANALYSIS_20251025.md`
- `BYBIT_BALANCE_BUG_FIX_20251025.md`
- `MAGIC_NUMBERS_AUDIT_REPORT_20251025.md`

---

## 📁 Current Investigations (Oct 2025)

### 🔴 Critical Issues

#### BYBIT_BALANCE_BUG_FIX_20251025.md
**Issue:** Bybit mainnet showing $0.00 free balance when $52.71 available
**Root Cause:** API returns empty string for `totalAvailableBalance`
**Status:** ✅ Fixed - now reading from `coin[]` array
**Impact:** ALL Bybit signals filtered since mainnet switch

#### MAGIC_NUMBERS_AUDIT_REPORT_20251025.md
**Issue:** Found 254 magic numbers in codebase
**Critical:** `200.0` hardcoded in signal_processor_websocket.py:312
**Status:** ⚠️ Awaiting fix approval
**Impact:** ALL Bybit signals filtered (checking $52 < $200)

#### MAGIC_NUMBER_200_VISUAL_20251025.md
**Type:** Visual explanation of the $200 magic number problem
**Contents:** Diagrams, flow charts, impact timeline
**Purpose:** User-friendly visualization of critical bug

#### MAGIC_NUMBERS_EXECUTIVE_SUMMARY_20251025.md
**Type:** Executive summary of magic numbers audit
**Contents:** Quick overview, priorities, action plan
**Purpose:** Fast reference for decision making

### 📊 Wave Analysis

#### WAVE_22_49_INITIAL_ANALYSIS_20251025.txt
**Wave Time:** 2025-10-24 22:49 UTC
**Signals:** 22 total, 0 opened
**Initial Findings:** All signals filtered, suspected balance issues

#### WAVE_22_49_FORENSIC_ANALYSIS_20251025.md
**Type:** Deep forensic investigation
**Key Finding:** Bybit $0 balance + 2 Binance signals filtered
**Status:** Bybit explained, Binance pending logs

#### WAVE_22_49_FINAL_ANALYSIS_20251025.md
**Type:** Complete investigation report
**Conclusion:**
- 3 Bybit: Balance bug (fixed)
- 2 Binance: Likely duplicates (needs confirmation)
- 17 others: Not in top 7 (expected)

---

## 🎯 Investigation Categories

### Bug Reports
Detailed analysis of bugs found in production:
- Root cause analysis
- Impact assessment
- Fix verification
- Lessons learned

### System Audits
Comprehensive system reviews:
- Code quality audits
- Configuration audits
- Performance analysis
- Security reviews

### Wave Analysis
Trading wave execution investigations:
- Signal processing flow
- Filter/validation analysis
- Success/failure breakdown
- Optimization recommendations

### Performance Issues
System performance investigations:
- Bottleneck identification
- Optimization strategies
- Before/after metrics

---

## 📝 Report Structure

Each investigation should include:

### 1. Executive Summary
- What happened
- Impact
- Current status
- Action required

### 2. Problem Statement
- Symptoms observed
- User reports
- Log evidence
- Metrics/data

### 3. Investigation Process
- Hypothesis formation
- Testing methodology
- Evidence gathering
- Analysis approach

### 4. Root Cause Analysis
- Primary cause
- Contributing factors
- Why it happened
- Why not caught earlier

### 5. Solution/Fix
- Proposed solution
- Implementation details
- Testing strategy
- Rollback plan

### 6. Verification
- Test results
- Metrics validation
- User confirmation
- Production monitoring

### 7. Prevention
- Process improvements
- Code changes needed
- Monitoring additions
- Documentation updates

### 8. Lessons Learned
- What went well
- What could improve
- Team takeaways
- Future recommendations

---

## 🔧 Creating New Reports

When creating a new investigation report:

1. **Use this template location:**
   ```
   /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/docs/investigations/
   ```

2. **Name the file:**
   ```
   {TOPIC}_{YYYYMMDD}.md
   ```

3. **Include metadata at top:**
   ```markdown
   # {Investigation Title}

   **Date:** YYYY-MM-DD
   **Investigator:** [Name/Tool]
   **Severity:** [Critical/High/Medium/Low]
   **Status:** [Active/Fixed/Monitoring/Closed]
   **Related:** [Links to related reports]
   ```

4. **Update this README:**
   - Add to current investigations list
   - Link to new report
   - Update category if needed

---

## 📊 Statistics

**Total Reports:** 7 (as of 2025-10-25)

**By Category:**
- Critical Bugs: 2
- System Audits: 3
- Wave Analysis: 3
- Performance: 0

**By Status:**
- Fixed: 1
- In Progress: 1
- Awaiting Approval: 1
- Completed: 4

---

## 🔗 Related Documentation

- `/docs/` - General documentation
- `/docs/archive/` - Older investigations (pre-structure)
- `/tests/` - Test reports and results
- `/.env` - Current configuration
- `/config/settings.py` - Configuration code

---

## ✅ Best Practices

1. **Always include dates** in filenames and content
2. **Be specific** - clear problem statements
3. **Include evidence** - logs, metrics, screenshots
4. **Document the process** - how you investigated
5. **Provide context** - why this matters
6. **Link related items** - other reports, commits, issues
7. **Update this README** when adding reports
8. **Archive old reports** after 6 months (move to archive/)

---

**Last Updated:** 2025-10-25
**Maintained By:** Development Team
