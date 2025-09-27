#!/usr/bin/env python3
"""
Pre-start system check script
Verifies all dependencies and connections before starting the trading bot
"""

import sys
import asyncio
import asyncpg
import ccxt
from loguru import logger
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def check_database():
    """Check database connectivity"""
    try:
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        version = await conn.fetchval('SELECT version()')
        logger.info(f"✓ Database connected: {version[:30]}...")
        
        # Check required schemas
        schemas = await conn.fetch("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('fas', 'monitoring')")
        if len(schemas) != 2:
            logger.error("✗ Required database schemas missing")
            return False
            
        await conn.close()
        return True
    except Exception as e:
        logger.error(f"✗ Database check failed: {e}")
        return False

async def check_exchanges():
    """Check exchange API connectivity"""
    results = []
    
    # Check Binance
    if os.getenv('BINANCE_API_KEY'):
        try:
            exchange = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY'),
                'secret': os.getenv('BINANCE_API_SECRET'),
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            
            # Test public endpoint
            await exchange.fetch_ticker('BTC/USDT')
            
            # Test private endpoint
            balance = await exchange.fetch_balance()
            
            logger.info(f"✓ Binance connected")
            results.append(True)
        except Exception as e:
            logger.error(f"✗ Binance check failed: {e}")
            results.append(False)
    
    # Check Bybit
    if os.getenv('BYBIT_API_KEY'):
        try:
            exchange = ccxt.bybit({
                'apiKey': os.getenv('BYBIT_API_KEY'),
                'secret': os.getenv('BYBIT_API_SECRET'),
                'enableRateLimit': True
            })
            
            # Test public endpoint
            await exchange.fetch_ticker('BTC/USDT')
            
            logger.info(f"✓ Bybit connected")
            results.append(True)
        except Exception as e:
            logger.error(f"✗ Bybit check failed: {e}")
            results.append(False)
    
    return all(results) if results else False

def check_directories():
    """Check required directories exist"""
    required_dirs = [
        'logs',
        'reports',
        'backups',
        'config'
    ]
    
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            try:
                os.makedirs(dir_name, exist_ok=True)
                logger.info(f"✓ Created directory: {dir_name}")
            except Exception as e:
                logger.error(f"✗ Failed to create directory {dir_name}: {e}")
                return False
        else:
            logger.info(f"✓ Directory exists: {dir_name}")
    
    return True

def check_config():
    """Check configuration files"""
    config_files = [
        'config/config.yaml',
        '.env'
    ]
    
    for config_file in config_files:
        if not os.path.exists(config_file):
            logger.error(f"✗ Configuration file missing: {config_file}")
            return False
        logger.info(f"✓ Configuration file found: {config_file}")
    
    return True

async def main():
    """Run all pre-start checks"""
    logger.info("=" * 50)
    logger.info("Running pre-start checks...")
    logger.info("=" * 50)
    
    checks = [
        ("Configuration", check_config()),
        ("Directories", check_directories()),
        ("Database", await check_database()),
        ("Exchanges", await check_exchanges())
    ]
    
    all_passed = all(check[1] for check in checks)
    
    logger.info("=" * 50)
    if all_passed:
        logger.success("All checks passed! System ready to start.")
        sys.exit(0)
    else:
        logger.error("Some checks failed. Please fix the issues before starting.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())