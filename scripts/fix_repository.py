#!/usr/bin/env python3
"""Fix repository methods to use correct schema"""

import os
from pathlib import Path

def fix_repository():
    """Fix repository methods to use trading_bot schema"""
    
    repo_file = Path(__file__).parent.parent / "database" / "repository.py"
    
    if not repo_file.exists():
        print(f"❌ Repository file not found: {repo_file}")
        return
        
    print("🔧 Fixing repository methods...")
    
    with open(repo_file, 'r') as f:
        content = f.read()
    
    # Fix schema references
    replacements = [
        # Fix monitoring schema to trading_bot
        ('FROM monitoring.positions', 'FROM trading_bot.positions'),
        ('UPDATE monitoring.positions', 'UPDATE trading_bot.positions'),
        ('INSERT INTO monitoring.positions', 'INSERT INTO trading_bot.positions'),
        ('FROM monitoring.signals', 'FROM trading_bot.signals'),
        ('UPDATE monitoring.signals', 'UPDATE trading_bot.signals'),
        ('INSERT INTO monitoring.signals', 'INSERT INTO trading_bot.signals'),
        
        # Fix fas schema references if any
        ('FROM fas.', 'FROM trading_bot.'),
        ('UPDATE fas.', 'UPDATE trading_bot.'),
        ('INSERT INTO fas.', 'INSERT INTO trading_bot.'),
    ]
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"  ✅ Replaced '{old}' with '{new}'")
    
    # Update get_pending_signals method
    old_method = """    async def get_pending_signals(self) -> List[Any]:
        \"\"\"Get pending signals\"\"\"
        return []"""
    
    new_method = """    async def get_pending_signals(self) -> List[Any]:
        \"\"\"Get pending signals\"\"\"
        query = \"\"\"
            SELECT * FROM trading_bot.signals 
            WHERE processed = false 
            ORDER BY created_at DESC
            LIMIT 10
        \"\"\"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]"""
    
    if old_method in content:
        content = content.replace(old_method, new_method)
        print("  ✅ Fixed get_pending_signals method")
    
    # Update get_daily_pnl method
    old_daily_pnl = """    async def get_daily_pnl(self) -> Decimal:
        \"\"\"Get daily PnL\"\"\"
        return Decimal('0')"""
    
    new_daily_pnl = """    async def get_daily_pnl(self) -> Decimal:
        \"\"\"Get daily PnL\"\"\"
        query = \"\"\"
            SELECT COALESCE(SUM(pnl), 0) as daily_pnl
            FROM trading_bot.positions
            WHERE DATE(closed_at) = CURRENT_DATE
        \"\"\"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return Decimal(str(row['daily_pnl'])) if row else Decimal('0')"""
    
    if old_daily_pnl in content:
        content = content.replace(old_daily_pnl, new_daily_pnl)
        print("  ✅ Fixed get_daily_pnl method")
    
    # Save the fixed file
    with open(repo_file, 'w') as f:
        f.write(content)
    
    print("\n✅ Repository file fixed successfully!")

if __name__ == "__main__":
    fix_repository()