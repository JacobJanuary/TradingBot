#!/usr/bin/env python3
"""
Test script to verify order creation and response on Binance and Bybit
Tests with minimal amounts to check API behavior
"""
import asyncio
import logging
import ccxt.async_support as ccxt
from datetime import datetime, timezone
from typing import Dict, Optional
from dotenv import load_dotenv
import os
import json

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class OrderTester:
    """Test order creation and behavior"""

    def __init__(self):
        self.exchanges = {}
        self.test_symbols = {
            'binance': 'BTC/USDT:USDT',  # Binance perpetual
            'bybit': 'BTC/USDT:USDT'      # Bybit perpetual
        }

    async def setup_exchange(self, name: str):
        """Setup single exchange"""
        try:
            if name == 'binance':
                use_testnet = os.getenv('BINANCE_TESTNET', '').lower() == 'true'
                exchange = ccxt.binance({
                    'apiKey': os.getenv('BINANCE_API_KEY'),
                    'secret': os.getenv('BINANCE_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'adjustForTimeDifference': True,
                    }
                })

                if use_testnet:
                    exchange.set_sandbox_mode(True)
                    logger.info("Binance testnet mode enabled")

            elif name == 'bybit':
                use_testnet = os.getenv('BYBIT_TESTNET', '').lower() == 'true'
                exchange = ccxt.bybit({
                    'apiKey': os.getenv('BYBIT_API_KEY'),
                    'secret': os.getenv('BYBIT_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'accountType': 'UNIFIED',
                    }
                })

                if use_testnet:
                    exchange.urls['api'] = {
                        'public': 'https://api-testnet.bybit.com',
                        'private': 'https://api-testnet.bybit.com'
                    }
                    exchange.hostname = 'api-testnet.bybit.com'
                    logger.info("Bybit testnet mode enabled")

            else:
                return None

            await exchange.load_markets()
            self.exchanges[name] = exchange
            logger.info(f"✅ {name} connected")
            return exchange

        except Exception as e:
            logger.error(f"❌ {name} connection failed: {e}")
            return None

    async def test_market_order(self, exchange_name: str) -> Dict:
        """Test market order creation and response"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            await self.setup_exchange(exchange_name)
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return {'error': 'Exchange not available'}

        symbol = self.test_symbols[exchange_name]
        logger.info(f"\n{'='*40}")
        logger.info(f"Testing {exchange_name} market order for {symbol}")
        logger.info(f"{'='*40}")

        try:
            # Get market info
            market = exchange.market(symbol)
            min_amount = market['limits']['amount']['min']
            logger.info(f"Market min amount: {min_amount}")

            # Get current price
            ticker = await exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            logger.info(f"Current price: ${current_price}")

            # Calculate minimal order size
            test_amount = max(min_amount, 0.001)  # Use minimum viable amount
            logger.info(f"Test amount: {test_amount}")

            # Create market order
            logger.info(f"Creating SELL market order...")
            order = await exchange.create_market_sell_order(symbol, test_amount)

            # Log full response
            logger.info(f"Order Response:")
            logger.info(json.dumps(order, indent=2, default=str))

            # Analyze response structure
            result = {
                'exchange': exchange_name,
                'symbol': symbol,
                'order_id': order.get('id'),
                'status': order.get('status'),
                'side': order.get('side'),
                'type': order.get('type'),
                'amount': order.get('amount'),
                'filled': order.get('filled'),
                'remaining': order.get('remaining'),
                'price': order.get('price'),
                'average': order.get('average'),
                'info_keys': list(order.get('info', {}).keys()),
            }

            # Check critical fields
            logger.info("\n📋 Critical Fields Check:")
            logger.info(f"  ID present: {order.get('id') is not None}")
            logger.info(f"  Status: {order.get('status')}")
            logger.info(f"  Side: {order.get('side')}")
            logger.info(f"  Amount: {order.get('amount')}")
            logger.info(f"  Filled: {order.get('filled')}")

            # Immediately close the position to avoid loss
            logger.info(f"\n🔄 Closing position...")
            close_order = await exchange.create_market_buy_order(symbol, test_amount)
            logger.info(f"Position closed: {close_order.get('id')}")

            return result

        except Exception as e:
            logger.error(f"❌ Order test failed: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            return {'error': str(e), 'exchange': exchange_name}

    async def test_stop_loss_order(self, exchange_name: str) -> Dict:
        """Test stop-loss order creation"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return {'error': 'Exchange not available'}

        symbol = self.test_symbols[exchange_name]
        logger.info(f"\n{'='*40}")
        logger.info(f"Testing {exchange_name} stop-loss order")
        logger.info(f"{'='*40}")

        try:
            # Get current price
            ticker = await exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            logger.info(f"Current price: ${current_price}")

            # Calculate stop price (10% above for sell stop)
            stop_price = current_price * 1.1

            # Get minimum amount
            market = exchange.market(symbol)
            min_amount = market['limits']['amount']['min']
            test_amount = max(min_amount, 0.001)

            logger.info(f"Creating stop-loss order at ${stop_price}")

            # Create stop order
            params = {}
            if exchange_name == 'binance':
                params = {
                    'stopPrice': stop_price,
                    'type': 'STOP_MARKET'
                }
                order = await exchange.create_order(
                    symbol, 'STOP_MARKET', 'buy', test_amount, None, params
                )
            elif exchange_name == 'bybit':
                params = {
                    'stopLoss': stop_price,
                    'orderFilter': 'StopOrder'
                }
                order = await exchange.create_order(
                    symbol, 'market', 'buy', test_amount, None, params
                )

            logger.info(f"Stop order created: {order.get('id')}")
            logger.info(json.dumps(order, indent=2, default=str))

            # Cancel the order
            await asyncio.sleep(1)
            logger.info(f"Canceling stop order...")
            await exchange.cancel_order(order['id'], symbol)
            logger.info(f"Order canceled")

            return {
                'exchange': exchange_name,
                'order_id': order.get('id'),
                'status': order.get('status'),
                'stop_price': stop_price,
            }

        except Exception as e:
            logger.error(f"❌ Stop-loss test failed: {e}")
            return {'error': str(e), 'exchange': exchange_name}

    async def analyze_order_result(self, exchange_name: str, symbol: str):
        """Analyze OrderResult structure for specific symbol"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return

        logger.info(f"\n{'='*40}")
        logger.info(f"Analyzing {symbol} on {exchange_name}")
        logger.info(f"{'='*40}")

        try:
            # Check if market exists
            if symbol not in exchange.markets:
                # Try to find similar symbol
                similar = [s for s in exchange.markets.keys() if symbol.replace('USDT', '') in s]
                logger.warning(f"Symbol {symbol} not found. Similar: {similar[:3]}")
                if similar:
                    symbol = similar[0]
                    logger.info(f"Using {symbol} instead")
                else:
                    return

            market = exchange.market(symbol)
            logger.info(f"Market info:")
            logger.info(f"  Base: {market['base']}")
            logger.info(f"  Quote: {market['quote']}")
            logger.info(f"  Min amount: {market['limits']['amount']['min']}")
            logger.info(f"  Min cost: {market['limits']['cost']['min']}")

        except Exception as e:
            logger.error(f"Analysis failed: {e}")

    async def close_all(self):
        """Close all connections"""
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"Closed {name}")
            except:
                pass

    async def run_tests(self):
        """Run all tests"""
        results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'tests': {}
        }

        # Test Binance
        logger.info("\n" + "="*60)
        logger.info("TESTING BINANCE")
        logger.info("="*60)
        binance_result = await self.test_market_order('binance')
        results['tests']['binance_market'] = binance_result

        # Test Bybit
        logger.info("\n" + "="*60)
        logger.info("TESTING BYBIT")
        logger.info("="*60)
        bybit_result = await self.test_market_order('bybit')
        results['tests']['bybit_market'] = bybit_result

        # Analyze specific problematic symbols
        await self.analyze_order_result('bybit', 'HPOS10IUSDT')
        await self.analyze_order_result('bybit', 'PEAQUSDT')

        await self.close_all()

        # Save results
        with open('order_test_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"\nResults saved to order_test_results.json")
        return results

async def main():
    tester = OrderTester()
    await tester.run_tests()

if __name__ == "__main__":
    asyncio.run(main())