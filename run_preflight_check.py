#!/usr/bin/env python3
"""
Task 0.1: Pre-flight Database Checks
Проверка текущего состояния БД перед миграциями
"""
import asyncio
import asyncpg
import os
import sys
from config.settings import Config

async def run_checks():
    """Run all pre-flight checks"""

    print("=" * 70)
    print("Task 0.1: Pre-flight Database Checks")
    print("=" * 70)

    # Load config
    config = Config()
    db = config.database

    print(f"\n📊 Connecting to: {db.host}:{db.port}/{db.database}")

    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db.host,
            port=db.port,
            database=db.database,
            user=db.user,
            password=db.password
        )

        print("✅ Connected successfully\n")

        # Check 1: Active positions
        print("1️⃣ Количество активных позиций:")
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active'"
        )
        print(f"   Active positions: {count}")

        # Check 2: Schema size
        print("\n2️⃣ Размер monitoring schema:")
        size = await conn.fetchval("""
            SELECT pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint)
            FROM pg_tables WHERE schemaname = 'monitoring'
        """)
        print(f"   Monitoring schema size: {size}")

        # Check 3: Truncated exit_reasons
        print("\n3️⃣ Позиции с обрезанным exit_reason (ровно 100 символов):")
        truncated = await conn.fetchval("""
            SELECT COUNT(*) FROM monitoring.positions
            WHERE LENGTH(exit_reason) = 100
        """)
        print(f"   Truncated exit_reasons: {truncated}")
        if truncated > 0:
            print(f"   ⚠️ Найдено {truncated} обрезанных сообщений - миграция нужна!")

        # Check 4: Current exit_reason type
        print("\n4️⃣ Текущий тип поля exit_reason:")
        col_info = await conn.fetchrow("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
              AND table_name = 'positions'
              AND column_name = 'exit_reason'
        """)
        if col_info:
            print(f"   Type: {col_info['data_type']}")
            if col_info['character_maximum_length']:
                print(f"   Max length: {col_info['character_maximum_length']}")
                print(f"   ⚠️ VARCHAR({col_info['character_maximum_length']}) - нужна миграция на TEXT")
            else:
                print(f"   ✅ Уже TEXT - миграция exit_reason не нужна")

        # Check 5: New fields existence
        print("\n5️⃣ Проверка существования новых полей:")
        new_fields = ['error_details', 'retry_count', 'last_error_at',
                      'last_sync_at', 'sync_status', 'exchange_order_id', 'sl_order_id']

        existing = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'monitoring'
              AND table_name = 'positions'
              AND column_name = ANY($1::text[])
        """, new_fields)

        existing_names = {row['column_name'] for row in existing}

        for field in new_fields:
            if field in existing_names:
                print(f"   ✅ {field} - существует")
            else:
                print(f"   ❌ {field} - отсутствует (нужна миграция)")

        # Check 6: New tables existence
        print("\n6️⃣ Проверка существования новых таблиц:")
        new_tables = ['event_log', 'schema_migrations', 'sync_status']

        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
              AND table_name = ANY($1::text[])
        """, new_tables)

        existing_tables = {row['table_name'] for row in tables}

        for table in new_tables:
            if table in existing_tables:
                print(f"   ✅ {table} - существует")
            else:
                print(f"   ❌ {table} - отсутствует (нужна миграция)")

        # Check 7: Total DB size
        print("\n7️⃣ Размер всей БД:")
        total_size = await conn.fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        print(f"   Total database size: {total_size}")

        # Summary
        print("\n" + "=" * 70)
        print("📋 SUMMARY")
        print("=" * 70)

        needs_migration = []

        if col_info and col_info['character_maximum_length'] == 100:
            needs_migration.append("exit_reason VARCHAR(100) → TEXT")

        missing_fields = [f for f in new_fields if f not in existing_names]
        if missing_fields:
            needs_migration.append(f"{len(missing_fields)} новых полей")

        missing_tables = [t for t in new_tables if t not in existing_tables]
        if missing_tables:
            needs_migration.append(f"{len(missing_tables)} новых таблиц")

        if needs_migration:
            print("\n⚠️ ТРЕБУЕТСЯ МИГРАЦИЯ:")
            for item in needs_migration:
                print(f"   • {item}")
            print("\n✅ Pre-flight checks завершены - можно продолжать")
        else:
            print("\n✅ Все изменения уже применены - миграция не требуется")

        await conn.close()

        print("\n" + "=" * 70)
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_checks())
    sys.exit(0 if success else 1)
