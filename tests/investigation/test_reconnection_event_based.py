#!/usr/bin/env python3
"""
ТЕСТ ПЕРЕПОДКЛЮЧЕНИЙ: Event-Based верификация
Используем asyncio.Event() для неблокирующей верификации подписок
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


class EventBasedReconnectionTester:
    """Test reconnection with event-based verification (non-blocking)"""

    def __init__(self, symbols: list, reconnect_interval: int = 120):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.symbols = symbols
        self.reconnect_interval = reconnect_interval

        # Statistics
        self.cycle_count = 0
        self.total_subscriptions = 0
        self.total_verified = 0
        self.total_silent_fails = 0
        self.total_timeouts = 0

        # Current cycle data
        self.next_id = 1
        self.subscription_events: Dict[str, asyncio.Event] = {}
        self.subscription_responses: Dict[int, str] = {}
        self.last_data_time: Dict[str, float] = {}

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        print(f"{timestamp} | {message}")

    async def message_handler(self, ws):
        """Handle all incoming messages (runs in background)"""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    # Subscription response
                    if 'id' in data and 'result' in data:
                        req_id = data['id']
                        if req_id in self.subscription_responses:
                            symbol = self.subscription_responses[req_id]
                            # Response received, but we still wait for data

                    # Mark price update - TRIGGER EVENT
                    elif 'e' in data and data['e'] == 'markPriceUpdate':
                        symbol = data['s']
                        self.last_data_time[symbol] = asyncio.get_event_loop().time()

                        # Set event if waiting for this symbol
                        if symbol in self.subscription_events:
                            self.subscription_events[symbol].set()

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log(f"❌ WebSocket error: {msg.data}")
                    break

        except Exception as e:
            self.log(f"❌ Message handler error: {e}")

    async def subscribe_with_verification(self, ws, symbol: str, timeout: float = 10.0) -> bool:
        """
        Subscribe to symbol and WAIT for REAL DATA (using Event - non-blocking!)

        This approach does NOT block the event loop - message_handler runs in parallel
        """
        stream_name = f"{symbol.lower()}@markPrice@1s"
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": self.next_id
        }

        # Create event for this symbol
        event = asyncio.Event()
        self.subscription_events[symbol] = event
        self.subscription_responses[self.next_id] = symbol

        # Send SUBSCRIBE
        await ws.send_str(json.dumps(subscribe_msg))
        self.next_id += 1
        self.total_subscriptions += 1

        # Wait for REAL DATA (non-blocking - message_handler will set event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            # Success - data received!
            self.total_verified += 1
            return True

        except asyncio.TimeoutError:
            # Timeout - silent fail detected
            self.log(f"   ⚠️  TIMEOUT: {symbol} - no data after {timeout}s")
            self.total_timeouts += 1
            self.total_silent_fails += 1
            return False

        finally:
            # Cleanup
            self.subscription_events.pop(symbol, None)
            # Note: we keep subscription_responses for message_handler

    async def subscribe_all_parallel(self, ws) -> Dict[str, bool]:
        """Subscribe to all symbols in PARALLEL with verification"""
        self.log(f"📤 Subscribing to {len(self.symbols)} symbols (PARALLEL with verification)...")

        # Start message handler in background
        handler_task = asyncio.create_task(self.message_handler(ws))

        # Small delay to let handler start
        await asyncio.sleep(0.1)

        # Subscribe to all in parallel (with small stagger to avoid burst)
        tasks = []
        for i, symbol in enumerate(self.symbols):
            # Stagger subscriptions by 100ms
            delay = i * 0.1
            task = asyncio.create_task(self._subscribe_with_delay(ws, symbol, delay))
            tasks.append((symbol, task))

        # Wait for all to complete
        results = {}
        for symbol, task in tasks:
            try:
                success = await task
                results[symbol] = success
            except Exception as e:
                self.log(f"   ❌ ERROR subscribing {symbol}: {e}")
                results[symbol] = False

        # Cancel handler (we'll restart it for monitoring)
        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass

        verified_count = sum(1 for v in results.values() if v)
        failed_count = len(results) - verified_count

        self.log(f"✅ Verification complete: {verified_count}/{len(self.symbols)} verified")
        if failed_count > 0:
            self.log(f"   ⚠️  {failed_count} silent fails detected")

        return results

    async def _subscribe_with_delay(self, ws, symbol: str, delay: float) -> bool:
        """Helper: subscribe with initial delay"""
        if delay > 0:
            await asyncio.sleep(delay)
        return await self.subscribe_with_verification(ws, symbol, timeout=10.0)

    async def monitor_data(self, ws, duration: float) -> Set[str]:
        """Monitor data arrival for specified duration"""
        self.log(f"👁️  Monitoring data for {duration:.0f} seconds...")

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

                # Subscribe with verification (PARALLEL, NON-BLOCKING)
                results = await self.subscribe_all_parallel(ws)

                verified = {s for s, ok in results.items() if ok}
                failed = {s for s, ok in results.items() if not ok}

                # Report
                self.log(f"\n📊 CYCLE #{self.cycle_count} RESULTS:")
                self.log(f"   Subscribed: {len(self.symbols)}")
                self.log(f"   Verified (real data): {len(verified)}")
                self.log(f"   Failed (silent fail): {len(failed)}")

                if failed:
                    self.log(f"   ⚠️  Failed symbols: {sorted(failed)}")

                success_rate = (len(verified) / len(self.symbols)) * 100
                self.log(f"   Success rate: {success_rate:.1f}%")

                # Monitor for remaining time
                remaining = self.reconnect_interval - 15  # rough estimate of time spent
                if remaining > 0:
                    self.log(f"\n⏳ Monitoring for {remaining}s before reconnection...")
                    final_data = await self.monitor_data(ws, remaining)

                    # Check for stale subscriptions
                    current_time = asyncio.get_event_loop().time()
                    stale_symbols = []
                    for symbol in verified:
                        last_update = self.last_data_time.get(symbol, 0)
                        if current_time - last_update > 30:
                            stale_symbols.append(symbol)

                    if stale_symbols:
                        self.log(f"   ⚠️  Stale subscriptions (>30s): {stale_symbols}")

                await ws.close()

    async def run(self, num_cycles: int = 5):
        """Run multiple reconnection cycles"""
        self.log(f"\n{'='*80}")
        self.log(f"EVENT-BASED VERIFICATION RECONNECTION TEST")
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
        self.log(f"Total verified: {self.total_verified}")
        self.log(f"Total timeouts: {self.total_timeouts}")
        self.log(f"Total silent fails: {self.total_silent_fails}")

        if self.total_subscriptions > 0:
            success_rate = (self.total_verified / self.total_subscriptions) * 100
            self.log(f"Overall success rate: {success_rate:.1f}%")
            self.log(f"Silent fail rate: {(self.total_silent_fails / self.total_subscriptions) * 100:.1f}%")


async def main():
    test_symbols = [
        'VFYUSDT', 'NOTUSDT', 'THETAUSDT', 'ANIMEUSDT',
        'GLMUSDT', 'POLUSDT', 'BASUSDT', 'C98USDT',
        'EULUSDT', 'SKLUSDT', 'HOOKUSDT', 'ONGUSDT',
        'LUNA2USDT', 'DOGEUSDT', 'RSRUSDT'
    ]

    tester = EventBasedReconnectionTester(
        symbols=test_symbols,
        reconnect_interval=120
    )

    await tester.run(num_cycles=5)


if __name__ == "__main__":
    asyncio.run(main())
