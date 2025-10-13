#!/usr/bin/env python3
"""
Check database status and table counts
ONLY ANALYSIS - NO CODE CHANGES
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    # Get DB config from .env
    config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5433)),
        'database': os.getenv('DB_NAME', 'fox_crypto_test'),
        'user': os.getenv('DB_USER', 'elcrypto'),
        'password': os.getenv('DB_PASSWORD', '')
    }

    print("=" * 80)
    print("DATABASE STATUS CHECK")
    print("=" * 80)
    print(f"Connecting to: {config['user']}@{config['host']}:{config['port']}/{config['database']}")
    print()

    try:
        # Connect
        conn = await asyncpg.connect(**config)
        print("✅ Connected successfully!")
        print()

        # Check schemas
        print("📊 SCHEMAS:")
        schemas = await conn.fetch("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name IN ('fas', 'monitoring', 'public')
            ORDER BY schema_name
        """)
        for s in schemas:
            print(f"  - {s['schema_name']}")
        print()

        # Check tables in monitoring schema
        print("📋 TABLES in monitoring schema:")
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'monitoring'
            ORDER BY tablename
        """)

        if not tables:
            print("  ❌ NO TABLES FOUND")
        else:
            for t in tables:
                # Get row count
                try:
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM monitoring.{t['tablename']}")
                    print(f"  - monitoring.{t['tablename']:<30} → {count:>6} записей")
                except Exception as e:
                    print(f"  - monitoring.{t['tablename']:<30} → ERROR: {e}")
        print()

        # Check positions table specifically
        print("🎯 POSITIONS TABLE DETAILS:")
        try:
            # Check if table exists
            exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'monitoring'
                    AND table_name = 'positions'
                )
            """)

            if exists:
                print("  ✅ Table exists")

                # Get columns
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'monitoring'
                    AND table_name = 'positions'
                    ORDER BY ordinal_position
                """)
                print(f"  Columns: {len(columns)}")
                for col in columns[:10]:  # First 10 columns
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    print(f"    - {col['column_name']:<25} {col['data_type']:<15} {nullable}")

                if len(columns) > 10:
                    print(f"    ... and {len(columns) - 10} more columns")

                # Get row count
                count = await conn.fetchval("SELECT COUNT(*) FROM monitoring.positions")
                print(f"  Total rows: {count}")

                # Get open positions
                if count > 0:
                    open_count = await conn.fetchval("""
                        SELECT COUNT(*) FROM monitoring.positions WHERE status = 'open'
                    """)
                    print(f"  Open positions: {open_count}")

                    # Get sample
                    if open_count > 0:
                        samples = await conn.fetch("""
                            SELECT id, symbol, exchange, side, status, created_at
                            FROM monitoring.positions
                            WHERE status = 'open'
                            ORDER BY created_at DESC
                            LIMIT 5
                        """)
                        print(f"\n  Sample open positions:")
                        for pos in samples:
                            print(f"    #{pos['id']}: {pos['symbol']:<15} {pos['exchange']:<10} {pos['side']:<6} created: {pos['created_at']}")
            else:
                print("  ❌ Table does NOT exist")

        except Exception as e:
            print(f"  ❌ Error checking positions: {e}")
        print()

        # Check search_path
        print("🔍 PostgreSQL search_path:")
        search_path = await conn.fetchval("SHOW search_path")
        print(f"  {search_path}")
        print()

        await conn.close()
        print("✅ Analysis complete!")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print()
        print("Possible reasons:")
        print("  - PostgreSQL not running")
        print("  - Wrong credentials")
        print("  - Database does not exist")
        print("  - Port incorrect")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
