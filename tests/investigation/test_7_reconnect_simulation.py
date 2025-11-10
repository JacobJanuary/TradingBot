#!/usr/bin/env python3
"""
ТЕСТ #7: Симуляция RECONNECT - воспроизведение проблемы из логов
"""

import asyncio
import json
from datetime import datetime, timezone
import aiohttp


class BinanceReconnectSimulator:
    """Simulate reconnect scenario like in production"""

    def __init__(self):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.next_id = 1
        self.subscribed_symbols = set()

    async def simulate_production_cycle(self, symbols: list):
        """Simulate what happens in production:
        1. Connect
        2. Subscribe to symbols
        3. Receive data
        4. DISCONNECT (simulated)
        5. RECONNECT
        6. RESTORE subscriptions (like _restore_subscriptions)
        """

        print(f"\n{'='*80}")
        print(f"СИМУЛЯЦИЯ PRODUCTION RECONNECT CYCLE")
        print(f"{'='*80}\n")

        print(f"Символов для тестирования: {len(symbols)}")

        # PHASE 1: Initial connection and subscription
        print(f"\n{'='*80}")
        print(f"ФАЗА 1: Первичное подключение и подписка")
        print(f"{'='*80}\n")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws1:
                print(f"✅ WebSocket connected (connection #1)")

                # Subscribe initially
                print(f"\n📤 Подписка на {len(symbols)} символов...")
                subscribe_ids = {}

                for i, symbol in enumerate(symbols):
                    stream_name = f"{symbol.lower()}@markPrice@1s"
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": [stream_name],
                        "id": self.next_id
                    }

                    subscribe_ids[self.next_id] = symbol
                    await ws1.send_str(json.dumps(subscribe_msg))
                    self.next_id += 1

                    if i < len(symbols) - 1:
                        await asyncio.sleep(0.1)

                print(f"✅ Все {len(symbols)} SUBSCRIBE отправлены")

                # Wait for responses and data
                print(f"\n📥 Ожидание подтверждений и данных (15s)...")
                timeout_time = asyncio.get_event_loop().time() + 15

                responses = {}
                data_symbols = set()

                while asyncio.get_event_loop().time() < timeout_time:
                    try:
                        msg = await asyncio.wait_for(ws1.receive(), timeout=1.0)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)

                            if 'id' in data and 'result' in data:
                                req_id = data['id']
                                if req_id in subscribe_ids:
                                    symbol = subscribe_ids[req_id]
                                    responses[symbol] = data['result']

                                    # Simulate bot behavior: add to subscribed_symbols
                                    if data['result'] is None:
                                        self.subscribed_symbols.add(symbol)

                            elif 'e' in data and data['e'] == 'markPriceUpdate':
                                data_symbols.add(data['s'])

                    except asyncio.TimeoutError:
                        continue

                print(f"\n📊 РЕЗУЛЬТАТЫ ФАЗЫ 1:")
                print(f"   Подписано (result=null): {len(self.subscribed_symbols)}")
                print(f"   Получено данных от:      {len(data_symbols)}")
                print(f"   Success rate:            {len(data_symbols)/len(symbols)*100:.1f}%")

                # PHASE 2: RECONNECT (after some time, like in production)
                print(f"\n{'='*80}")
                print(f"ФАЗА 2: RECONNECT (симуляция periodic reconnect)")
                print(f"{'='*80}\n")

                print(f"⏸️  Симуляция работы соединения 30 секунд...")
                await asyncio.sleep(30)

                print(f"🔌 Закрываем WebSocket (симуляция reconnect)...")
                await ws1.close()

        # PHASE 3: Restore subscriptions on new connection
        print(f"\n{'='*80}")
        print(f"ФАЗА 3: ВОССТАНОВЛЕНИЕ ПОДПИСОК (как _restore_subscriptions)")
        print(f"{'='*80}\n")

        # Simulate bot's _restore_subscriptions logic
        symbols_to_restore = list(self.subscribed_symbols)
        print(f"📋 Символов для восстановления: {len(symbols_to_restore)}")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws2:
                print(f"✅ WebSocket reconnected (connection #2)")

                # THIS IS THE CRITICAL PART - simulating bot's restore logic
                print(f"\n📤 Восстановление подписок (как в боте)...")

                # Simulate: clear sets (like in bot code line 777-778)
                original_subscribed = self.subscribed_symbols.copy()
                self.subscribed_symbols.clear()  # ❌ Clear BEFORE restore!

                restore_ids = {}
                restored = 0

                for i, symbol in enumerate(symbols_to_restore):
                    stream_name = f"{symbol.lower()}@markPrice@1s"
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": [stream_name],
                        "id": self.next_id
                    }

                    restore_ids[self.next_id] = symbol
                    await ws2.send_str(json.dumps(subscribe_msg))
                    self.next_id += 1
                    restored += 1

                    # Delay like in bot (0.1s)
                    if i < len(symbols_to_restore) - 1:
                        await asyncio.sleep(0.1)

                print(f"✅ Отправлено {restored} restore requests")

                # Wait for responses and data
                print(f"\n📥 Ожидание подтверждений и данных (25s)...")
                timeout_time = asyncio.get_event_loop().time() + 25

                restore_responses = {}
                restore_data_symbols = set()

                while asyncio.get_event_loop().time() < timeout_time:
                    try:
                        msg = await asyncio.wait_for(ws2.receive(), timeout=1.0)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)

                            if 'id' in data and 'result' in data:
                                req_id = data['id']
                                if req_id in restore_ids:
                                    symbol = restore_ids[req_id]
                                    restore_responses[symbol] = data['result']

                                    # Simulate bot: add back to subscribed_symbols
                                    if data['result'] is None:
                                        self.subscribed_symbols.add(symbol)

                            elif 'e' in data and data['e'] == 'markPriceUpdate':
                                restore_data_symbols.add(data['s'])

                    except asyncio.TimeoutError:
                        continue

                # Analysis
                print(f"\n{'='*80}")
                print(f"📊 РЕЗУЛЬТАТЫ ФАЗЫ 3 (RESTORE)")
                print(f"{'='*80}\n")

                print(f"Попытка восстановить:       {len(symbols_to_restore)}")
                print(f"Получено responses:         {len(restore_responses)}")
                print(f"Ответов 'result: null':     {sum(1 for r in restore_responses.values() if r is None)}")
                print(f"Получено РЕАЛЬНЫХ данных:   {len(restore_data_symbols)}")

                # Silent fails
                confirmed = set(s for s, r in restore_responses.items() if r is None)
                silent_fails = confirmed - restore_data_symbols

                if silent_fails:
                    print(f"\n⚠️  SILENT FAILS: {len(silent_fails)}")
                    for symbol in sorted(list(silent_fails)[:15]):
                        print(f"   - {symbol}")
                    if len(silent_fails) > 15:
                        print(f"   ... и еще {len(silent_fails) - 15}")

                # Compare with logs
                success_rate = (len(restore_data_symbols) / len(symbols_to_restore)) * 100
                silent_fail_rate = (len(silent_fails) / len(symbols_to_restore)) * 100

                print(f"\n{'='*80}")
                print(f"📈 ИТОГОВАЯ СТАТИСТИКА")
                print(f"{'='*80}")
                print(f"Success rate:     {success_rate:.1f}%")
                print(f"Silent fail rate: {silent_fail_rate:.1f}%")

                print(f"\nСравнение с production логами:")
                print(f"   Тест:       {success_rate:.1f}% success")
                print(f"   Production: 12-14% success (из логов)")

                if silent_fail_rate > 50:
                    print(f"\n🔴 ПРОБЛЕМА ВОСПРОИЗВЕДЕНА!")
                    print(f"   Silent fail rate {silent_fail_rate:.1f}% близок к production (86-89%)")
                elif silent_fail_rate > 20:
                    print(f"\n⚠️  Частичное воспроизведение проблемы")
                else:
                    print(f"\n✅ Проблема НЕ воспроизведена")

                await ws2.close()

                return {
                    'initial_success': len(data_symbols),
                    'restore_success': len(restore_data_symbols),
                    'silent_fails': len(silent_fails),
                    'success_rate': success_rate
                }


async def main():
    print("=" * 80)
    print("ТЕСТ #7: СИМУЛЯЦИЯ RECONNECT КАК В PRODUCTION")
    print("=" * 80)
    print(f"Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("\nЦель: Воспроизвести silent fails при reconnect\n")

    simulator = BinanceReconnectSimulator()

    # Real symbols from production logs
    symbols = [
        'ALCHUSDT', 'ATAUSDT', 'MEMEUSDT', 'DUSKUSDT', 'ENJUSDT', 'MOVEUSDT',
        'MAVUSDT', 'ILVUSDT', 'SSVUSDT', 'B2USDT', 'USUALUSDT', 'ZETAUSDT',
        'TLMUSDT', 'KSMUSDT', 'EPICUSDT', 'DYMUSDT', 'TIAUSDT', 'FUSDT',
        'ACEUSDT', 'EGLDUSDT', 'XAIUSDT', 'PUNDIXUSDT', 'ZBTUSDT', 'LSKUSDT',
        'FLUXUSDT', 'FLMUSDT', 'SOMIUSDT', 'JASMYUSDT', 'SUSHIUSDT', 'DOLOUSDT',
        'NEARUSDT', 'NMRUSDT', 'SANDUSDT', 'CHZUSDT', 'YFIUSDT', 'RLCUSDT',
        'DAMUSDT', 'BLUAIUSDT', 'TANSSIUSDT', 'SYNUSDT', '1000FLOKIUSDT',
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'
    ]

    result = await simulator.simulate_production_cycle(symbols[:47])

    print(f"\n{'='*80}")
    print("ФИНАЛЬНЫЕ ВЫВОДЫ")
    print("="*80)

    if result['silent_fails'] > 20:
        print(f"\n✅ Проблема успешно воспроизведена!")
        print(f"\nКлючевые факторы:")
        print(f"   1. Long-lived connection перед reconnect")
        print(f"   2. Массовая restore подписок")
        print(f"   3. Недостаточный delay (0.1s)")
        print(f"   4. Очистка subscribed_symbols ДО восстановления")
    else:
        print(f"\n⚠️  Проблема частично/не воспроизведена")
        print(f"\nВозможные причины отличия от production:")
        print(f"   1. Время работы соединения (production: часы, тест: 30s)")
        print(f"   2. Нагрузка на Binance API")
        print(f"   3. Качество сетевого соединения")
        print(f"   4. Накопленное состояние WebSocket")


if __name__ == "__main__":
    asyncio.run(main())
