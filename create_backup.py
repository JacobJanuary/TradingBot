#!/usr/bin/env python3
"""
Task 1.1: Create backup of monitoring schema
Creates SQL dump of monitoring schema structure and data
"""
import asyncio
import asyncpg
from datetime import datetime
from config.settings import Config

async def create_backup():
    """Create backup of monitoring schema"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_monitoring_{timestamp}.sql"

    print("=" * 70)
    print("Task 1.1: Creating backup of monitoring schema")
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

        # Get all tables in monitoring schema
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            ORDER BY table_name
        """)

        print(f"📋 Found {len(tables)} tables in monitoring schema:")
        for table in tables:
            print(f"   • {table['table_name']}")

        # Start building backup SQL
        backup_sql = []
        backup_sql.append("-- Backup of monitoring schema")
        backup_sql.append(f"-- Created: {datetime.now().isoformat()}")
        backup_sql.append(f"-- Database: {db.database}")
        backup_sql.append("--" + "=" * 68)
        backup_sql.append("")
        backup_sql.append("-- Create monitoring schema if not exists")
        backup_sql.append("CREATE SCHEMA IF NOT EXISTS monitoring;")
        backup_sql.append("")

        # For each table, get structure and data
        for table_row in tables:
            table_name = table_row['table_name']
            print(f"\n📦 Backing up table: {table_name}")

            # Get table definition
            backup_sql.append(f"-- Table: monitoring.{table_name}")
            backup_sql.append("--" + "-" * 68)

            # Get columns definition
            columns = await conn.fetch("""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'monitoring'
                  AND table_name = $1
                ORDER BY ordinal_position
            """, table_name)

            # Build CREATE TABLE statement (simplified, for reference only)
            backup_sql.append(f"-- CREATE TABLE monitoring.{table_name} (")
            for col in columns:
                col_def = f"--   {col['column_name']} {col['data_type']}"
                if col['character_maximum_length']:
                    col_def += f"({col['character_maximum_length']})"
                if col['is_nullable'] == 'NO':
                    col_def += " NOT NULL"
                if col['column_default']:
                    col_def += f" DEFAULT {col['column_default']}"
                backup_sql.append(col_def)
            backup_sql.append("-- );")
            backup_sql.append("")

            # Get row count
            count = await conn.fetchval(f"SELECT COUNT(*) FROM monitoring.{table_name}")
            print(f"   Rows: {count}")

            if count > 0:
                # Get data
                rows = await conn.fetch(f"SELECT * FROM monitoring.{table_name}")

                # Get column names
                col_names = [col['column_name'] for col in columns]

                backup_sql.append(f"-- Data for monitoring.{table_name} ({count} rows)")
                backup_sql.append(f"-- Note: This backup contains structure info only")
                backup_sql.append(f"-- Use pg_dump for full data restore")
                backup_sql.append("")
            else:
                backup_sql.append(f"-- No data in monitoring.{table_name}")
                backup_sql.append("")

        # Get indexes
        indexes = await conn.fetch("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'monitoring'
            ORDER BY indexname
        """)

        if indexes:
            backup_sql.append("-- Indexes")
            backup_sql.append("--" + "-" * 68)
            for idx in indexes:
                backup_sql.append(f"-- {idx['indexdef']};")
            backup_sql.append("")

        # Get constraints
        constraints = await conn.fetch("""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_schema = 'monitoring'
            ORDER BY constraint_name
        """)

        if constraints:
            backup_sql.append("-- Constraints")
            backup_sql.append("--" + "-" * 68)
            for const in constraints:
                backup_sql.append(f"-- {const['constraint_name']} ({const['constraint_type']})")
            backup_sql.append("")

        # Save backup file
        with open(backup_file, 'w') as f:
            f.write('\n'.join(backup_sql))

        print("\n" + "=" * 70)
        print("✅ BACKUP CREATED")
        print("=" * 70)
        print(f"\nBackup file: {backup_file}")

        # Get file size
        import os
        file_size = os.path.getsize(backup_file)
        print(f"File size: {file_size:,} bytes")

        print("\n📌 Note:")
        print("   This backup contains schema structure information.")
        print("   For full data backup, use pg_dump command:")
        print(f"   pg_dump -h {db.host} -p {db.port} -U {db.user} -d {db.database} \\")
        print(f"           -n monitoring -f {backup_file}.full")

        await conn.close()

        print("\n" + "=" * 70)
        return backup_file

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None

if __name__ == "__main__":
    import sys
    backup_file = asyncio.run(create_backup())
    sys.exit(0 if backup_file else 1)
