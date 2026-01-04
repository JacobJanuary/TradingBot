
import os
import sys
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
            await mgr._set_binance_stop_loss_algo("BTCUSDT", 50000, "short", 0.1)
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
        # Try to load .env manually if needed, or assume env vars set
        # But script run manually might not have env. 
        # Using the DSN provided by user in conversation or localhost default
        # "postgresql://tradebot_user:LohNeMamont%40%2911@localhost:5433/tradebot_db" (User said output earlier)
        # But on SERVER it connects to localhost:5432 usually?
        # User said: "DB_PORT=5433" in local request.
        # On SERVER, port is usually 5432.
        # Let's try default DSN first, then the custom one.
        
        dsn = os.getenv("DATABASE_URL", "postgresql://tradebot_user:tradebot_password@localhost:5432/tradebot_db")
        
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
    await test_guardian_logic()
    await check_recent_errors()

if __name__ == "__main__":
    asyncio.run(main())
