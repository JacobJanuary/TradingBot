
import os
import sys

# AUTO-FIX PYTHON PATH for imports
current_dir = os.path.dirname(os.path.abspath(__file__)) # scripts/
project_root = os.path.dirname(current_dir) # root
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import asyncio
import unittest
import json
import asyncpg
from datetime import datetime, timedelta, timezone

# 1. PRINT FILE CONTENT MD5 / GREP
def check_file_content():
    print("\n[DIAGNOSTIC 1] Checking File Content: core/stop_loss_manager.py")
    try:
        path = "core/stop_loss_manager.py"
        with open(path, 'r') as f:
            content = f.read()
            if "try:" in content and "fapiPrivatePostAlgoOrder" in content and "except AttributeError:" in content:
                print("✅ PASSED: try-except block FOUND in file.")
            else:
                print("❌ FAILED: try-except block NOT found!")
                # Print explicit snippet
                start = content.find("fapiPrivatePostAlgoOrder") - 50
                end = start + 200
                print(f"Snippet around fapiPrivatePostAlgoOrder:\n{content[start:end]}")
    except Exception as e:
        print(f"❌ Error reading file: {e}")

def check_exchange_manager():
    print("\n[DIAGNOSTIC 1b] Checking File Content: core/exchange_manager.py")
    try:
        path = "core/exchange_manager.py"
        with open(path, 'r') as f:
            content = f.read()
            # Look for the try-except block added in step 4260
            # "try:\n                algo_method = self.exchange.fapiPrivatePostAlgoOrder\n            except AttributeError:"
            if "try:" in content and "algo_method = self.exchange.fapiPrivatePostAlgoOrder" in content and "except AttributeError" in content:
                print("✅ PASSED: try-except block FOUND in core/exchange_manager.py")
            else:
                print("❌ FAILED: try-except block NOT found in core/exchange_manager.py!")
                start = content.find("fapiPrivatePostAlgoOrder") - 50
                if start > 0:
                    end = start + 300
                    print(f"Snippet:\n{content[start:end]}")
                else:
                    print("String 'fapiPrivatePostAlgoOrder' NOT FOUND in file at all.")
    except Exception as e:
        print(f"❌ Error reading file: {e}")

def check_running_processes():
    print("\n[DIAGNOSTIC 1c] Checking Running Python Processes")
    try:
        import subprocess
        # grep for python, exclude grep itself
        cmd = "ps aux | grep python | grep -v grep | grep -v debug_server_state"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        processes = result.stdout.strip().split('\n')
        print(f"Found {len(processes)} python processes:")
        for p in processes:
            if not p: continue
            
            # Extract PID to find CWD
            try:
                # p string format: user pid ...
                parts = p.split()
                pid = parts[1]
                
                # Get CWD
                cwd_cmd = f"readlink -f /proc/{pid}/cwd" 
                cwd_res = subprocess.run(cwd_cmd, shell=True, capture_output=True, text=True)
                cwd = cwd_res.stdout.strip()
            except:
                cwd = "???"

            # Highlight suspicious scripts
            if "test_aceusdt" in p or "verify_sl" in p or "main.py" in p:
                print(f"🚨 SUSPICIOUS [PID {pid} @ {cwd}]: {p}")
            else:
                print(f"   [PID {pid} @ {cwd}]: {p}")
                
    except Exception as e:
        print(f"❌ Error checking processes: {e}")

# 2. RUN GUARDIAN TEST LOGIC
async def test_guardian_logic():
    print("\n[DIAGNOSTIC 2] Testing Runtime Guardian Logic")
    try:
        from core.stop_loss_manager import StopLossManager
        
        class BrokenExchange:
            def __init__(self): 
                self.options = {}
            def milliseconds(self): return 1000
            def price_to_precision(self, s, p): return float(p)
            def amount_to_precision(self, s, a): return float(a)
            @property
            def fapiPrivatePostAlgoOrder(self):
                raise AttributeError("'binance' object has no attribute 'fapiPrivatePostAlgoOrder'")
        
        ex = BrokenExchange()
        mgr = StopLossManager(ex, 'binance')
        
        try:
            # Correct Signature: symbol, side, amount, stop_price
            await mgr._set_binance_stop_loss_algo("BTCUSDT", "short", 0.1, 50000)
        except AttributeError as e:
            if "CCXT_MISSING_ALGO_METHOD_V2" in str(e):
                print("✅ PASSED: Logic caught AttributeError and raised custom V2 error.")
            else:
                print(f"❌ FAILED: Logic leaked original AttributeError: {e}")
        except Exception as e:
            print(f"⚠️ Unexpected exception: {e}")
            
    except Exception as e:
        print(f"❌ Test Failed to Run: {e}")

# 3. QUERY RECENT ERRORS
async def check_recent_errors():
    print("\n[DIAGNOSTIC 3] Checking DB for LAST 5 MINUTE Errors")
    try:
        # User DSN from env/input
        import os
        
        # 1. Try generic environment variable
        dsn = os.getenv("DATABASE_URL")
        
        # 2. If no DSN, try to parse .env file manually
        if not dsn:
            db_user = "tradebot_user"
            db_pass = "tradebot_password"
            db_host = "localhost"
            db_port = "5432"
            db_name = "tradebot_db"
            
            env_path = os.path.join(project_root, '.env')
            if os.path.exists(env_path):
                print(f"Reading credentials from {env_path}")
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#'): continue
                        if 'DB_USER=' in line: db_user = line.split('=')[1].strip()
                        if 'DB_PASSWORD=' in line: db_pass = line.split('=')[1].strip()
                        if 'DB_HOST=' in line: db_host = line.split('=')[1].strip()
                        if 'DB_PORT=' in line: db_port = line.split('=')[1].strip()
                        if 'DB_NAME=' in line: db_name = line.split('=')[1].strip()
            
            # Construct DSN
            # Handle special chars in password if needed, but simple string usually fine for asyncpg unless complex
            # URL encode password just in case
            from urllib.parse import quote_plus
            encoded_pass = quote_plus(db_pass)
            dsn = f"postgresql://{db_user}:{encoded_pass}@{db_host}:{db_port}/{db_name}"
            # print(f"DEBUG: Using DSN: postgresql://{db_user}:****@{db_host}:{db_port}/{db_name}")

        conn = await asyncpg.connect(dsn)
        
        # 5 mins ago
        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        rows = await conn.fetch("""
            SELECT created_at, event_data 
            FROM monitoring.events 
            WHERE event_type = 'stop_loss_error' 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        print(f"Found {len(rows)} errors total (showing recent):")
        recent_count = 0
        current_time = datetime.now(timezone.utc)
        print(f"Current System Time: {current_time}")

        for row in rows:
            dt = row['created_at']
            # fix timezone awareness if needed
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
                
            age = (current_time - dt).total_seconds()
            data_str = row['event_data']
            if isinstance(data_str, str):
                data = json.loads(data_str)
            else:
                data = data_str
            
            error_msg = data.get('error', 'N/A')
            
            print(f"[{dt.strftime('%H:%M:%S')}] (Age: {age:.1f}s) Error: {error_msg}")
            print(f"   FULL DATA: {json.dumps(data, indent=2, default=str)}")
            
            if age < 300: # 5 mins
                recent_count += 1
                
        if recent_count == 0:
            print("✅ PASSED: NO errors in last 5 minutes.")
        else:
            print(f"❌ FAILED: {recent_count} errors in last 5 minutes!")
            
        await conn.close()
        
    except Exception as e:
        print(f"⚠️ DB Check Failed (Check credentials): {e}")

async def main():
    check_file_content()
    check_exchange_manager()
    check_running_processes()
    await test_guardian_logic()
    await check_recent_errors()

if __name__ == "__main__":
    asyncio.run(main())
