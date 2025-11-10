#!/usr/bin/env python3
"""
ТЕСТ ПЕРЕПОДКЛЮЧЕНИЙ: Baseline подход (без верификации)
Текущий подход бота - отправляем SUBSCRIBE, ждем response, но не проверяем данные
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


class BaselineReconnectionTester:
    """Test reconnection with baseline approach (no data verification)"""

    def __init__(self, symbols: list, reconnect_interval: int = 120):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.symbols = symbols
        self.reconnect_interval = reconnect_interval

        # Statistics
        self.cycle_count = 0
        self.total_subscriptions = 0
        self.total_responses = 0
        self.total_data_received = 0
        self.silent_fails_count = 0

        # Current cycle data
        self.next_id = 1
        self.last_data_time: Dict[str, float] = {}

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        print(f"{timestamp} | {message}")

    async def subscribe_all(self, ws) -> Dict[str, bool]:
        """Subscribe to all symbols (baseline approach - no verification)"""
        self.log(f"📤 Subscribing to {len(self.symbols)} symbols...")

        subscribe_ids = {}
        responses = {}

        # Send all SUBSCRIBE requests
        for symbol in self.symbols:
            stream_name = f"{symbol.lower()}@markPrice@1s"
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [stream_name],
                "id": self.next_id
            }

            subscribe_ids[self.next_id] = symbol
            await ws.send_str(json.dumps(subscribe_msg))
            self.next_id += 1
            self.total_subscriptions += 1

            await asyncio.sleep(0.1)  # Same delay as bot

        # Wait for responses (5 seconds timeout)
        self.log(f"📥 Waiting for subscription responses...")
        timeout_time = asyncio.get_event_loop().time() + 5.0

        while asyncio.get_event_loop().time() < timeout_time and len(responses) < len(self.symbols):
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    # Subscription response
                    if 'id' in data and 'result' in data:
                        req_id = data['id']
                        if req_id in subscribe_ids:
                            symbol = subscribe_ids[req_id]
                            responses[symbol] = data['result'] is None
                            self.total_responses += 1

            except asyncio.TimeoutError:
                continue

        success_count = sum(1 for v in responses.values() if v)
        self.log(f"✅ Received {len(responses)}/{len(self.symbols)} responses ({success_count} successful)")

        return responses

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

                    # Mark price update
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

                # Subscribe
                responses = await self.subscribe_all(ws)

                # Wait 5 seconds, then check data
                await asyncio.sleep(5.0)

                # Check data for 10 seconds
                data_symbols = await self.monitor_data(ws, 10.0)

                # Calculate silent fails
                confirmed_symbols = {s for s, ok in responses.items() if ok}
                silent_fails = confirmed_symbols - data_symbols

                self.total_data_received += len(data_symbols)
                self.silent_fails_count += len(silent_fails)

                # Report
                self.log(f"\n📊 CYCLE #{self.cycle_count} RESULTS:")
                self.log(f"   Subscribed: {len(self.symbols)}")
                self.log(f"   Responses OK: {len(confirmed_symbols)}")
                self.log(f"   Data received: {len(data_symbols)}")
                self.log(f"   Silent fails: {len(silent_fails)}")

                if silent_fails:
                    self.log(f"   ⚠️  Silent fail symbols: {sorted(silent_fails)}")

                success_rate = (len(data_symbols) / len(self.symbols)) * 100
                self.log(f"   Success rate: {success_rate:.1f}%")

                # Wait remaining time before reconnect
                remaining = self.reconnect_interval - 15  # 15s already spent
                if remaining > 0:
                    self.log(f"\n⏳ Waiting {remaining}s before next reconnection...")

                    # Monitor data during wait
                    final_data = await self.monitor_data(ws, remaining)

                    # Check for stale subscriptions
                    current_time = asyncio.get_event_loop().time()
                    stale_symbols = []
                    for symbol in self.symbols:
                        last_update = self.last_data_time.get(symbol, 0)
                        if current_time - last_update > 30:
                            stale_symbols.append(symbol)

                    if stale_symbols:
                        self.log(f"   ⚠️  Stale subscriptions (>30s): {stale_symbols}")

                await ws.close()

    async def run(self, num_cycles: int = 5):
        """Run multiple reconnection cycles"""
        self.log(f"\n{'='*80}")
        self.log(f"BASELINE RECONNECTION TEST")
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

            # Small delay between cycles
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
        self.log(f"Total responses: {self.total_responses}")
        self.log(f"Total data received: {self.total_data_received}")
        self.log(f"Total silent fails: {self.silent_fails_count}")

        if self.total_subscriptions > 0:
            overall_success = ((self.total_subscriptions - self.silent_fails_count) / self.total_subscriptions) * 100
            self.log(f"Overall success rate: {overall_success:.1f}%")
            self.log(f"Silent fail rate: {(self.silent_fails_count / self.total_subscriptions) * 100:.1f}%")


async def main():
    # Use same symbols as the bot
    test_symbols = [
        'VFYUSDT', 'NOTUSDT', 'THETAUSDT', 'ANIMEUSDT',
        'GLMUSDT', 'POLUSDT', 'BASUSDT', 'C98USDT',
        'EULUSDT', 'SKLUSDT', 'HOOKUSDT', 'ONGUSDT',
        'LUNA2USDT', 'DOGEUSDT', 'RSRUSDT'
    ]

    tester = BaselineReconnectionTester(
        symbols=test_symbols,
        reconnect_interval=120  # 2 minutes per cycle
    )

    await tester.run(num_cycles=5)  # 5 cycles = ~10 minutes


if __name__ == "__main__":
    asyncio.run(main())
