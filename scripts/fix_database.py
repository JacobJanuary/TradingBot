#!/usr/bin/env python3
"""Fix database schema issues"""

import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection parameters
DB_PARAMS = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5433'),
    'database': os.getenv('DB_NAME', 'fox_crypto'),
    'user': os.getenv('DB_USER', 'elcrypto'),
    'password': os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
}

def fix_database_schema():
    """Fix missing columns and schema issues"""
    
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False
    cur = conn.cursor()
    
    fixes_applied = []
    
    try:
        print("🔧 FIXING DATABASE SCHEMA ISSUES\n")
        print("=" * 60)
        
        # 1. Fix signals table - add exchange_id column
        print("\n1. Checking signals table...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'trading_bot' 
            AND table_name = 'signals' 
            AND column_name = 'exchange_id'
        """)
        
        if not cur.fetchone():
            print("   ❌ Column 'exchange_id' missing - adding...")
            cur.execute("""
                ALTER TABLE trading_bot.signals 
                ADD COLUMN exchange_id INTEGER,
                ADD COLUMN exchange VARCHAR(50) DEFAULT 'binance'
            """)
            fixes_applied.append("Added exchange_id and exchange columns to signals table")
            print("   ✅ Column added successfully")
        else:
            print("   ✅ Column 'exchange_id' already exists")
            
        # 2. Add total_balance to performance table
        print("\n2. Checking performance table...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'trading_bot' 
            AND table_name = 'performance' 
            AND column_name = 'total_balance'
        """)
        
        if not cur.fetchone():
            print("   ❌ Column 'total_balance' missing - adding...")
            cur.execute("""
                ALTER TABLE trading_bot.performance 
                ADD COLUMN total_balance DECIMAL(20, 8) DEFAULT 0,
                ADD COLUMN available_balance DECIMAL(20, 8) DEFAULT 0,
                ADD COLUMN margin_used DECIMAL(20, 8) DEFAULT 0
            """)
            fixes_applied.append("Added balance columns to performance table")
            print("   ✅ Balance columns added successfully")
        else:
            print("   ✅ Column 'total_balance' already exists")
            
        # 3. Add missing indexes for better performance
        print("\n3. Checking indexes...")
        
        # Check if index exists
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'trading_bot' 
            AND indexname = 'idx_signals_exchange_id'
        """)
        
        if not cur.fetchone():
            print("   Adding index on signals.exchange_id...")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_exchange_id 
                ON trading_bot.signals(exchange_id)
            """)
            fixes_applied.append("Added index on signals.exchange_id")
            print("   ✅ Index added")
        else:
            print("   ✅ Index already exists")
            
        # 4. Create a view for position statistics
        print("\n4. Creating/updating statistics view...")
        cur.execute("""
            CREATE OR REPLACE VIEW trading_bot.position_statistics AS
            SELECT 
                COUNT(*) as total_positions,
                COUNT(CASE WHEN status = 'open' THEN 1 END) as open_positions,
                COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_positions,
                SUM(CASE WHEN status = 'open' THEN quantity * current_price ELSE 0 END) as total_exposure,
                SUM(pnl) as total_pnl,
                AVG(pnl_percentage) as avg_pnl_percentage,
                COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_positions,
                COUNT(CASE WHEN pnl < 0 THEN 1 END) as losing_positions,
                CASE 
                    WHEN COUNT(CASE WHEN status = 'closed' THEN 1 END) > 0 
                    THEN COUNT(CASE WHEN pnl > 0 THEN 1 END)::FLOAT / 
                         COUNT(CASE WHEN status = 'closed' THEN 1 END) * 100
                    ELSE 0 
                END as win_rate
            FROM trading_bot.positions
        """)
        fixes_applied.append("Created/updated position_statistics view")
        print("   ✅ View created/updated")
        
        # 5. Add balance tracking table if missing
        print("\n5. Checking balance_history table...")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'trading_bot' 
                AND table_name = 'balance_history'
            )
        """)
        
        if not cur.fetchone()[0]:
            print("   Creating balance_history table...")
            cur.execute("""
                CREATE TABLE trading_bot.balance_history (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    exchange VARCHAR(50) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    total_balance DECIMAL(20, 8) NOT NULL,
                    available_balance DECIMAL(20, 8) NOT NULL,
                    margin_used DECIMAL(20, 8) DEFAULT 0,
                    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
                    UNIQUE(timestamp, exchange, currency)
                )
            """)
            
            # Create index for faster queries
            cur.execute("""
                CREATE INDEX idx_balance_history_timestamp 
                ON trading_bot.balance_history(timestamp DESC)
            """)
            
            fixes_applied.append("Created balance_history table")
            print("   ✅ Table created")
        else:
            print("   ✅ Table already exists")
            
        # 6. Fix risk_metrics table - add missing columns
        print("\n6. Updating risk_metrics table...")
        cur.execute("""
            ALTER TABLE trading_bot.risk_metrics 
            ADD COLUMN IF NOT EXISTS total_balance DECIMAL(20, 8) DEFAULT 0,
            ADD COLUMN IF NOT EXISTS exchange VARCHAR(50) DEFAULT 'binance'
        """)
        fixes_applied.append("Added missing columns to risk_metrics table")
        print("   ✅ Columns added/verified")
        
        # 7. Create stored procedure for getting total balance
        print("\n7. Creating helper functions...")
        cur.execute("""
            CREATE OR REPLACE FUNCTION trading_bot.get_total_balance(
                p_exchange VARCHAR DEFAULT NULL
            )
            RETURNS TABLE (
                exchange VARCHAR,
                total_balance DECIMAL,
                available_balance DECIMAL,
                margin_used DECIMAL,
                unrealized_pnl DECIMAL
            )
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RETURN QUERY
                SELECT 
                    bh.exchange,
                    bh.total_balance,
                    bh.available_balance,
                    bh.margin_used,
                    COALESCE(
                        (SELECT SUM(p.pnl) 
                         FROM trading_bot.positions p 
                         WHERE p.status = 'open' 
                         AND (p_exchange IS NULL OR p.exchange = p_exchange)
                        ), 0
                    ) as unrealized_pnl
                FROM (
                    SELECT DISTINCT ON (bh2.exchange) 
                        bh2.exchange,
                        bh2.total_balance,
                        bh2.available_balance,
                        bh2.margin_used
                    FROM trading_bot.balance_history bh2
                    WHERE p_exchange IS NULL OR bh2.exchange = p_exchange
                    ORDER BY bh2.exchange, bh2.timestamp DESC
                ) bh;
            END;
            $$;
        """)
        fixes_applied.append("Created get_total_balance function")
        print("   ✅ Function created")
        
        # Commit all changes
        conn.commit()
        
        print("\n" + "=" * 60)
        print("✅ DATABASE FIXES COMPLETED SUCCESSFULLY")
        print("\nChanges applied:")
        for fix in fixes_applied:
            print(f"  • {fix}")
            
        if not fixes_applied:
            print("  • No fixes needed - schema is up to date")
            
        # Verify the fixes
        print("\n" + "=" * 60)
        print("VERIFYING FIXES...")
        
        # Check signals table
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'trading_bot' 
            AND table_name = 'signals' 
            AND column_name IN ('exchange_id', 'exchange')
            ORDER BY ordinal_position
        """)
        
        columns = cur.fetchall()
        if columns:
            print("\n✅ Signals table columns:")
            for col_name, data_type in columns:
                print(f"   • {col_name}: {data_type}")
                
        # Check performance table
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'trading_bot' 
            AND table_name = 'performance' 
            AND column_name LIKE '%balance%'
            ORDER BY ordinal_position
        """)
        
        columns = cur.fetchall()
        if columns:
            print("\n✅ Performance table balance columns:")
            for col_name, data_type in columns:
                print(f"   • {col_name}: {data_type}")
                
        # Test the function
        cur.execute("SELECT * FROM trading_bot.get_total_balance()")
        result = cur.fetchone()
        print("\n✅ Balance function test:")
        if result:
            print(f"   • Can retrieve balance data")
        else:
            print(f"   • No balance data yet (normal for new installation)")
            
        print("\n" + "=" * 60)
        print("🎉 All database issues have been resolved!")
        print("\nThe system is now ready for operation.")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error applying fixes: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fix_database_schema()