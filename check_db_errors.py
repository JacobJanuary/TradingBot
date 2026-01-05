
import asyncio
import asyncpg
import datetime
import json
from decimal import Decimal
import os
import sys
from urllib.parse import quote_plus

# Load DB config from .env file dynamically
def get_db_dsn():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    db_user = "tradebot_user"
    db_pass = "tradebot_password"
    db_host = "localhost"
    db_port = "5433"
    db_name = "tradebot_db"
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line: continue
                key, val = line.split('=', 1)
                if key == 'DB_USER': db_user = val.strip()
                elif key == 'DB_PASSWORD': db_pass = val.strip()
                elif key == 'DB_HOST': db_host = val.strip()
                elif key == 'DB_PORT': db_port = val.strip()
                elif key == 'DB_NAME': db_name = val.strip()
    
    return f"postgresql://{db_user}:{quote_plus(db_pass)}@{db_host}:{db_port}/{db_name}"

DB_DSN = get_db_dsn()

async def check_errors():
    try:
        conn = await asyncpg.connect(DB_DSN)
        print("Connected to database.")
        
        # Query recent stop_loss_error events
        query = """
            SELECT id, created_at, event_type, event_data
            FROM monitoring.events
            WHERE event_type = 'stop_loss_error'
            ORDER BY created_at DESC
            LIMIT 10
        """
        
        rows = await conn.fetch(query)
        
        print(f"\nFound {len(rows)} recent stop_loss_error events:\n")
        for row in rows:
             dt = row['created_at'].strftime("%H:%M:%S.%f")
             raw_data = row['event_data']
             if isinstance(raw_data, str):
                 data = json.loads(raw_data)
             else:
                 data = raw_data
                 
             error_msg = data.get('error', 'N/A')
             symbol = data.get('symbol', 'N/A')
             print(f"[{dt}] {symbol} - ERROR: {error_msg}")
             print("-" * 50)
             
        await conn.close()
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    asyncio.run(check_errors())
