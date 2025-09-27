#!/usr/bin/env python3
"""
Test database connection with different configurations
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_connection(host, port, database, user, password):
    """Test database connection"""
    print(f"\nTesting connection to {host}:{port}")
    print(f"Database: {database}")
    print(f"User: {user}")
    
    try:
        # Try to connect
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=10
        )
        
        # Test query
        version = await conn.fetchval('SELECT version()')
        print(f"✅ Connected successfully!")
        print(f"PostgreSQL version: {version}")
        
        # Get schemas
        schemas = await conn.fetch("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY schema_name
        """)
        print(f"\nAvailable schemas: {', '.join([s['schema_name'] for s in schemas])}")
        
        # Get tables count
        tables = await conn.fetch("""
            SELECT table_schema, COUNT(*) as table_count
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            GROUP BY table_schema
            ORDER BY table_schema
        """)
        
        print("\nTables per schema:")
        for t in tables:
            print(f"  - {t['table_schema']}: {t['table_count']} tables")
        
        await conn.close()
        return True
        
    except asyncpg.exceptions.InvalidCatalogNameError as e:
        print(f"❌ Database '{database}' does not exist")
        return False
    except asyncpg.exceptions.InvalidPasswordError as e:
        print(f"❌ Invalid password for user '{user}'")
        return False
    except asyncpg.exceptions.InvalidAuthorizationSpecificationError as e:
        print(f"❌ User '{user}' does not exist")
        return False
    except asyncio.TimeoutError:
        print(f"❌ Connection timeout - server might be unreachable or port blocked")
        return False
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


async def main():
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)
    
    # Configuration from .env
    configs = [
        {
            'host': os.getenv('DB_HOST', '10.8.0.1'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'fox_crypto_new'),
            'user': os.getenv('DB_USER', 'elcrypto'),
            'password': os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
        },
        # Try localhost
        {
            'host': 'localhost',
            'port': 5432,
            'database': 'fox_crypto_new',
            'user': 'elcrypto',
            'password': 'LohNeMamont@!21'
        },
        # Try with postgres user
        {
            'host': 'localhost',
            'port': 5432,
            'database': 'postgres',
            'user': 'evgeniyyanvarskiy',
            'password': ''
        }
    ]
    
    for i, config in enumerate(configs, 1):
        print(f"\n--- Test {i} ---")
        success = await test_connection(**config)
        if success:
            print("\n✅ Use this configuration in your .env file")
            break
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())