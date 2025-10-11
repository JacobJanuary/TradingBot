#!/usr/bin/env python3
"""
Test script to check open positions on Binance and Bybit
"""
import asyncio
import logging
import ccxt.async_support as ccxt
from datetime import datetime, timezone
from typing import Dict, List
from dotenv import load_dotenv
import os
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class PositionChecker:
    """Check positions on exchanges"""

    def __init__(self):
        self.exchanges = {}

    async def setup_exchanges(self):
        """Initialize exchange connections"""
        # Check for testnet mode
        use_testnet = os.getenv('BINANCE_TESTNET', '').lower() == 'true'

        # Setup Binance
        try:
            self.exchanges['binance'] = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY'),
                'secret': os.getenv('BINANCE_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use futures market
                    'adjustForTimeDifference': True,
                }
            })

            # Enable testnet if configured
            if use_testnet:
                self.exchanges['binance'].set_sandbox_mode(True)
                logger.info("Binance testnet mode enabled")

            await self.exchanges['binance'].load_markets()
            logger.info("✅ Binance connected")
        except Exception as e:
            logger.error(f"❌ Binance connection failed: {e}")

        # Setup Bybit
        use_bybit_testnet = os.getenv('BYBIT_TESTNET', '').lower() == 'true'

        try:
            self.exchanges['bybit'] = ccxt.bybit({
                'apiKey': os.getenv('BYBIT_API_KEY'),
                'secret': os.getenv('BYBIT_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Changed to future for consistency
                    'accountType': 'UNIFIED',  # V5 API requires UNIFIED account
                }
            })

            # Enable testnet if configured
            if use_bybit_testnet:
                self.exchanges['bybit'].urls['api'] = {
                    'public': 'https://api-testnet.bybit.com',
                    'private': 'https://api-testnet.bybit.com'
                }
                self.exchanges['bybit'].hostname = 'api-testnet.bybit.com'
                logger.info("Bybit testnet mode enabled")

            await self.exchanges['bybit'].load_markets()
            logger.info("✅ Bybit connected")
        except Exception as e:
            logger.error(f"❌ Bybit connection failed: {e}")

    async def check_positions(self, exchange_name: str) -> List[Dict]:
        """Check open positions on an exchange"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            logger.error(f"Exchange {exchange_name} not available")
            return []

        try:
            # Fetch positions
            positions = await exchange.fetch_positions()

            if not positions:
                logger.info(f"📊 {exchange_name}: No open positions")
                return []

            logger.info(f"📊 {exchange_name}: Found {len(positions)} positions")

            result = []
            for pos in positions:
                if pos['contracts'] > 0:  # Only active positions
                    position_info = {
                        'symbol': pos['symbol'],
                        'side': pos['side'],
                        'contracts': pos['contracts'],
                        'percentage': pos['percentage'],
                        'unrealizedPnl': pos['unrealizedPnl'],
                        'markPrice': pos['markPrice'],
                        'entryPrice': pos.get('info', {}).get('avgPrice'),
                    }
                    result.append(position_info)

                    logger.info(f"  └─ {pos['symbol']}: {pos['side']} {pos['contracts']} contracts")
                    logger.info(f"     Entry: {position_info['entryPrice']}, Mark: {pos['markPrice']}")
                    logger.info(f"     PnL: ${pos['unrealizedPnl']:.2f} ({pos['percentage']:.2f}%)")

            return result

        except Exception as e:
            logger.error(f"❌ Error checking {exchange_name} positions: {e}")
            return []

    async def check_open_orders(self, exchange_name: str) -> List[Dict]:
        """Check open orders (including stop-loss)"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return []

        try:
            # Fetch all open orders
            orders = await exchange.fetch_open_orders()

            if not orders:
                logger.info(f"📋 {exchange_name}: No open orders")
                return []

            logger.info(f"📋 {exchange_name}: Found {len(orders)} open orders")

            result = []
            for order in orders:
                order_info = {
                    'id': order['id'],
                    'symbol': order['symbol'],
                    'type': order['type'],
                    'side': order['side'],
                    'price': order['price'],
                    'amount': order['amount'],
                    'status': order['status'],
                    'stopPrice': order.get('stopPrice'),
                }
                result.append(order_info)

                if order.get('stopPrice'):
                    logger.info(f"  └─ SL Order: {order['symbol']} {order['side']} @ {order['stopPrice']}")
                else:
                    logger.info(f"  └─ {order['type']}: {order['symbol']} {order['side']} {order['amount']} @ {order['price']}")

            return result

        except Exception as e:
            logger.error(f"❌ Error checking {exchange_name} orders: {e}")
            return []

    async def check_balance(self, exchange_name: str):
        """Check account balance"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return

        try:
            balance = await exchange.fetch_balance()

            # Find USDT balance
            usdt = balance.get('USDT', {})
            if usdt:
                logger.info(f"💰 {exchange_name} Balance:")
                logger.info(f"   USDT Total: ${usdt.get('total', 0):.2f}")
                logger.info(f"   USDT Free: ${usdt.get('free', 0):.2f}")
                logger.info(f"   USDT Used: ${usdt.get('used', 0):.2f}")

        except Exception as e:
            logger.error(f"❌ Error checking {exchange_name} balance: {e}")

    async def close_all(self):
        """Close all exchange connections"""
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"Closed {name} connection")
            except:
                pass

    async def run_full_check(self):
        """Run complete position check"""
        logger.info("="*60)
        logger.info("🔍 STARTING POSITION CHECK")
        logger.info("="*60)

        await self.setup_exchanges()

        all_positions = {}
        all_orders = {}

        for exchange_name in ['binance', 'bybit']:
            logger.info(f"\n{'='*30} {exchange_name.upper()} {'='*30}")

            # Check balance
            await self.check_balance(exchange_name)

            # Check positions
            positions = await self.check_positions(exchange_name)
            if positions:
                all_positions[exchange_name] = positions

            # Check orders
            orders = await self.check_open_orders(exchange_name)
            if orders:
                all_orders[exchange_name] = orders

            logger.info("")

        # Summary
        logger.info("="*60)
        logger.info("📊 SUMMARY")
        logger.info("="*60)

        total_positions = sum(len(pos) for pos in all_positions.values())
        total_orders = sum(len(ord) for ord in all_orders.values())

        logger.info(f"Total open positions: {total_positions}")
        logger.info(f"Total open orders: {total_orders}")

        if all_positions:
            logger.info("\n📍 Active Positions:")
            for exchange, positions in all_positions.items():
                for pos in positions:
                    logger.info(f"  • {exchange}: {pos['symbol']} {pos['side']}")

        if all_orders:
            logger.info("\n⏱️ Open Orders:")
            for exchange, orders in all_orders.items():
                for order in orders:
                    if order.get('stopPrice'):
                        logger.info(f"  • {exchange}: SL for {order['symbol']} @ {order['stopPrice']}")

        await self.close_all()

        return {
            'positions': all_positions,
            'orders': all_orders,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

async def main():
    checker = PositionChecker()
    result = await checker.run_full_check()

    # Save result to file
    with open('positions_check_result.json', 'w') as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"\nResults saved to positions_check_result.json")

if __name__ == "__main__":
    asyncio.run(main())