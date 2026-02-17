"""
Staging canary test: Verify per-symbol WebSocket connections to Binance

Run on the server BEFORE deploying to production:
    python scripts/test_per_symbol_ws.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --duration 30

What it tests:
1. Each symbol connects independently
2. Data arrives at ~1s intervals
3. Adding a 4th symbol mid-test has zero impact on existing 3
4. Removing a symbol has zero impact on remaining ones
"""

import asyncio
import argparse
import logging
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websocket.mark_price_per_symbol_pool import MarkPricePerSymbolPool

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)


class CanaryTest:
    """Live canary test for per-symbol WS connections"""

    def __init__(self, symbols: list, duration: int):
        self.initial_symbols = symbols
        self.duration = duration
        self.received: dict = {}  # symbol → list of timestamps
        self.pool = MarkPricePerSymbolPool(
            on_price_update=self._on_price_update,
            frequency="1s",
        )

    async def _on_price_update(self, data: dict):
        symbol = data.get('s', 'UNKNOWN')
        price = data.get('p', '?')
        now = time.monotonic()

        if symbol not in self.received:
            self.received[symbol] = []
        self.received[symbol].append(now)

        # Log every 5th message to avoid spam
        if len(self.received[symbol]) % 5 == 1:
            logger.info(
                f"📊 {symbol}: price={price}, "
                f"messages={len(self.received[symbol])}"
            )

    async def run(self):
        logger.info("=" * 60)
        logger.info("🚀 Per-Symbol WebSocket Canary Test")
        logger.info(f"   Symbols: {self.initial_symbols}")
        logger.info(f"   Duration: {self.duration}s")
        logger.info("=" * 60)

        # Phase 1: Connect initial symbols
        logger.info("\n📌 Phase 1: Connecting initial symbols...")
        await self.pool.set_symbols(set(self.initial_symbols))
        await asyncio.sleep(5)

        status = self.pool.get_status()
        logger.info(f"   Connected: {status['connected_count']}/{status['total_connections']}")

        # Phase 2: Run for half duration and verify data flow
        logger.info(f"\n📌 Phase 2: Monitoring for {self.duration // 2}s...")
        await asyncio.sleep(self.duration // 2)

        # Phase 3: Add a new symbol mid-test
        add_symbol = "XRPUSDT"
        if add_symbol not in self.initial_symbols:
            logger.info(f"\n📌 Phase 3: Adding {add_symbol} (should have ZERO impact on others)...")
            pre_add_counts = {s: len(self.received.get(s, [])) for s in self.initial_symbols}
            await self.pool.add_symbol(add_symbol)
            await asyncio.sleep(5)

            # Verify existing symbols still flowing
            for s in self.initial_symbols:
                new_count = len(self.received.get(s, []))
                delta = new_count - pre_add_counts[s]
                impact = "✅ OK" if delta >= 3 else "❌ DISRUPTED"
                logger.info(f"   {s}: +{delta} messages during add → {impact}")

        # Phase 4: Remove first symbol
        remove_symbol = self.initial_symbols[0]
        logger.info(f"\n📌 Phase 4: Removing {remove_symbol} (should have ZERO impact on others)...")
        remaining = [s for s in self.initial_symbols if s != remove_symbol]
        pre_remove_counts = {s: len(self.received.get(s, [])) for s in remaining}
        await self.pool.remove_symbol(remove_symbol)
        await asyncio.sleep(5)

        for s in remaining:
            new_count = len(self.received.get(s, []))
            delta = new_count - pre_remove_counts[s]
            impact = "✅ OK" if delta >= 3 else "❌ DISRUPTED"
            logger.info(f"   {s}: +{delta} messages during remove → {impact}")

        # Phase 5: Wait remaining duration
        remaining_time = max(0, self.duration - self.duration // 2 - 10)
        if remaining_time > 0:
            logger.info(f"\n📌 Phase 5: Monitoring remaining {remaining_time}s...")
            await asyncio.sleep(remaining_time)

        # Final report
        await self.pool.stop()
        self._print_report()

    def _print_report(self):
        logger.info("\n" + "=" * 60)
        logger.info("📋 CANARY TEST REPORT")
        logger.info("=" * 60)

        all_pass = True
        for symbol, timestamps in sorted(self.received.items()):
            count = len(timestamps)
            if count >= 2:
                # Average interval between messages
                intervals = [
                    timestamps[i] - timestamps[i-1]
                    for i in range(1, len(timestamps))
                ]
                avg_interval = sum(intervals) / len(intervals)
                max_gap = max(intervals)
                interval_ok = "✅" if avg_interval < 2.0 else "❌"
                gap_ok = "✅" if max_gap < 5.0 else "❌"
                logger.info(
                    f"   {symbol}: {count} msgs, "
                    f"avg interval={avg_interval:.2f}s {interval_ok}, "
                    f"max gap={max_gap:.2f}s {gap_ok}"
                )
                if avg_interval >= 2.0 or max_gap >= 5.0:
                    all_pass = False
            else:
                logger.info(f"   {symbol}: {count} msgs ❌ (too few)")
                all_pass = False

        logger.info("-" * 60)
        if all_pass:
            logger.info("✅ ALL CHECKS PASSED — ready for production deploy")
        else:
            logger.info("❌ SOME CHECKS FAILED — do NOT deploy")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Per-symbol WS canary test")
    parser.add_argument(
        "--symbols",
        type=str,
        default="BTCUSDT,ETHUSDT,SOLUSDT",
        help="Comma-separated symbols to test",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Test duration in seconds",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    test = CanaryTest(symbols=symbols, duration=args.duration)

    try:
        asyncio.run(test.run())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Test interrupted by user")


if __name__ == "__main__":
    main()
