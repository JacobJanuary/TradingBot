#!/usr/bin/env python3
"""
ФИНАЛЬНЫЙ ТЕСТ - АГРЕССИВНЫЙ РЕЖИМ (ПИК ~100 ПОЗИЦИЙ)

Основано на успешном FIX V3:
- Начальные подписки: OPTIMISTIC (без verification)
- Последующие подписки: EVENT-BASED verification
- Агрессивные параметры для достижения 100 позиций в пике

ПАРАМЕТРЫ:
- Начальные optimistic: 30 позиций
- Subscribe: каждые 8 секунд
- Unsubscribe: каждые 30 секунд (начало через 90s)
- Длительность: 1 час
- Ожидаемый пик: ~100 активных позиций через 12 минут
"""

import asyncio
import json
import sys
import random
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Set, List
import aiohttp

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class AggressiveTester:
    """Final aggressive test - peak ~100 positions"""

    def __init__(self, all_symbols: List[str], duration_hours: float = 1.0):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.all_symbols = all_symbols
        self.duration_seconds = duration_hours * 3600

        # Active subscriptions
        self.active_subscriptions: Set[str] = set()
        self.pending_symbols: List[str] = list(all_symbols)
        random.shuffle(self.pending_symbols)

        # Data tracking
        self.last_data_time: Dict[str, float] = {}
        self.data_count: Dict[str, int] = {}

        # EVENT-BASED VERIFICATION
        self.verification_events: Dict[str, asyncio.Event] = {}

        # Statistics
        self.total_subscriptions = 0
        self.total_verified = 0
        self.total_unsubscriptions = 0
        self.total_silent_fails = 0
        self.total_retry_success = 0
        self.total_data_received = 0
        self.initial_subscriptions_count = 0
        self.peak_active = 0  # Track peak

        # Request tracking
        self.next_id = 1
        self.pending_requests: Dict[int, tuple] = {}

        # State
        self.ws = None
        self.running = False
        self.start_time = None

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        print(f"{timestamp} | {message}")

    async def message_handler(self):
        """Handle all incoming WebSocket messages"""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    # Subscription/Unsubscription response
                    if 'id' in data and 'result' in data:
                        req_id = data['id']
                        if req_id in self.pending_requests:
                            action, symbol = self.pending_requests.pop(req_id)
                            result = data.get('result')

                            if result is None:
                                if action == 'SUBSCRIBE':
                                    pass  # Wait for REAL DATA
                                else:
                                    self.log(f"   ✅ UNSUBSCRIBE confirmed: {symbol}")

                    # Mark price update - TRIGGER VERIFICATION EVENT
                    elif 'e' in data and data['e'] == 'markPriceUpdate':
                        symbol = data['s']
                        current_time = asyncio.get_event_loop().time()

                        self.last_data_time[symbol] = current_time
                        self.data_count[symbol] = self.data_count.get(symbol, 0) + 1
                        self.total_data_received += 1

                        # SET EVENT if waiting for verification
                        if symbol in self.verification_events:
                            self.verification_events[symbol].set()

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log(f"❌ WebSocket error: {msg.data}")
                    break

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.log(f"🔌 WebSocket closed")
                    break

        except Exception as e:
            self.log(f"❌ Message handler error: {e}")

    async def subscribe_with_verification(self, symbol: str, timeout: float = 10.0) -> bool:
        """
        Subscribe with EVENT-BASED verification (NON-BLOCKING!)
        Returns True if REAL DATA received within timeout
        """
        stream_name = f"{symbol.lower()}@markPrice@1s"
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": self.next_id
        }

        # Create verification event
        event = asyncio.Event()
        self.verification_events[symbol] = event
        self.pending_requests[self.next_id] = ('SUBSCRIBE', symbol)
        self.next_id += 1

        try:
            # Send SUBSCRIBE
            start_time = asyncio.get_event_loop().time()
            await self.ws.send_str(json.dumps(subscribe_msg))
            self.total_subscriptions += 1

            # Wait for REAL DATA (event-based, NON-BLOCKING!)
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
                # SUCCESS - data received!
                elapsed = asyncio.get_event_loop().time() - start_time
                self.active_subscriptions.add(symbol)
                self.total_verified += 1
                self.log(f"   ✅ VERIFIED: {symbol} (real data in {elapsed:.1f}s)")
                return True

            except asyncio.TimeoutError:
                # SILENT FAIL - no data after timeout
                self.log(f"   🚨 SILENT FAIL: {symbol} (timeout {timeout}s)")
                self.total_silent_fails += 1
                return False

        except Exception as e:
            self.log(f"   ❌ ERROR subscribing {symbol}: {e}")
            return False

        finally:
            # Cleanup
            self.verification_events.pop(symbol, None)

    async def subscribe_optimistic(self, symbol: str) -> bool:
        """
        Subscribe WITHOUT verification (optimistic approach)
        Used for initial subscriptions after WebSocket connect.
        """
        stream_name = f"{symbol.lower()}@markPrice@1s"
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": self.next_id
        }

        self.pending_requests[self.next_id] = ('SUBSCRIBE', symbol)
        self.next_id += 1

        try:
            # Send SUBSCRIBE (without verification)
            await self.ws.send_str(json.dumps(subscribe_msg))
            self.total_subscriptions += 1
            self.active_subscriptions.add(symbol)  # Optimistic
            self.log(f"   📤 SENT (optimistic): {symbol}")
            return True

        except Exception as e:
            self.log(f"   ❌ ERROR subscribing {symbol}: {e}")
            return False

    async def unsubscribe(self, symbol: str):
        """Unsubscribe from symbol"""
        stream_name = f"{symbol.lower()}@markPrice@1s"
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": [stream_name],
            "id": self.next_id
        }

        self.pending_requests[self.next_id] = ('UNSUBSCRIBE', symbol)
        self.next_id += 1

        try:
            await self.ws.send_str(json.dumps(unsubscribe_msg))
            self.active_subscriptions.discard(symbol)
            self.total_unsubscriptions += 1
            return True
        except Exception as e:
            self.log(f"   ❌ Failed UNSUBSCRIBE {symbol}: {e}")
            return False

    async def subscribe_task(self):
        """Subscribe to new symbol every 8 seconds WITH VERIFICATION"""
        while self.running:
            await asyncio.sleep(8)  # AGGRESSIVE: every 8 seconds

            if self.pending_symbols:
                symbol = self.pending_symbols.pop(0)
                self.log(f"📥 [AUTO] Subscribing to {symbol} (active: {len(self.active_subscriptions)})")

                # Subscribe with verification
                await self.subscribe_with_verification(symbol)

                # Update peak
                if len(self.active_subscriptions) > self.peak_active:
                    self.peak_active = len(self.active_subscriptions)
            else:
                self.log(f"⚠️  No more symbols")

    async def unsubscribe_task(self):
        """Unsubscribe from random symbol every 30 seconds"""
        # Wait 90 seconds before starting unsubscriptions
        await asyncio.sleep(90)

        while self.running:
            await asyncio.sleep(30)  # Every 30 seconds

            if len(self.active_subscriptions) > 10:
                symbol = random.choice(list(self.active_subscriptions))
                self.log(f"📤 [AUTO] Unsubscribing from {symbol} (active: {len(self.active_subscriptions)})")
                await self.unsubscribe(symbol)

    async def health_check_task(self):
        """Check subscription health every 60 seconds"""
        while self.running:
            await asyncio.sleep(60)

            current_time = asyncio.get_event_loop().time()
            stale_threshold = 30.0

            stale = []
            healthy = []

            for symbol in self.active_subscriptions:
                last_update = self.last_data_time.get(symbol, 0)

                if current_time - last_update > stale_threshold:
                    stale.append(symbol)
                else:
                    healthy.append(symbol)

            self.log(f"\n📊 [HEALTH CHECK]")
            self.log(f"   Active: {len(self.active_subscriptions)}")
            self.log(f"   Healthy: {len(healthy)}")
            self.log(f"   Stale: {len(stale)}")
            self.log(f"   Peak so far: {self.peak_active}")

            if len(self.active_subscriptions) > 0:
                health_pct = (len(healthy) / len(self.active_subscriptions)) * 100
                self.log(f"   Health: {health_pct:.1f}%")

                if health_pct < 90:
                    self.log(f"   ⚠️  WARNING: Health below 90%!")

            if stale:
                self.log(f"   ⚠️  Stale: {stale[:3]}")

            self.log("")

    async def stats_task(self):
        """Print statistics every 5 minutes"""
        while self.running:
            await asyncio.sleep(300)

            self.log(f"\n{'='*80}")
            self.log(f"📊 5-MINUTE STATISTICS (AGGRESSIVE MODE - PEAK 100)")
            self.log(f"{'='*80}")

            elapsed = asyncio.get_event_loop().time() - self.start_time
            self.log(f"Elapsed time: {elapsed/60:.1f} minutes")
            self.log(f"Total subscriptions: {self.total_subscriptions}")
            self.log(f"Total VERIFIED (real data): {self.total_verified}")
            self.log(f"Total silent fails: {self.total_silent_fails}")
            self.log(f"Total unsubscriptions: {self.total_unsubscriptions}")
            self.log(f"Currently active: {len(self.active_subscriptions)}")
            self.log(f"PEAK active: {self.peak_active}")
            self.log(f"Total data received: {self.total_data_received}")

            if self.total_subscriptions > 0:
                verify_rate = (self.total_verified / self.total_subscriptions) * 100
                fail_rate = (self.total_silent_fails / self.total_subscriptions) * 100
                self.log(f"\n🎯 VERIFICATION RATE: {verify_rate:.1f}%")
                self.log(f"🚨 SILENT FAIL RATE: {fail_rate:.1f}%")

            if self.data_count:
                top = sorted(self.data_count.items(), key=lambda x: x[1], reverse=True)[:5]
                self.log(f"\nTop data receivers:")
                for sym, count in top:
                    self.log(f"   {sym}: {count} updates")

            self.log(f"{'='*80}\n")

    async def run(self):
        """Run aggressive test"""
        self.log(f"\n{'='*80}")
        self.log(f"AGGRESSIVE TEST - PEAK ~100 POSITIONS")
        self.log(f"{'='*80}")
        self.log(f"Duration: {self.duration_seconds/3600:.1f} hours")
        self.log(f"Total symbols: {len(self.all_symbols)}")
        self.log(f"Initial optimistic: 30 positions")
        self.log(f"Subscribe interval: 8 seconds")
        self.log(f"Unsubscribe interval: 30 seconds (start after 90s)")
        self.log(f"Expected peak: ~100 positions at 12 minutes")
        self.log(f"{'='*80}\n")

        self.start_time = asyncio.get_event_loop().time()
        end_time = self.start_time + self.duration_seconds

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                self.ws = ws
                self.running = True

                self.log(f"✅ WebSocket connected")

                # Wait 3 seconds for WebSocket stabilization
                self.log(f"⏳ Waiting 3s for WebSocket stabilization...")
                await asyncio.sleep(3.0)

                # Initial 30 subscriptions WITHOUT verification (optimistic)
                self.log(f"\n📥 Initial subscriptions (30 symbols, OPTIMISTIC - no wait)...")
                for i in range(30):
                    if self.pending_symbols:
                        symbol = self.pending_symbols.pop(0)
                        self.initial_subscriptions_count += 1
                        await self.subscribe_optimistic(symbol)
                        await asyncio.sleep(0.1)

                self.log(f"✅ Initial: {self.initial_subscriptions_count} sent (optimistic)\n")

                # Wait 60 seconds for initial subscriptions to "warm up"
                self.log(f"⏳ Waiting 60s for initial subscriptions to start sending data...")
                await asyncio.sleep(60.0)
                self.log(f"✅ Warmup complete\n")

                # Start background tasks
                tasks = [
                    asyncio.create_task(self.message_handler()),
                    asyncio.create_task(self.subscribe_task()),
                    asyncio.create_task(self.unsubscribe_task()),
                    asyncio.create_task(self.health_check_task()),
                    asyncio.create_task(self.stats_task()),
                ]

                remaining = end_time - asyncio.get_event_loop().time()
                self.log(f"⏳ Running for {remaining/3600:.1f} hours...\n")

                try:
                    await asyncio.sleep(remaining)
                except KeyboardInterrupt:
                    self.log(f"\n⚠️  Interrupted")

                self.running = False
                for task in tasks:
                    task.cancel()

                await asyncio.gather(*tasks, return_exceptions=True)
                await ws.close()

        # Final stats
        elapsed = asyncio.get_event_loop().time() - self.start_time

        self.log(f"\n{'='*80}")
        self.log(f"📊 FINAL STATISTICS (AGGRESSIVE MODE)")
        self.log(f"{'='*80}")
        self.log(f"Duration: {elapsed/3600:.2f} hours")
        self.log(f"Total subscriptions: {self.total_subscriptions}")
        self.log(f"Total VERIFIED: {self.total_verified}")
        self.log(f"Total silent fails: {self.total_silent_fails}")
        self.log(f"Total unsubscriptions: {self.total_unsubscriptions}")
        self.log(f"PEAK active positions: {self.peak_active}")
        self.log(f"Total data received: {self.total_data_received}")

        if self.total_subscriptions > 0:
            verify_rate = (self.total_verified / self.total_subscriptions) * 100
            fail_rate = (self.total_silent_fails / self.total_subscriptions) * 100

            self.log(f"\n🎯 VERIFICATION RATE: {verify_rate:.1f}%")
            self.log(f"🚨 SILENT FAIL RATE: {fail_rate:.1f}%")

        self.log(f"{'='*80}\n")


async def main():
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
        'ADAUSDT', 'DOGEUSDT', 'TRXUSDT', 'LINKUSDT', 'MATICUSDT',
        'AVAXUSDT', 'DOTUSDT', 'UNIUSDT', 'ATOMUSDT', 'NEARUSDT',
        'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT',
        'LTCUSDT', 'ETCUSDT', 'FILUSDT', 'ICPUSDT', 'HBARUSDT',
        'STXUSDT', 'IMXUSDT', 'ALGOUSDT', 'FTMUSDT', 'SANDUSDT',
        'MANAUSDT', 'AXSUSDT', 'CHZUSDT', 'THETAUSDT', 'FLOWUSDT',
        'GALAUSDT', 'APEUSDT', 'GMXUSDT', 'LDOUSDT', 'ARUSDT',
        'VFYUSDT', 'NOTUSDT', 'ANIMEUSDT', 'GLMUSDT', 'POLUSDT',
        'BASUSDT', 'C98USDT', 'EULUSDT', 'SKLUSDT', 'HOOKUSDT',
        'ONGUSDT', 'LUNA2USDT', 'RSRUSDT',
        'ENJUSDT', 'ZILUSDT', 'BALUSDT', 'YFIUSDT', 'CRVUSDT',
        'SUSHIUSDT', 'SNXUSDT', 'COMPUSDT', 'MKRUSDT', 'AAVEUSDT',
        '1INCHUSDT', 'RENUSDT', 'KSMUSDT', 'RUNEUSDT', 'OCEANUSDT',
        'ZENUSDT', 'WAVESUSDT', 'DASHUSDT', 'ZECUSDT', 'XMRUSDT',
        'VETUSDT', 'XLMUSDT', 'IOTAUSDT', 'NEOUSDT', 'QTUMUSDT',
        'ONTUSDT', 'ICXUSDT', 'NULSUSDT', 'SCUSDT',
        'FETUSDT', 'CELRUSDT', 'CTKUSDT', 'AKROUSDT',
        'AUDIOUSDT', 'COTIUSDT', 'CKBUSDT', 'TWTUSDT', 'FIROUSDT',
        'LITUSDT', 'SFPUSDT', 'DODOUSDT', 'CAKEUSDT', 'ACMUSDT',
        'BADGERUSDT', 'FISUSDT', 'OMUSDT', 'PONDUSDT', 'DEGOUSDT'
    ]

    print(f"Total symbols: {len(symbols)}")

    tester = AggressiveTester(
        all_symbols=symbols,
        duration_hours=1.0  # 1 hour
    )

    await tester.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
