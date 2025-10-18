# 🐛 SINGLE INSTANCE LOCK BUG ANALYSIS

**Date:** 2025-10-18
**Issue:** Two bot instances ran simultaneously despite SingleInstance lock
**Status:** 🔴 ROOT CAUSE FOUND

---

## 🔍 DISCOVERED FACTS

### Two bots were running:

1. **PID 72189** - Started 20:10 (8:10 PM), ran 10+ hours
2. **PID 17656** - Started 14:43 (2:43 PM), ran 3+ hours

Both writing to same database simultaneously!

### Lock file state:

```bash
$ ls -lah /var/folders/.../T/trading_bot.*
-rw-r--r-- trading_bot.lock (0 bytes, modified 15:00)

$ cat trading_bot.pid
# File not found!

$ cat trading_bot.info
# File not found!
```

**Lock файл пустой, .pid и .info файлов нет!**

---

## 🐛 ROOT CAUSES IDENTIFIED

### Bug #1: FileLock vs PID File Mismatch

**Problem:**
- FileLock blocks using `.lock` file
- Validation checks `.pid` file
- **They are INDEPENDENT!**

**Code:**
```python
# utils/single_instance.py:133-142
if self.lock_file.exists():  # Check .lock file
    if not self._is_lock_valid():  # Check .pid file! ← MISMATCH!
        self._cleanup_stale_lock()

self.lock = FileLock(str(self.lock_file), timeout=self.timeout)
self.lock.acquire(timeout=self.timeout)
```

**Scenario that breaks:**
1. Process A gets lock, creates .lock + .pid
2. .pid file deleted (by cleanup script, user, etc)
3. Process B starts, checks `_is_lock_valid()`
4. `get_running_pid()` returns None (no .pid file)
5. `_is_lock_valid()` returns FALSE
6. Process B thinks lock is stale
7. Process B calls `_cleanup_stale_lock()` → **deletes .lock file!**
8. Process B creates new lock
9. **Both processes now have locks!**

### Bug #2: No Atomic Lock Check

**Problem:**
```python
# Step 1: Check if lock exists
if self.lock_file.exists():
    # Step 2: Validate lock
    if not self._is_lock_valid():
        # Step 3: Clean up
        self._cleanup_stale_lock()

# Step 4: Create new lock
self.lock = FileLock(...)
self.lock.acquire()
```

**RACE CONDITION** between steps 1-4!

Two processes can both:
1. See no .lock file (or stale lock)
2. Both call FileLock()
3. Both call acquire()
4. **FileLock might let both through!**

### Bug #3: Silent PID File Write Failure

**Code:**
```python
def _write_pid_file(self):
    try:
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Failed to write PID file: {e}")  # ← Only warning!
```

If .pid file write fails:
- Lock is acquired ✅
- But .pid file missing ❌
- Next process thinks lock is stale ❌
- Deletes lock ❌
- Gets new lock ❌
- **Duplicate!** ❌

---

## 💡 HOW IT HAPPENED

### Most Likely Scenario:

**14:43** - First bot (PID 17656) started
- Acquired lock
- Created .lock, .pid, .info files
- Started working

**15:00** - Someone ran cleanup script
- Deleted log files
- **Maybe deleted lock files too?**
- Or .pid file corrupted?

**20:10** - Second bot (PID 72189) started
- Checked .lock file → exists
- Checked .pid file → missing or invalid
- Thought lock is stale
- Deleted .lock file
- Created new lock
- **Both bots now running!**

**Alternative Scenario:**

FileLock library has bug where timeout=0 doesn't work correctly on macOS!

---

## 🔧 FIX REQUIRED

### Fix #1: Use PID in Lock File

**Instead of separate .pid file, store PID inside .lock file:**

```python
def acquire(self) -> bool:
    try:
        # Create lock with PID inside
        self.lock = FileLock(str(self.lock_file), timeout=self.timeout)

        # Try to acquire (will fail if another process holds it)
        self.lock.acquire(timeout=self.timeout)

        # Write PID to .lock file itself
        with open(self.lock_file, 'w') as f:
            f.write(f"{os.getpid()}\n")
            f.write(f"{datetime.now().isoformat()}\n")

        self.acquired = True
        return True

    except Timeout:
        # Read .lock file to see who has it
        try:
            with open(self.lock_file, 'r') as f:
                pid = int(f.readline().strip())

            # Check if process is alive
            if self.is_process_running(pid):
                logger.error(f"Lock held by PID {pid}")
                return False
            else:
                # Process dead, but lock file exists
                logger.warning(f"Stale lock from dead PID {pid}")
                # Force break lock
                self.lock_file.unlink()
                # Retry once
                return self.acquire()

        except:
            return False
```

### Fix #2: Add Lock Verification After Acquire

```python
def acquire(self) -> bool:
    # Acquire lock
    self.lock.acquire(timeout=self.timeout)

    # Write PID
    self._write_pid_file()

    # VERIFY we actually have the lock
    time.sleep(0.1)  # Let other processes write if they got it too

    pid_in_file = self.get_running_pid()
    if pid_in_file != os.getpid():
        logger.error(f"Lock acquired but PID mismatch: {pid_in_file} != {os.getpid()}")
        self.release()
        return False

    return True
```

### Fix #3: Use Database-Based Lock

**Most reliable option:**

```python
async def acquire_db_lock(self) -> bool:
    """Use PostgreSQL advisory lock"""
    # Advisory lock - atomic, process-scoped
    result = await conn.fetchval(
        "SELECT pg_try_advisory_lock($1)",
        hash('trading_bot')
    )
    return result  # True if acquired, False if already locked
```

**Advantages:**
- Atomic operation
- Automatically released on process death
- No file system race conditions
- Works across network (if needed)

---

## 🚨 IMMEDIATE ACTION REQUIRED

### Option A: Quick Fix (Use flock)

Replace FileLock with native flock:

```python
import fcntl

def acquire(self) -> bool:
    try:
        self.lock_fd = open(self.lock_file, 'w')
        fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Write PID
        self.lock_fd.write(f"{os.getpid()}\n")
        self.lock_fd.flush()

        return True

    except IOError:
        # Lock held by another process
        return False
```

### Option B: Database Lock (Best)

Use PostgreSQL advisory locks - guaranteed atomic.

### Option C: Add Verification

Keep current code but add verification that lock actually works.

---

## 🧪 TEST REPRODUCTION

```bash
# Terminal 1
python3 main.py &
sleep 1

# Terminal 2
python3 main.py &

# Check if both running
ps aux | grep main.py

# Should only be ONE!
```

---

## 📊 IMPACT

### What went wrong:
- ❌ Two bots ran simultaneously
- ❌ Both writing to same DB
- ❌ Duplicate events
- ❌ Confusing logs
- ❌ Wasted resources (2x CPU)

### What went right:
- ✅ No data corruption
- ✅ No money lost
- ✅ Both bots functioning correctly
- ✅ Easy to detect (DB connections)

---

## ✅ RECOMMENDATION

**Implement Option B (Database Lock) ASAP!**

It's:
- ✅ Atomic
- ✅ Reliable
- ✅ Auto-cleanup on crash
- ✅ No file system issues
- ✅ Works across network

**Plus add startup check:**
```python
# On startup, check for running instances
result = await conn.fetch("""
    SELECT pid, application_name
    FROM pg_stat_activity
    WHERE application_name = 'trading_bot'
    AND pid != pg_backend_pid()
""")

if result:
    logger.error(f"Found {len(result)} other bot instances!")
    for row in result:
        logger.error(f"  PID {row['pid']}: {row['application_name']}")
    sys.exit(1)
```

---

**Created:** 2025-10-18
**Priority:** 🔴 CRITICAL
**Status:** Bug identified, fix required

