#!/usr/bin/env python3
"""
ДИНАМИЧЕСКИЙ СТРЕСС-ТЕСТ: Эмуляция реальной работы бота
- 100 символов
- 2 часа работы
- Каждые 30s: подписка на новый символ (как открытие позиции)
- Каждые 60s: отписка от случайного (как закрытие позиции)
- Постоянный мониторинг здоровья подписок
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


class DynamicSubscriptionTester:
    """Test dynamic subscription/unsubscription like real bot"""

    def __init__(self, all_symbols: List[str], duration_hours: float = 2.0):
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

        # Statistics
        self.total_subscriptions = 0
        self.total_unsubscriptions = 0
        self.total_silent_fails = 0
        self.total_data_received = 0

        # Request tracking
        self.next_id = 1
        self.pending_requests: Dict[int, tuple] = {}  # {id: (action, symbol)}

        # State
        self.ws = None
        self.running = False

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
                                    self.log(f"   ✅ SUBSCRIBE confirmed: {symbol}")
                                else:
                                    self.log(f"   ✅ UNSUBSCRIBE confirmed: {symbol}")
                            else:
                                self.log(f"   ⚠️  {action} failed for {symbol}: {result}")

                    # Mark price update
                    elif 'e' in data and data['e'] == 'markPriceUpdate':
                        symbol = data['s']
                        current_time = asyncio.get_event_loop().time()

                        self.last_data_time[symbol] = current_time
                        self.data_count[symbol] = self.data_count.get(symbol, 0) + 1
                        self.total_data_received += 1

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log(f"❌ WebSocket error: {msg.data}")
                    break

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.log(f"🔌 WebSocket closed")
                    break

        except Exception as e:
            self.log(f"❌ Message handler error: {e}")

    async def subscribe(self, symbol: str):
        """Subscribe to symbol"""
        stream_name = f"{symbol.lower()}@markPrice@1s"
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": self.next_id
        }

        self.pending_requests[self.next_id] = ('SUBSCRIBE', symbol)
        self.next_id += 1

        try:
            await self.ws.send_str(json.dumps(subscribe_msg))
            self.active_subscriptions.add(symbol)
            self.total_subscriptions += 1
            return True
        except Exception as e:
            self.log(f"   ❌ Failed to send SUBSCRIBE for {symbol}: {e}")
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
            self.log(f"   ❌ Failed to send UNSUBSCRIBE for {symbol}: {e}")
            return False

    async def subscribe_task(self):
        """Subscribe to new symbol every 30 seconds"""
        while self.running:
            await asyncio.sleep(30)

            if self.pending_symbols:
                symbol = self.pending_symbols.pop(0)
                self.log(f"📥 [AUTO] Subscribing to {symbol} "
                        f"(active: {len(self.active_subscriptions)})")
                await self.subscribe(symbol)
            else:
                self.log(f"⚠️  No more symbols to subscribe")

    async def unsubscribe_task(self):
        """Unsubscribe from random symbol every 60 seconds"""
        while self.running:
            await asyncio.sleep(60)

            if len(self.active_subscriptions) > 5:  # Keep at least 5 active
                symbol = random.choice(list(self.active_subscriptions))
                self.log(f"📤 [AUTO] Unsubscribing from {symbol} "
                        f"(active: {len(self.active_subscriptions)})")
                await self.unsubscribe(symbol)
            else:
                self.log(f"⏸️  Skipping unsubscribe (only {len(self.active_subscriptions)} active)")

    async def health_check_task(self):
        """Check subscription health every 60 seconds"""
        while self.running:
            await asyncio.sleep(60)

            current_time = asyncio.get_event_loop().time()
            stale_threshold = 30.0  # 30 seconds

            # Check active subscriptions
            stale = []
            healthy = []
            never_received = []

            for symbol in self.active_subscriptions:
                last_update = self.last_data_time.get(symbol, 0)

                if last_update == 0:
                    # Never received data
                    never_received.append(symbol)
                elif current_time - last_update > stale_threshold:
                    # Stale
                    stale.append(symbol)
                else:
                    # Healthy
                    healthy.append(symbol)

            self.log(f"\n📊 [HEALTH CHECK]")
            self.log(f"   Active subscriptions: {len(self.active_subscriptions)}")
            self.log(f"   Healthy (fresh data): {len(healthy)}")
            self.log(f"   Stale (>30s): {len(stale)}")
            self.log(f"   Silent fails (no data): {len(never_received)}")

            if stale:
                self.log(f"   ⚠️  Stale symbols: {stale[:5]}")

            if never_received:
                self.log(f"   🚨 SILENT FAILS: {never_received}")
                self.total_silent_fails += len(never_received)

            # Calculate health percentage
            if len(self.active_subscriptions) > 0:
                health_pct = (len(healthy) / len(self.active_subscriptions)) * 100
                self.log(f"   Health: {health_pct:.1f}%")

                if health_pct < 90:
                    self.log(f"   ⚠️  WARNING: Health below 90%!")

            self.log("")  # Empty line

    async def stats_task(self):
        """Print statistics every 5 minutes"""
        while self.running:
            await asyncio.sleep(300)  # 5 minutes

            self.log(f"\n{'='*80}")
            self.log(f"📊 5-MINUTE STATISTICS")
            self.log(f"{'='*80}")
            self.log(f"Total subscriptions: {self.total_subscriptions}")
            self.log(f"Total unsubscriptions: {self.total_unsubscriptions}")
            self.log(f"Currently active: {len(self.active_subscriptions)}")
            self.log(f"Total data received: {self.total_data_received}")
            self.log(f"Total silent fails detected: {self.total_silent_fails}")

            # Top data receivers
            if self.data_count:
                top_symbols = sorted(self.data_count.items(),
                                   key=lambda x: x[1], reverse=True)[:5]
                self.log(f"\nTop data receivers:")
                for symbol, count in top_symbols:
                    self.log(f"   {symbol}: {count} updates")

            self.log(f"{'='*80}\n")

    async def run(self):
        """Run dynamic subscription test"""
        self.log(f"\n{'='*80}")
        self.log(f"DYNAMIC SUBSCRIPTION STRESS TEST")
        self.log(f"{'='*80}")
        self.log(f"Duration: {self.duration_seconds/3600:.1f} hours")
        self.log(f"Total symbols available: {len(self.all_symbols)}")
        self.log(f"Subscribe interval: 30 seconds")
        self.log(f"Unsubscribe interval: 60 seconds")
        self.log(f"Expected subscriptions: ~{int(self.duration_seconds / 30)}")
        self.log(f"Expected unsubscriptions: ~{int(self.duration_seconds / 60)}")
        self.log(f"{'='*80}\n")

        start_time = asyncio.get_event_loop().time()
        end_time = start_time + self.duration_seconds

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                self.ws = ws
                self.running = True

                self.log(f"✅ WebSocket connected")

                # Subscribe to initial 10 symbols
                self.log(f"\n📥 Initial subscriptions (10 symbols)...")
                for i in range(10):
                    if self.pending_symbols:
                        symbol = self.pending_symbols.pop(0)
                        await self.subscribe(symbol)
                        await asyncio.sleep(0.1)

                self.log(f"✅ Initial subscriptions complete\n")

                # Start background tasks
                tasks = [
                    asyncio.create_task(self.message_handler()),
                    asyncio.create_task(self.subscribe_task()),
                    asyncio.create_task(self.unsubscribe_task()),
                    asyncio.create_task(self.health_check_task()),
                    asyncio.create_task(self.stats_task()),
                ]

                # Wait for duration
                remaining = end_time - asyncio.get_event_loop().time()
                self.log(f"⏳ Running test for {remaining/3600:.1f} hours...\n")

                try:
                    await asyncio.sleep(remaining)
                except KeyboardInterrupt:
                    self.log(f"\n⚠️  Test interrupted by user")

                # Stop tasks
                self.running = False
                for task in tasks:
                    task.cancel()

                # Wait for tasks to finish
                await asyncio.gather(*tasks, return_exceptions=True)

                await ws.close()

        # Final statistics
        elapsed = asyncio.get_event_loop().time() - start_time

        self.log(f"\n{'='*80}")
        self.log(f"📊 FINAL STATISTICS")
        self.log(f"{'='*80}")
        self.log(f"Duration: {elapsed/3600:.2f} hours ({elapsed/60:.1f} minutes)")
        self.log(f"Total subscriptions: {self.total_subscriptions}")
        self.log(f"Total unsubscriptions: {self.total_unsubscriptions}")
        self.log(f"Total data received: {self.total_data_received}")
        self.log(f"Total silent fails: {self.total_silent_fails}")

        if self.total_subscriptions > 0:
            fail_rate = (self.total_silent_fails / self.total_subscriptions) * 100
            self.log(f"Silent fail rate: {fail_rate:.1f}%")

        # Symbols that never sent data
        never_received = [s for s in self.active_subscriptions
                         if s not in self.last_data_time]

        if never_received:
            self.log(f"\n🚨 Symbols that NEVER sent data:")
            for symbol in never_received[:20]:
                self.log(f"   - {symbol}")
            if len(never_received) > 20:
                self.log(f"   ... and {len(never_received) - 20} more")

        # Data count distribution
        if self.data_count:
            counts = list(self.data_count.values())
            avg = sum(counts) / len(counts)
            self.log(f"\nData distribution:")
            self.log(f"   Average updates per symbol: {avg:.1f}")
            self.log(f"   Min: {min(counts)}, Max: {max(counts)}")

        self.log(f"{'='*80}\n")


async def main():
    # Get top 100 USDT futures symbols
    # (В реальности можно получить через Binance API, но для теста хардкодим)
    symbols = [
        # Top 20 by volume
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
        'ADAUSDT', 'DOGEUSDT', 'TRXUSDT', 'LINKUSDT', 'MATICUSDT',
        'AVAXUSDT', 'DOTUSDT', 'UNIUSDT', 'ATOMUSDT', 'NEARUSDT',
        'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT',

        # Mid-cap
        'LTCUSDT', 'ETCUSDT', 'FILUSDT', 'ICPUSDT', 'HBARUSDT',
        'STXUSDT', 'IMXUSDT', 'ALGOUSDT', 'FTMUSDT', 'SANDUSDT',
        'MANAUSDT', 'AXSUSDT', 'CHZUSDT', 'THETAUSDT', 'FLOWUSDT',
        'GALAUSDT', 'APEUSDT', 'GMXUSDT', 'LDOUSDT', 'ARUSDT',

        # From bot
        'VFYUSDT', 'NOTUSDT', 'ANIMEUSDT', 'GLMUSDT', 'POLUSDT',
        'BASUSDT', 'C98USDT', 'EULUSDT', 'SKLUSDT', 'HOOKUSDT',
        'ONGUSDT', 'LUNA2USDT', 'RSRUSDT',

        # Additional symbols
        'ENJUSDT', 'ZILUSDT', 'BALUSDT', 'YFIUSDT', 'CRVUSDT',
        'SUSHIUSDT', 'SNXUSDT', 'COMPUSDT', 'MKRUSDT', 'AAVEUSDT',
        '1INCHUSDT', 'RENUSDT', 'KSMUSDT', 'RUNEUSDT', 'OCEANUSDT',
        'ZENUSDT', 'WAVESUSDT', 'DASHUSDT', 'ZECUSDT', 'XMRUSDT',

        # More symbols
        'VETUSDT', 'XLMUSDT', 'IOTAUSDT', 'NEOUSDT', 'QTUMUSDT',
        'ONTUSDT', 'ICXUSDT', 'NULSUSDT', 'SCUSDT', 'ZILUSDT',
        'FETUSDT', 'CELRUSDT', 'CTKUSDT', 'AKROUSDT', 'AXSUSDT',
        'AUDIOUSDT', 'COTIUSDT', 'CKBUSDT', 'TWTUSDT', 'FIROUSDT',
        'LITUSDT', 'SFPUSDT', 'DODOUSDT', 'CAKEUSDT', 'ACMUSDT',
        'BADGERUSDT', 'FISUSDT', 'OMUSDT', 'PONDUSDT', 'DEGOUSDT'
    ]

    print(f"Total symbols loaded: {len(symbols)}")

    tester = DynamicSubscriptionTester(
        all_symbols=symbols,
        duration_hours=2.0
    )

    await tester.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
