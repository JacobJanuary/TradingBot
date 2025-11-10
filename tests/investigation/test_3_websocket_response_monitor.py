#!/usr/bin/env python3
"""
ТЕСТ #3: Мониторинг WebSocket ответов Binance - отслеживание SUBSCRIBE responses
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import aiohttp

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class BinanceWSSubscriptionTester:
    """Test Binance WebSocket subscription responses"""

    def __init__(self):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.responses = []
        self.data_received = {}
        self.next_id = 1

    async def test_single_subscription(self, symbol: str):
        """Test single symbol subscription and monitor response"""

        print(f"\n{'='*80}")
        print(f"ТЕСТ: Одиночная подписка на {symbol}")
        print(f"{'='*80}\n")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                print(f"✅ WebSocket connected to {self.ws_url}")

                # Subscribe
                stream_name = f"{symbol.lower()}@markPrice@1s"
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": [stream_name],
                    "id": self.next_id
                }

                print(f"\n📤 Sending SUBSCRIBE:")
                print(f"   {json.dumps(subscribe_msg, indent=2)}")

                await ws.send_str(json.dumps(subscribe_msg))
                self.next_id += 1

                # Wait for responses
                print(f"\n📥 Waiting for responses (10 seconds)...")
                timeout_time = asyncio.get_event_loop().time() + 10
                response_received = False
                data_count = 0

                while asyncio.get_event_loop().time() < timeout_time:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)

                            # Check if it's a subscription response
                            if 'id' in data and 'result' in data:
                                print(f"\n✅ SUBSCRIPTION RESPONSE:")
                                print(f"   {json.dumps(data, indent=2)}")
                                response_received = True

                            # Check if it's actual data
                            elif 'e' in data and data['e'] == 'markPriceUpdate':
                                if data_count == 0:
                                    print(f"\n✅ FIRST DATA RECEIVED:")
                                    print(f"   Symbol: {data['s']}")
                                    print(f"   Mark Price: {data['p']}")
                                    print(f"   Event Time: {datetime.fromtimestamp(data['E']/1000, tz=timezone.utc)}")
                                data_count += 1

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"❌ WebSocket error: {msg.data}")

                    except asyncio.TimeoutError:
                        continue

                print(f"\n📊 РЕЗУЛЬТАТЫ:")
                print(f"   Response received: {response_received}")
                print(f"   Data messages: {data_count}")

                if response_received and data_count > 0:
                    print(f"   ✅ Подписка работает корректно")
                elif response_received and data_count == 0:
                    print(f"   ⚠️  Response получен, но данных НЕТ (silent fail!)")
                else:
                    print(f"   ❌ Подписка не работает")

                await ws.close()

    async def test_bulk_subscription(self, symbols: list, delay: float = 0.1):
        """Test bulk subscription like our bot does"""

        print(f"\n{'='*80}")
        print(f"ТЕСТ: Массовая подписка ({len(symbols)} символов с delay={delay}s)")
        print(f"{'='*80}\n")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                print(f"✅ WebSocket connected")

                # Subscribe to all symbols with delay (как делает бот)
                subscribe_ids = {}

                print(f"\n📤 Отправка {len(symbols)} SUBSCRIBE запросов...")
                for i, symbol in enumerate(symbols):
                    stream_name = f"{symbol.lower()}@markPrice@1s"
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": [stream_name],
                        "id": self.next_id
                    }

                    subscribe_ids[self.next_id] = symbol
                    await ws.send_str(json.dumps(subscribe_msg))

                    if (i + 1) % 10 == 0:
                        print(f"   Sent {i+1}/{len(symbols)}...")

                    self.next_id += 1

                    if i < len(symbols) - 1:
                        await asyncio.sleep(delay)

                print(f"✅ Все SUBSCRIBE отправлены")

                # Wait for responses
                print(f"\n📥 Waiting for responses (15 seconds)...")
                timeout_time = asyncio.get_event_loop().time() + 15

                responses = {}
                data_symbols = set()

                while asyncio.get_event_loop().time() < timeout_time:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)

                            # Subscription response
                            if 'id' in data and 'result' in data:
                                req_id = data['id']
                                if req_id in subscribe_ids:
                                    symbol = subscribe_ids[req_id]
                                    responses[symbol] = data['result']

                            # Data
                            elif 'e' in data and data['e'] == 'markPriceUpdate':
                                data_symbols.add(data['s'])

                    except asyncio.TimeoutError:
                        continue

                # Analysis
                print(f"\n📊 РЕЗУЛЬТАТЫ:")
                print(f"   Запрошено подписок: {len(symbols)}")
                print(f"   Получено responses: {len(responses)}")
                print(f"   Получено данных от символов: {len(data_symbols)}")

                confirmed = [s for s, r in responses.items() if r is None]
                print(f"\n   ✅ Confirmed (result=null): {len(confirmed)}")

                # Find silent fails
                silent_fails = set(confirmed) - data_symbols
                if silent_fails:
                    print(f"\n   ⚠️  SILENT FAILS (response OK, но нет данных):")
                    for symbol in sorted(silent_fails)[:10]:
                        print(f"      - {symbol}")
                    if len(silent_fails) > 10:
                        print(f"      ... и еще {len(silent_fails) - 10}")

                # Success rate
                success_rate = (len(data_symbols) / len(symbols)) * 100
                print(f"\n   Реальный success rate: {success_rate:.1f}%")

                if success_rate < 50:
                    print(f"   🔴 КРИТИЧНО: Менее 50% подписок работают!")
                elif success_rate < 90:
                    print(f"   ⚠️  ПРОБЛЕМА: {100-success_rate:.1f}% подписок не работают")
                else:
                    print(f"   ✅ Большинство подписок работают")

                await ws.close()

    async def test_combined_stream(self, symbols: list):
        """Test combined stream approach (recommended by Binance)"""

        print(f"\n{'='*80}")
        print(f"ТЕСТ: Combined Stream подход ({len(symbols)} символов)")
        print(f"{'='*80}\n")

        # Build combined stream URL
        streams = [f"{s.lower()}@markPrice@1s" for s in symbols]
        combined_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

        print(f"📡 Combined stream URL длина: {len(combined_url)} символов")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(combined_url) as ws:
                    print(f"✅ WebSocket connected (combined stream)")

                    # Wait for data
                    print(f"\n📥 Waiting for data (10 seconds)...")
                    timeout_time = asyncio.get_event_loop().time() + 10

                    data_symbols = set()

                    while asyncio.get_event_loop().time() < timeout_time:
                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=1.0)

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)

                                # Combined stream format
                                if 'stream' in data and 'data' in data:
                                    payload = data['data']
                                    if 'e' in payload and payload['e'] == 'markPriceUpdate':
                                        data_symbols.add(payload['s'])

                                        if len(data_symbols) == 1:
                                            print(f"✅ First data: {payload['s']} @ {payload['p']}")

                        except asyncio.TimeoutError:
                            continue

                    print(f"\n📊 РЕЗУЛЬТАТЫ:")
                    print(f"   Запрошено символов: {len(symbols)}")
                    print(f"   Получено данных: {len(data_symbols)}")

                    success_rate = (len(data_symbols) / len(symbols)) * 100
                    print(f"   Success rate: {success_rate:.1f}%")

                    if success_rate > 95:
                        print(f"   ✅ Combined stream работает ЗНАЧИТЕЛЬНО ЛУЧШЕ!")

                    await ws.close()

            except Exception as e:
                print(f"❌ Error with combined stream: {e}")
                print(f"   Возможно URL слишком длинный или формат неправильный")


async def main():
    print("=" * 80)
    print("ТЕСТ #3: МОНИТОРИНГ WEBSOCKET ОТВЕТОВ BINANCE")
    print("=" * 80)
    print(f"Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()

    tester = BinanceWSSubscriptionTester()

    # Test 1: Single subscription
    await tester.test_single_subscription("BTCUSDT")

    await asyncio.sleep(2)

    # Test 2: Bulk subscription (как делает бот)
    test_symbols = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
        'ADAUSDT', 'DOGEUSDT', 'TRXUSDT', 'LINKUSDT', 'MATICUSDT',
        'AVAXUSDT', 'DOTUSDT', 'UNIUSDT', 'ATOMUSDT', 'NEARUSDT',
        'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT'
    ]

    await tester.test_bulk_subscription(test_symbols[:20], delay=0.1)

    await asyncio.sleep(2)

    # Test 3: Combined stream approach
    await tester.test_combined_stream(test_symbols[:10])

    print(f"\n{'='*80}")
    print("ВЫВОДЫ")
    print("=" * 80)
    print("""
1. Single subscription - проверяет базовую работу WebSocket
2. Bulk subscription - симулирует поведение бота (множество SUBSCRIBE)
3. Combined stream - рекомендуемый подход Binance

Если bulk subscription показывает низкий success rate, а combined stream
работает хорошо - это подтверждает что проблема в методе подписки!
    """)


if __name__ == "__main__":
    asyncio.run(main())
