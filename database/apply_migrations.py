#!/usr/bin/env python3
"""
Database Migration Script
Applies all pending migrations to the database

Usage:
    python database/apply_migrations.py
    python database/apply_migrations.py --dry-run
"""
import asyncio
import asyncpg
import os
from pathlib import Path
from typing import List, Tuple
from datetime import datetime
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Config
from utils.logger import logger


class MigrationManager:
    """Manages database migrations"""
    
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.migrations_dir = Path(__file__).parent / 'migrations'
        
    async def connect(self) -> asyncpg.Connection:
        """Create database connection"""
        return await asyncpg.connect(
            host=self.db_config.get('host', 'localhost'),
            port=self.db_config.get('port', 5433),
            database=self.db_config.get('database', 'fox_crypto'),
            user=self.db_config.get('user', 'elcrypto'),
            password=self.db_config.get('password', '')
        )
    
    async def create_migrations_table(self, conn: asyncpg.Connection):
        """Create table to track applied migrations"""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring.applied_migrations (
                id SERIAL PRIMARY KEY,
                migration_file VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW(),
                checksum VARCHAR(64),
                status VARCHAR(20) DEFAULT 'success'
            )
        """)
        logger.info("✅ Migrations tracking table ready")
    
    async def get_applied_migrations(self, conn: asyncpg.Connection) -> set:
        """Get list of already applied migrations"""
        rows = await conn.fetch(
            "SELECT migration_file FROM monitoring.applied_migrations WHERE status = 'success'"
        )
        return {row['migration_file'] for row in rows}
    
    def get_pending_migrations(self, applied: set) -> List[Path]:
        """Get list of migrations to apply"""
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return []
        
        all_migrations = sorted(self.migrations_dir.glob('*.sql'))
        pending = [m for m in all_migrations if m.name not in applied]
        
        logger.info(f"📋 Found {len(all_migrations)} total migrations")
        logger.info(f"✅ Already applied: {len(applied)}")
        logger.info(f"⏳ Pending: {len(pending)}")
        
        return pending
    
    async def apply_migration(self, conn: asyncpg.Connection, migration_file: Path, dry_run: bool = False) -> bool:
        """Apply a single migration"""
        logger.info(f"\n{'[DRY-RUN] ' if dry_run else ''}📝 Applying: {migration_file.name}")
        
        try:
            # Read migration SQL
            sql_content = migration_file.read_text()
            
            if dry_run:
                logger.info(f"{'='*60}")
                logger.info(sql_content)
                logger.info(f"{'='*60}")
                return True
            
            # Execute migration in transaction
            async with conn.transaction():
                # Split by semicolon and execute each statement
                statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]
                
                for stmt in statements:
                    if stmt.upper().startswith('SELECT'):
                        # For SELECT statements (verification), just log the result
                        result = await conn.fetch(stmt)
                        logger.info(f"  Verification: {len(result)} rows")
                    else:
                        await conn.execute(stmt)
                
                # Record migration as applied
                await conn.execute(
                    """
                    INSERT INTO monitoring.applied_migrations (migration_file, applied_at, status)
                    VALUES ($1, NOW(), 'success')
                    ON CONFLICT (migration_file) DO UPDATE SET applied_at = NOW()
                    """,
                    migration_file.name
                )
            
            logger.info(f"✅ Successfully applied: {migration_file.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to apply {migration_file.name}: {e}")
            
            if not dry_run:
                # Record failed migration
                try:
                    await conn.execute(
                        """
                        INSERT INTO monitoring.applied_migrations (migration_file, applied_at, status)
                        VALUES ($1, NOW(), 'failed')
                        ON CONFLICT (migration_file) DO UPDATE SET status = 'failed', applied_at = NOW()
                        """,
                        migration_file.name
                    )
                except:
                    pass
            
            return False
    
    async def apply_all_migrations(self, dry_run: bool = False):
        """Apply all pending migrations"""
        logger.info(f"\n{'='*70}")
        logger.info(f"🔄 {'DRY-RUN: ' if dry_run else ''}Database Migration Process Started")
        logger.info(f"{'='*70}\n")
        
        conn = None
        try:
            # Connect to database
            conn = await self.connect()
            logger.info(f"✅ Connected to database: {self.db_config.get('database')}")
            
            # Create migrations tracking table
            await self.create_migrations_table(conn)
            
            # Get applied and pending migrations
            applied = await self.get_applied_migrations(conn)
            pending = self.get_pending_migrations(applied)
            
            if not pending:
                logger.info("\n✨ No pending migrations. Database is up to date!")
                return True
            
            # Apply each pending migration
            success_count = 0
            for migration_file in pending:
                success = await self.apply_migration(conn, migration_file, dry_run)
                if success:
                    success_count += 1
                else:
                    logger.error(f"\n⚠️  Migration failed. Stopping here.")
                    break
            
            # Summary
            logger.info(f"\n{'='*70}")
            logger.info(f"📊 Migration Summary:")
            logger.info(f"   Total pending: {len(pending)}")
            logger.info(f"   Successfully applied: {success_count}")
            logger.info(f"   Failed: {len(pending) - success_count}")
            logger.info(f"{'='*70}\n")
            
            return success_count == len(pending)
            
        except Exception as e:
            logger.error(f"❌ Migration process failed: {e}")
            return False
        finally:
            if conn:
                await conn.close()
                logger.info("🔌 Database connection closed")


async def main():
    """Main entry point"""
    # Check for dry-run flag
    dry_run = '--dry-run' in sys.argv
    
    if dry_run:
        logger.info("🔍 DRY-RUN MODE: No changes will be made to the database\n")
    
    # Load config
    config = Config()
    db_config = {
        'host': config.database.host,
        'port': config.database.port,
        'database': config.database.database,
        'user': config.database.user,
        'password': config.database.password
    }
    
    # Run migrations
    manager = MigrationManager(db_config)
    success = await manager.apply_all_migrations(dry_run)
    
    if success:
        logger.info("✅ All migrations applied successfully!")
        return 0
    else:
        logger.error("❌ Some migrations failed. Please check the logs.")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

