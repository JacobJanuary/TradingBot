#!/usr/bin/env python3
"""
ТЕСТ ПЕРЕПОДКЛЮЧЕНИЙ: Optimistic Subscribe
Подписываемся быстро (оптимистично), проверяем данные в фоне, повторяем неудачные
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import aiohttp
from typing import Dict, Set

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class OptimisticReconnectionTester:
    """Test reconnection with optimistic subscribe + background verification"""

    def __init__(self, symbols: list, reconnect_interval: int = 120):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.symbols = symbols
        self.reconnect_interval = reconnect_interval

        # Statistics
        self.cycle_count = 0
        self.total_subscriptions = 0
        self.total_resubscriptions = 0
        self.total_verified = 0
        self.total_permanent_fails = 0

        # Current cycle data
        self.next_id = 1
        self.last_data_time: Dict[str, float] = {}

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        print(f"{timestamp} | {message}")

    async def subscribe_all_fast(self, ws) -> Set[str]:
        """Subscribe to all symbols FAST (optimistic - don't wait for verification)"""
        self.log(f"📤 Subscribing to {len(self.symbols)} symbols (OPTIMISTIC - fast)...")

        for symbol in self.symbols:
            stream_name = f"{symbol.lower()}@markPrice@1s"
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [stream_name],
                "id": self.next_id
            }

            await ws.send_str(json.dumps(subscribe_msg))
            self.next_id += 1
            self.total_subscriptions += 1

            await asyncio.sleep(0.05)  # Minimal delay (50ms vs 100ms)

        self.log(f"✅ All SUBSCRIBE sent ({len(self.symbols)} symbols)")
        return set(self.symbols)

    async def verify_subscriptions(self, ws, symbols: Set[str], timeout: float = 15.0) -> Dict[str, bool]:
        """
        Verify subscriptions in BACKGROUND by checking data arrival

        This runs AFTER subscribing, doesn't block subscription process
        """
        self.log(f"🔍 Verifying subscriptions (waiting {timeout}s for data)...")

        verified = set()
        start_time = asyncio.get_event_loop().time()
        deadline = start_time + timeout

        while asyncio.get_event_loop().time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    # Mark price update
                    if 'e' in data and data['e'] == 'markPriceUpdate':
                        symbol = data['s']
                        if symbol in symbols:
                            verified.add(symbol)
                            self.last_data_time[symbol] = asyncio.get_event_loop().time()

                            # Log first verification
                            if len(verified) == 1 or len(verified) % 5 == 0:
                                self.log(f"   ✅ Verified {len(verified)}/{len(symbols)} symbols...")

            except asyncio.TimeoutError:
                continue

        failed = symbols - verified
        self.total_verified += len(verified)

        self.log(f"📊 Verification complete: {len(verified)}/{len(symbols)} verified")
        if failed:
            self.log(f"   ⚠️  {len(failed)} symbols failed verification")

        return {s: s in verified for s in symbols}

    async def resubscribe_failed(self, ws, failed_symbols: Set[str]) -> Set[str]:
        """Resubscribe to failed symbols (one retry)"""
        if not failed_symbols:
            return set()

        self.log(f"🔄 Resubscribing to {len(failed_symbols)} failed symbols...")

        for symbol in failed_symbols:
            stream_name = f"{symbol.lower()}@markPrice@1s"
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [stream_name],
                "id": self.next_id
            }

            await ws.send_str(json.dumps(subscribe_msg))
            self.next_id += 1
            self.total_resubscriptions += 1

            await asyncio.sleep(0.1)

        # Verify resubscriptions (shorter timeout)
        self.log(f"🔍 Verifying resubscriptions (10s timeout)...")
        verified = set()
        timeout_time = asyncio.get_event_loop().time() + 10.0

        while asyncio.get_event_loop().time() < timeout_time:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    if 'e' in data and data['e'] == 'markPriceUpdate':
                        symbol = data['s']
                        if symbol in failed_symbols:
                            verified.add(symbol)
                            self.last_data_time[symbol] = asyncio.get_event_loop().time()

            except asyncio.TimeoutError:
                continue

        still_failed = failed_symbols - verified
        self.total_verified += len(verified)
        self.total_permanent_fails += len(still_failed)

        self.log(f"📊 Resubscription: {len(verified)}/{len(failed_symbols)} recovered")
        if still_failed:
            self.log(f"   ❌ Permanent fails: {sorted(still_failed)}")

        return verified

    async def monitor_data(self, ws, duration: float) -> Set[str]:
        """Monitor data and detect stale subscriptions"""
        self.log(f"👁️  Monitoring for {duration:.0f} seconds...")

        data_symbols = set()
        timeout_time = asyncio.get_event_loop().time() + duration

        while asyncio.get_event_loop().time() < timeout_time:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    if 'e' in data and data['e'] == 'markPriceUpdate':
                        symbol = data['s']
                        data_symbols.add(symbol)
                        self.last_data_time[symbol] = asyncio.get_event_loop().time()

            except asyncio.TimeoutError:
                continue

        return data_symbols

    async def run_cycle(self):
        """Run one connection cycle"""
        self.cycle_count += 1
        self.log(f"\n{'='*80}")
        self.log(f"🔄 CYCLE #{self.cycle_count}")
        self.log(f"{'='*80}")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                self.log(f"✅ WebSocket connected")

                # Phase 1: Subscribe FAST (optimistic)
                subscribed = await self.subscribe_all_fast(ws)

                # Phase 2: Verify in background (15s timeout)
                results = await self.verify_subscriptions(ws, subscribed, timeout=15.0)

                failed_symbols = {s for s, ok in results.items() if not ok}

                # Phase 3: Retry failed subscriptions (if any)
                if failed_symbols:
                    recovered = await self.resubscribe_failed(ws, failed_symbols)
                    # Update results
                    for symbol in recovered:
                        results[symbol] = True
                else:
                    recovered = set()

                # Final stats
                verified = {s for s, ok in results.items() if ok}
                permanent_fails = {s for s, ok in results.items() if not ok}

                self.log(f"\n📊 CYCLE #{self.cycle_count} RESULTS:")
                self.log(f"   Subscribed: {len(self.symbols)}")
                self.log(f"   Verified (1st try): {len(verified) - len(recovered)}")
                self.log(f"   Recovered (2nd try): {len(recovered)}")
                self.log(f"   Total verified: {len(verified)}")
                self.log(f"   Permanent fails: {len(permanent_fails)}")

                if permanent_fails:
                    self.log(f"   ❌ Failed symbols: {sorted(permanent_fails)}")

                success_rate = (len(verified) / len(self.symbols)) * 100
                self.log(f"   Success rate: {success_rate:.1f}%")

                # Monitor remaining time
                remaining = self.reconnect_interval - 30  # rough estimate
                if remaining > 0:
                    self.log(f"\n⏳ Monitoring for {remaining}s before reconnection...")
                    data_symbols = await self.monitor_data(ws, remaining)

                    # Check for stale
                    current_time = asyncio.get_event_loop().time()
                    stale = []
                    for symbol in verified:
                        last = self.last_data_time.get(symbol, 0)
                        if current_time - last > 30:
                            stale.append(symbol)

                    if stale:
                        self.log(f"   ⚠️  Stale subscriptions: {stale}")

                await ws.close()

    async def run(self, num_cycles: int = 5):
        """Run multiple reconnection cycles"""
        self.log(f"\n{'='*80}")
        self.log(f"OPTIMISTIC SUBSCRIBE RECONNECTION TEST")
        self.log(f"{'='*80}")
        self.log(f"Symbols: {len(self.symbols)}")
        self.log(f"Reconnect interval: {self.reconnect_interval}s")
        self.log(f"Target cycles: {num_cycles}")
        self.log(f"Total duration: ~{(num_cycles * self.reconnect_interval) / 60:.1f} minutes")

        start_time = asyncio.get_event_loop().time()

        for i in range(num_cycles):
            try:
                await self.run_cycle()
            except Exception as e:
                self.log(f"❌ ERROR in cycle {i+1}: {e}")
                import traceback
                traceback.print_exc()

            if i < num_cycles - 1:
                await asyncio.sleep(2.0)

        # Final statistics
        elapsed = asyncio.get_event_loop().time() - start_time

        self.log(f"\n{'='*80}")
        self.log(f"📊 FINAL STATISTICS")
        self.log(f"{'='*80}")
        self.log(f"Total duration: {elapsed/60:.1f} minutes")
        self.log(f"Completed cycles: {self.cycle_count}")
        self.log(f"Total subscriptions: {self.total_subscriptions}")
        self.log(f"Total resubscriptions: {self.total_resubscriptions}")
        self.log(f"Total verified: {self.total_verified}")
        self.log(f"Total permanent fails: {self.total_permanent_fails}")

        expected = self.cycle_count * len(self.symbols)
        if expected > 0:
            success_rate = (self.total_verified / expected) * 100
            self.log(f"Overall success rate: {success_rate:.1f}%")
            self.log(f"Permanent fail rate: {(self.total_permanent_fails / expected) * 100:.1f}%")


async def main():
    test_symbols = [
        'VFYUSDT', 'NOTUSDT', 'THETAUSDT', 'ANIMEUSDT',
        'GLMUSDT', 'POLUSDT', 'BASUSDT', 'C98USDT',
        'EULUSDT', 'SKLUSDT', 'HOOKUSDT', 'ONGUSDT',
        'LUNA2USDT', 'DOGEUSDT', 'RSRUSDT'
    ]

    tester = OptimisticReconnectionTester(
        symbols=test_symbols,
        reconnect_interval=120
    )

    await tester.run(num_cycles=5)


if __name__ == "__main__":
    asyncio.run(main())
