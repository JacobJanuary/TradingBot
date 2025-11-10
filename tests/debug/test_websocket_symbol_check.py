#!/usr/bin/env python3
"""
Тестовый скрипт для проверки WebSocket подписок на проблемные символы
Проверяет: BERAUSDT, CGPTUSDT

КРИТИЧЕСКАЯ ПРОБЛЕМА: Позиции открываются, но не получают обновления цены
Следствие: Trailing Stop не работает, упущенная прибыль!
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebSocketSymbolTester:
    """Test if WebSocket receives data for specific symbols"""

    def __init__(self):
        self.received_updates = {}
        self.test_symbols = ['BERAUSDT', 'CGPTUSDT', 'BTCUSDT']  # BTC as control

    async def test_binance_stream(self, symbols: list, timeout: int = 30):
        """
        Test if Binance WebSocket sends data for symbols

        Args:
            symbols: List of symbols to test
            timeout: How long to listen (seconds)
        """
        import websockets
        import json

        # Binance futures WebSocket URL
        # Format: wss://fstream.binance.com/stream?streams=symbol@markPrice
        streams = [f"{symbol.lower()}@markPrice" for symbol in symbols]
        url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

        logger.info(f"🔍 Testing WebSocket for symbols: {symbols}")
        logger.info(f"📡 Connecting to: {url}")

        for symbol in symbols:
            self.received_updates[symbol] = []

        try:
            async with websockets.connect(url) as ws:
                logger.info("✅ WebSocket connected")

                start_time = asyncio.get_event_loop().time()

                while (asyncio.get_event_loop().time() - start_time) < timeout:
                    try:
                        # Wait for message with 1s timeout
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)

                        if 'data' in data:
                            stream_name = data.get('stream', '')
                            symbol_data = data['data']

                            # Extract symbol from stream name or data
                            symbol = symbol_data.get('s', '').upper()

                            if symbol in self.test_symbols:
                                price = symbol_data.get('p', symbol_data.get('markPrice', 'N/A'))
                                self.received_updates[symbol].append(float(price) if price != 'N/A' else None)

                                logger.info(f"📊 {symbol}: {price} (update #{len(self.received_updates[symbol])})")

                    except asyncio.TimeoutError:
                        # No message in 1s, continue waiting
                        continue
                    except Exception as e:
                        logger.error(f"Error receiving message: {e}")
                        continue

        except Exception as e:
            logger.error(f"❌ WebSocket connection error: {e}")
            return False

        # Analyze results
        logger.info("\n" + "="*60)
        logger.info("📊 TEST RESULTS")
        logger.info("="*60)

        for symbol in symbols:
            update_count = len(self.received_updates.get(symbol, []))

            if update_count > 0:
                logger.info(f"✅ {symbol}: {update_count} updates received")

                if update_count >= 3:
                    prices = self.received_updates[symbol][:5]
                    logger.info(f"   Sample prices: {prices}")
            else:
                logger.error(f"❌ {symbol}: NO UPDATES RECEIVED!")
                logger.error(f"   ⚠️  CRITICAL: This symbol may be delisted or not available")

        logger.info("="*60)

        return True

    async def check_symbol_on_binance_api(self, symbol: str):
        """Check if symbol exists and is tradable via REST API"""
        import requests

        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        logger.info(f"\n🔍 Checking {symbol} on Binance API...")

        try:
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}")
                return

            data = response.json()

            # Find symbol in exchange info
            for sym_info in data.get('symbols', []):
                if sym_info['symbol'] == symbol:
                    status = sym_info.get('status', 'UNKNOWN')
                    contract_type = sym_info.get('contractType', 'UNKNOWN')

                    logger.info(f"✅ {symbol} found:")
                    logger.info(f"   Status: {status}")
                    logger.info(f"   Contract: {contract_type}")
                    logger.info(f"   Quote Asset: {sym_info.get('quoteAsset', 'N/A')}")

                    if status != 'TRADING':
                        logger.error(f"   ❌ Symbol status is '{status}' (not TRADING)!")
                        logger.error(f"   ⚠️  This explains missing WebSocket updates!")

                    return sym_info

            logger.error(f"❌ {symbol} NOT FOUND in exchange info!")
            logger.error(f"   ⚠️  Symbol may be delisted!")

        except Exception as e:
            logger.error(f"Error checking API: {e}")


async def main():
    """Main test function"""
    tester = WebSocketSymbolTester()

    logger.info("="*60)
    logger.info("🔬 WEBSOCKET SYMBOL CHECK - CRITICAL INVESTIGATION")
    logger.info("="*60)
    logger.info("Problem: BERAUSDT and CGPTUSDT positions opened but NO price updates")
    logger.info("Result: Trailing stop doesn't work, missed profit!")
    logger.info("="*60 + "\n")

    # Step 1: Check symbols on API
    for symbol in ['BERAUSDT', 'CGPTUSDT']:
        await tester.check_symbol_on_binance_api(symbol)

    # Step 2: Test WebSocket stream
    logger.info("\n" + "="*60)
    logger.info("Testing WebSocket streams (30 seconds)...")
    logger.info("="*60 + "\n")

    await tester.test_binance_stream(tester.test_symbols, timeout=30)

    logger.info("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
