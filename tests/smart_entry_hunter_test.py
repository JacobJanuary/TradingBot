#!/usr/bin/env python3
"""
Smart Entry Hunter - Standalone Test Script

Tests the Smart Entry Hunter logic without integrating into the bot.
Monitors 1-30 pairs concurrently and reports when entry criteria are met.

Usage:
    python tests/smart_entry_hunter_test.py LSKUSDT ORCAUSDT API3USDT GPSUSDT IOSTUSDT
    
    or
    
    python tests/smart_entry_hunter_test.py --pairs LSKUSDT,ORCAUSDT,API3USDT
    
Environment:
    Requires .env file with Binance credentials:
    BINANCE_API_KEY=...
    BINANCE_API_SECRET=...
    MAX_CONCURRENT_HUNTERS=30 (optional, default 30)
"""
import asyncio
import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Import CCXT
import ccxt.async_support as ccxt_async

# Import Smart Entry Hunter
from core.smart_entry_hunter import (
    launch_hunter,
    get_hunter_registry,
    HunterRegistry
)

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/smart_entry_test.log')
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# MOCK EXCHANGE MANAGER
# ============================================================

class MockExchangeManager:
    """
    Minimal exchange manager for testing
    Only needs to support fetch_ohlcv
    """
    
    def __init__(self, exchange):
        self.exchange = exchange
        self.markets = {}
    
    async def initialize(self):
        """Load markets"""
        await self.exchange.load_markets()
        self.markets = self.exchange.markets
        logger.info(f"Loaded {len(self.markets)} markets")
    
    def find_exchange_symbol(self, symbol: str) -> str:
        """
        Find exchange-specific symbol format
        
        Args:
            symbol: Database format (e.g., 'LSKUSDT')
        
        Returns:
            Exchange format (e.g., 'LSK/USDT:USDT' for perpetual)
        """
        # Try exact match
        if symbol in self.markets:
            return symbol
        
        # Try with /USDT suffix
        with_slash = symbol.replace('USDT', '/USDT')
        if with_slash in self.markets:
            return with_slash
        
        # Try perpetual format
        perp_format = symbol.replace('USDT', '/USDT:USDT')
        if perp_format in self.markets:
            return perp_format
        
        logger.warning(f"Symbol {symbol} not found in markets, using as-is")
        return symbol
    
    async def close(self):
        """Close exchange connection"""
        await self.exchange.close()


# ============================================================
# TEST ORCHESTRATOR
# ============================================================

class SmartEntryTest:
    """
    Orchestrates Smart Entry Hunter testing
    """
    
    def __init__(self, pairs: List[str], exchange_id: str = 'binance'):
        self.pairs = pairs
        self.exchange_id = exchange_id
        self.exchange_manager = None
        self.registry = get_hunter_registry()
        self.results = {}
    
    async def setup(self):
        """Initialize exchange connection"""
        logger.info("=" * 80)
        logger.info("SMART ENTRY HUNTER - TEST MODE")
        logger.info("=" * 80)
        
        # Create Binance exchange
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            raise ValueError(
                "Binance credentials not found in .env file. "
                "Please add BINANCE_API_KEY and BINANCE_API_SECRET"
            )
        
        exchange = ccxt_async.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # Use futures market
            }
        })
        
        self.exchange_manager = MockExchangeManager(exchange)
        await self.exchange_manager.initialize()
        
        logger.info(f"✅ Exchange initialized: {self.exchange_id}")
        logger.info(f"📊 Testing {len(self.pairs)} pairs: {', '.join(self.pairs)}")
        logger.info(f"🎯 Max concurrent hunters: {self.registry.max_concurrent}")
    
    async def run_test(self):
        """
        Launch hunters for all pairs and monitor results
        """
        logger.info("=" * 80)
        logger.info("LAUNCHING HUNTERS")
        logger.info("=" * 80)
        
        # Launch hunters for each pair
        tasks = []
        for symbol in self.pairs:
            # Create mock signal
            signal = {
                'id': None,
                'symbol': symbol,
                'exchange': self.exchange_id,
                'recommended_action': 'BUY',
                'signal_type': 'BUY'
            }
            
            # Launch hunter (position_manager=None for test mode)
            task = launch_hunter(
                signal=signal,
                exchange_manager=self.exchange_manager,
                position_manager=None  # Test mode: no actual position opening
            )
            
            if task:
                tasks.append(task)
                logger.info(f"🎯 Hunter launched for {symbol}")
            else:
                logger.warning(f"⚠️ Failed to launch hunter for {symbol}")
        
        logger.info("=" * 80)
        logger.info(f"MONITORING {len(tasks)} HUNTERS")
        logger.info("Press Ctrl+C to stop early")
        logger.info("=" * 80)
        
        # Monitor and wait for completion
        try:
            while tasks:
                # Wait for any task to complete
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=10,  # Check every 10 seconds
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process completed tasks
                for task in done:
                    try:
                        result = task.result()
                        symbol = result.get('symbol')
                        status = result.get('status')
                        
                        self.results[symbol] = result
                        
                        if status == 'entered':
                            logger.info(
                                f"🎉 ENTRY SIGNAL: {symbol} - {result.get('reason')}"
                            )
                            logger.info(
                                f"   Price: ${result.get('price'):.4f} "
                                f"after {result.get('iterations')} iterations"
                            )
                        elif status == 'timeout':
                            logger.info(
                                f"⏱️ TIMEOUT: {symbol} - No entry found after 30 min "
                                f"({result.get('iterations')} checks)"
                            )
                        elif status == 'error':
                            logger.error(
                                f"❌ ERROR: {symbol} - {result.get('error')}"
                            )
                    
                    except Exception as e:
                        logger.error(f"Error processing task result: {e}")
                
                # Update task list
                tasks = list(pending)
                
                # Log progress
                if tasks:
                    stats = self.registry.get_stats()
                    logger.info(
                        f"📊 Progress: {stats['active_hunters']} active, "
                        f"{stats['entered']} entered, "
                        f"{stats['timeout']} timeout"
                    )
        
        except KeyboardInterrupt:
            logger.info("\n\n⚠️ Test interrupted by user")
            # Cancel remaining tasks
            for task in tasks:
                task.cancel()
            
            # Wait for cancellation
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def print_summary(self):
        """Print test summary"""
        logger.info("=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        
        stats = self.registry.get_stats()
        
        logger.info(f"Total pairs tested: {len(self.pairs)}")
        logger.info(f"Entry signals found: {stats['entered']}")
        logger.info(f"Timeouts: {stats['timeout']}")
        logger.info(f"Errors: {stats['errors']}")
        
        logger.info("\nResults by pair:")
        for symbol, result in self.results.items():
            status = result.get('status')
            if status == 'entered':
                logger.info(
                    f"  ✅ {symbol}: ENTRY at ${result.get('price'):.4f} "
                    f"- {result.get('reason')[:60]}..."
                )
            elif status == 'timeout':
                logger.info(f"  ⏱️ {symbol}: TIMEOUT after {result.get('iterations')} checks")
            elif status == 'error':
                logger.info(f"  ❌ {symbol}: ERROR - {result.get('error')}")
        
        logger.info("=" * 80)
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.exchange_manager:
            await self.exchange_manager.close()
            logger.info("✅ Exchange connection closed")


# ============================================================
# MAIN
# ============================================================

async def main():
    """Main test entry point"""
    parser = argparse.ArgumentParser(
        description='Test Smart Entry Hunter with live market data'
    )
    parser.add_argument(
        'pairs',
        nargs='*',
        help='Trading pairs to test (e.g., LSKUSDT ORCAUSDT)'
    )
    parser.add_argument(
        '--pairs',
        dest='pairs_comma',
        help='Comma-separated trading pairs (e.g., LSKUSDT,ORCAUSDT)'
    )
    parser.add_argument(
        '--exchange',
        default='binance',
        help='Exchange to use (default: binance)'
    )
    
    args = parser.parse_args()
    
    # Parse pairs
    if args.pairs_comma:
        pairs = [p.strip() for p in args.pairs_comma.split(',')]
    elif args.pairs:
        pairs = args.pairs
    else:
        # Default test pairs
        pairs = ['LSKUSDT', 'ORCAUSDT', 'API3USDT', 'GPSUSDT', 'IOSTUSDT']
    
    # Create test
    test = SmartEntryTest(pairs=pairs, exchange_id=args.exchange)
    
    try:
        # Setup
        await test.setup()
        
        # Run test
        await test.run_test()
        
        # Summary
        await test.print_summary()
    
    finally:
        await test.cleanup()


if __name__ == '__main__':
    # Ensure logs directory exists
    Path('logs').mkdir(exist_ok=True)
    
    # Run test
    asyncio.run(main())
