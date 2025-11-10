#!/usr/bin/env python3
"""
ДИНАМИЧЕСКИЙ ТЕСТ С EVENT-BASED VERIFICATION V3 (ФИНАЛЬНОЕ РЕШЕНИЕ)

КЛЮЧЕВОЕ ОТКРЫТИЕ:
- Начальные подписки после WebSocket connect получают данные с задержкой 20-60 секунд
- Последующие подписки работают мгновенно (<10s)

FIX V3:
1. Начальные подписки - OPTIMISTIC (без verification, просто send)
2. Delay 60s для "прогрева" начальных подписок
3. ВСЕ последующие подписки - event-based verification (10s timeout)
4. Health check проверяет реальное получение данных
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


class DynamicTesterWithFixV3:
    """Test with Event-based verification FIX V3 - Optimistic initial subs"""

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

        # EVENT-BASED VERIFICATION (NEW!)
        self.verification_events: Dict[str, asyncio.Event] = {}
        self.subscription_pending: Set[str] = set()

        # Statistics
        self.total_subscriptions = 0
        self.total_verified = 0
        self.total_unsubscriptions = 0
        self.total_silent_fails = 0
        self.total_retry_success = 0
        self.total_data_received = 0
        self.initial_subscriptions_count = 0  # NEW: track initial subs

        # Request tracking
        self.next_id = 1
        self.pending_requests: Dict[int, tuple] = {}

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
                                    # Response OK, but we still wait for REAL DATA
                                    pass
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

        FIX V3: Используется только для подписок ПОСЛЕ начальных (warmup).
        Начальные подписки используют subscribe_optimistic().

        Default timeout: 10s (после warmup данные приходят быстро)

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

    async def retry_silent_fail(self, symbol: str) -> bool:
        """
        Retry subscription for silent fail
        FIX V3: Более короткий timeout для retry (5s)
        """
        self.log(f"   🔄 RETRY: {symbol}")
        success = await self.subscribe_with_verification(symbol, timeout=5.0)
        if success:
            self.total_retry_success += 1
        return success

    async def subscribe_optimistic(self, symbol: str) -> bool:
        """
        Subscribe WITHOUT verification (optimistic approach)

        FIX V3: Используется для начальных подписок после WebSocket connect.
        Данные начнут приходить через 20-60 секунд, но мы не блокируем event loop ожиданием.

        Health check позже проверит что данные реально приходят.
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
            # Send SUBSCRIBE (без ожидания verification)
            await self.ws.send_str(json.dumps(subscribe_msg))
            self.total_subscriptions += 1
            self.active_subscriptions.add(symbol)  # Оптимистично добавляем
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
        """Subscribe to new symbol every 30 seconds WITH VERIFICATION"""
        while self.running:
            await asyncio.sleep(30)

            if self.pending_symbols:
                symbol = self.pending_symbols.pop(0)
                self.log(f"📥 [AUTO] Subscribing to {symbol} (active: {len(self.active_subscriptions)})")

                # Subscribe with verification
                success = await self.subscribe_with_verification(symbol)

                # If failed, retry ONCE
                if not success:
                    await asyncio.sleep(1.0)
                    await self.retry_silent_fail(symbol)
            else:
                self.log(f"⚠️  No more symbols")

    async def unsubscribe_task(self):
        """Unsubscribe from random symbol every 60 seconds"""
        while self.running:
            await asyncio.sleep(60)

            if len(self.active_subscriptions) > 5:
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
            self.log(f"📊 5-MINUTE STATISTICS (FIX V3 - OPTIMISTIC INITIAL)")
            self.log(f"{'='*80}")
            self.log(f"Total subscriptions: {self.total_subscriptions}")
            self.log(f"Total VERIFIED (real data): {self.total_verified}")
            self.log(f"Total silent fails: {self.total_silent_fails}")
            self.log(f"Total retry success: {self.total_retry_success}")
            self.log(f"Total unsubscriptions: {self.total_unsubscriptions}")
            self.log(f"Currently active: {len(self.active_subscriptions)}")
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
        """Run dynamic test WITH FIX V3"""
        self.log(f"\n{'='*80}")
        self.log(f"DYNAMIC TEST WITH EVENT-BASED VERIFICATION FIX V3")
        self.log(f"{'='*80}")
        self.log(f"Duration: {self.duration_seconds/3600:.1f} hours")
        self.log(f"Total symbols: {len(self.all_symbols)}")
        self.log(f"Expected subscriptions: ~{int(self.duration_seconds / 30)}")
        self.log(f"🔧 FIX V3:")
        self.log(f"   - Initial subs: OPTIMISTIC (no verification)")
        self.log(f"   - Warmup delay: 60s (let data start flowing)")
        self.log(f"   - Subsequent subs: EVENT-BASED (10s timeout)")
        self.log(f"{'='*80}\n")

        start_time = asyncio.get_event_loop().time()
        end_time = start_time + self.duration_seconds

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                self.ws = ws
                self.running = True

                self.log(f"✅ WebSocket connected")

                # FIX V3: Wait 3 seconds for WebSocket stabilization
                self.log(f"⏳ Waiting 3s for WebSocket stabilization...")
                await asyncio.sleep(3.0)

                # FIX V3: Initial subscriptions WITHOUT verification (optimistic)
                self.log(f"\n📥 Initial subscriptions (10 symbols, OPTIMISTIC - no wait)...")
                for i in range(10):
                    if self.pending_symbols:
                        symbol = self.pending_symbols.pop(0)
                        self.initial_subscriptions_count += 1
                        await self.subscribe_optimistic(symbol)
                        await asyncio.sleep(0.1)

                self.log(f"✅ Initial: {self.initial_subscriptions_count} sent (optimistic)\n")

                # FIX V3: Wait 60 seconds for initial subscriptions to "warm up"
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
        elapsed = asyncio.get_event_loop().time() - start_time

        self.log(f"\n{'='*80}")
        self.log(f"📊 FINAL STATISTICS (FIX V3 - OPTIMISTIC INITIAL)")
        self.log(f"{'='*80}")
        self.log(f"Duration: {elapsed/3600:.2f} hours")
        self.log(f"Total subscriptions: {self.total_subscriptions}")
        self.log(f"Total VERIFIED: {self.total_verified}")
        self.log(f"Total silent fails: {self.total_silent_fails}")
        self.log(f"Total retry success: {self.total_retry_success}")
        self.log(f"Total data received: {self.total_data_received}")

        if self.total_subscriptions > 0:
            verify_rate = (self.total_verified / self.total_subscriptions) * 100
            fail_rate = (self.total_silent_fails / self.total_subscriptions) * 100
            final_success = ((self.total_verified + self.total_retry_success) / self.total_subscriptions) * 100

            self.log(f"\n🎯 VERIFICATION RATE: {verify_rate:.1f}%")
            self.log(f"🚨 SILENT FAIL RATE: {fail_rate:.1f}%")
            self.log(f"✅ FINAL SUCCESS RATE (after retry): {final_success:.1f}%")

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

    tester = DynamicTesterWithFixV3(
        all_symbols=symbols,
        duration_hours=1.0  # 1 hour
    )

    await tester.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
