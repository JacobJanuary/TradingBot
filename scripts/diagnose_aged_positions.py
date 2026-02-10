#!/usr/bin/env python3
"""
SUPERUSDT Aged Position Diagnostic Script

Checks why aged positions are not being closed despite meeting criteria.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


async def diagnose_aged_positions():
    """Diagnose aged position detection and closure logic"""
    
    print("=" * 70)
    print("AGED POSITION DIAGNOSTIC")
    print("=" * 70)
    
    # Load config
    from config.settings import config
    
    print("\n📊 CONFIGURATION:")
    print(f"   MAX_POSITION_AGE_HOURS     = {config.trading.max_position_age_hours}")
    print(f"   AGED_GRACE_PERIOD_HOURS    = {config.trading.aged_grace_period_hours}")
    print(f"   AGED_LOSS_STEP_PERCENT     = {config.trading.aged_loss_step_percent}")
    print(f"   AGED_MAX_LOSS_PERCENT      = {config.trading.aged_max_loss_percent}")
    print(f"   USE_UNIFIED_PROTECTION     = {os.getenv('USE_UNIFIED_PROTECTION', 'false')}")
    
    # Connect to database
    print("\n📂 LOADING POSITIONS FROM DATABASE...")
    
    from database.repository import Repository
    from config.settings import config as global_config
    repo = Repository(global_config.database)
    await repo.initialize()
    
    # Get active positions
    positions = await repo.pool.fetch("""
        SELECT * FROM trading.positions 
        WHERE status = 'active' 
        ORDER BY opened_at
    """)
    
    print(f"\n📍 ACTIVE POSITIONS ({len(positions)}):")
    print("-" * 70)
    
    now = datetime.now(timezone.utc)
    
    for pos in positions:
        symbol = pos.get('symbol', 'Unknown')
        opened_at = pos.get('opened_at')
        entry_price = pos.get('entry_price', 0)
        current_price = pos.get('current_price', 0)
        side = pos.get('side', 'unknown')
        
        # Calculate age
        if opened_at:
            if isinstance(opened_at, str):
                from dateutil import parser
                opened_at = parser.parse(opened_at)
            age_hours = (now - opened_at).total_seconds() / 3600
        else:
            age_hours = 0
        
        # Calculate PnL
        if entry_price and current_price and entry_price > 0:
            if side in ['long', 'buy']:
                pnl_pct = (float(current_price) - float(entry_price)) / float(entry_price) * 100
            else:
                pnl_pct = (float(entry_price) - float(current_price)) / float(entry_price) * 100
        else:
            pnl_pct = 0
        
        # Determine status
        max_age = config.trading.max_position_age_hours
        grace = config.trading.aged_grace_period_hours
        loss_step = float(config.trading.aged_loss_step_percent)
        
        if age_hours <= max_age:
            status = "🟢 YOUNG"
            expected_action = "None - not aged yet"
        else:
            hours_over = age_hours - max_age
            if hours_over <= grace:
                status = "🟡 GRACE PERIOD"
                expected_action = f"Close only if profitable (breakeven)"
            else:
                hours_progressive = hours_over - grace
                loss_tolerance = min(hours_progressive * loss_step, float(config.trading.aged_max_loss_percent))
                status = f"🔴 PROGRESSIVE (tolerance: {loss_tolerance:.1f}%)"
                
                if pnl_pct >= 0:
                    expected_action = "✅ SHOULD CLOSE (profitable)"
                elif abs(pnl_pct) <= loss_tolerance:
                    expected_action = f"✅ SHOULD CLOSE (loss {abs(pnl_pct):.2f}% ≤ tolerance {loss_tolerance:.1f}%)"
                else:
                    expected_action = f"⏳ WAIT (loss {abs(pnl_pct):.2f}% > tolerance {loss_tolerance:.1f}%)"
        
        print(f"\n🔹 {symbol} ({side.upper()})")
        print(f"   Opened: {opened_at}")
        print(f"   Age: {age_hours:.1f}h (max_age: {max_age}h)")
        print(f"   Entry: ${entry_price}")
        print(f"   Current: ${current_price}")
        print(f"   PnL: {pnl_pct:+.2f}%")
        print(f"   Status: {status}")
        print(f"   Expected: {expected_action}")
    
    # Check if there's an aged_positions table with records
    print("\n" + "=" * 70)
    print("📋 AGED POSITIONS TABLE (in database):")
    print("-" * 70)
    
    try:
        result = await repo.pool.fetch("""
            SELECT * FROM trading.aged_positions 
            WHERE status = 'active'
            ORDER BY age_hours DESC
        """)
        
        if result:
            for row in result:
                print(f"   {dict(row)}")
        else:
            print("   (No active aged positions in database)")
            
    except Exception as e:
        print(f"   Error querying aged_positions: {e}")
    
    await repo.close()
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(diagnose_aged_positions())
