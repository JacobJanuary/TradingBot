
import asyncio
import asyncpg
import datetime
from decimal import Decimal
import os
import sys

# Load DB config from env or hardcode consistent with project
DB_DSN = "postgresql://tradebot_user:tradebot_password@localhost:5432/tradebot_db"

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
             data = row['event_data']
             error_msg = data.get('error', 'N/A')
             symbol = data.get('symbol', 'N/A')
             print(f"[{dt}] {symbol} - ERROR: {error_msg}")
             print("-" * 50)
             
        await conn.close()
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    asyncio.run(check_errors())
