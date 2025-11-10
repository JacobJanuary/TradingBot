#!/usr/bin/env python3
"""
ТЕСТ #6: Проверка лимитов массовой подписки - поиск точки отказа
"""

import asyncio
import json
from datetime import datetime, timezone
import aiohttp


class BinanceBulkSubscriptionTester:
    """Test bulk subscription with increasing number of symbols"""

    def __init__(self):
        self.ws_url = "wss://fstream.binance.com/ws"
        self.next_id = 1

    async def test_bulk_with_count(self, symbols: list, delay: float = 0.1, wait_time: int = 20):
        """Test bulk subscription with specific symbol count"""

        symbol_count = len(symbols)
        print(f"\n{'='*80}")
        print(f"ТЕСТ: Массовая подписка {symbol_count} символов (delay={delay}s)")
        print(f"{'='*80}\n")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ws_url) as ws:
                print(f"✅ WebSocket connected")

                # Subscribe to all symbols
                subscribe_ids = {}
                start_time = asyncio.get_event_loop().time()

                print(f"\n📤 Отправка {symbol_count} SUBSCRIBE запросов...")
                for i, symbol in enumerate(symbols):
                    stream_name = f"{symbol.lower()}@markPrice@1s"
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": [stream_name],
                        "id": self.next_id
                    }

                    subscribe_ids[self.next_id] = symbol
                    await ws.send_str(json.dumps(subscribe_msg))

                    if (i + 1) % 10 == 0 or (i + 1) == symbol_count:
                        print(f"   Sent {i+1}/{symbol_count}...")

                    self.next_id += 1

                    if i < len(symbols) - 1:
                        await asyncio.sleep(delay)

                send_time = asyncio.get_event_loop().time() - start_time
                print(f"✅ Все SUBSCRIBE отправлены за {send_time:.2f}s")

                # Wait for responses
                print(f"\n📥 Ожидание ответов и данных ({wait_time} секунд)...")
                timeout_time = asyncio.get_event_loop().time() + wait_time

                responses = {}
                data_symbols = set()
                errors = []

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

                                    # Check for errors
                                    if data['result'] is not None:
                                        errors.append({'symbol': symbol, 'error': data['result']})

                            # Data
                            elif 'e' in data and data['e'] == 'markPriceUpdate':
                                data_symbols.add(data['s'])

                                if len(data_symbols) == 1:
                                    print(f"✅ First data received at {asyncio.get_event_loop().time() - start_time:.2f}s")

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"❌ WebSocket error: {msg.data}")

                    except asyncio.TimeoutError:
                        continue

                # Analysis
                print(f"\n{'='*80}")
                print(f"📊 ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ")
                print(f"{'='*80}\n")

                print(f"Запрошено подписок:        {symbol_count}")
                print(f"Получено responses:        {len(responses)}")
                print(f"Ответов 'result: null':    {sum(1 for r in responses.values() if r is None)}")
                print(f"Получено РЕАЛЬНЫХ данных:  {len(data_symbols)}")

                if errors:
                    print(f"\n❌ ОШИБКИ при подписке:")
                    for err in errors[:5]:
                        print(f"   - {err['symbol']}: {err['error']}")
                    if len(errors) > 5:
                        print(f"   ... и еще {len(errors) - 5}")

                # Find silent fails
                confirmed = set(s for s, r in responses.items() if r is None)
                silent_fails = confirmed - data_symbols

                if silent_fails:
                    print(f"\n⚠️  SILENT FAILS (response OK, НО НЕТ ДАННЫХ): {len(silent_fails)}")
                    for symbol in sorted(list(silent_fails)[:20]):
                        print(f"   - {symbol}")
                    if len(silent_fails) > 20:
                        print(f"   ... и еще {len(silent_fails) - 20}")

                # Missing responses
                no_response = set(symbols) - set(responses.keys())
                if no_response:
                    print(f"\n❌ НЕТ RESPONSE: {len(no_response)}")
                    for symbol in sorted(list(no_response)[:10]):
                        print(f"   - {symbol}")

                # Success rate
                success_rate = (len(data_symbols) / symbol_count) * 100
                silent_fail_rate = (len(silent_fails) / symbol_count) * 100

                print(f"\n{'='*80}")
                print(f"📈 СТАТИСТИКА")
                print(f"{'='*80}")
                print(f"Success rate (данные получены):  {success_rate:.1f}%")
                print(f"Silent fail rate:                 {silent_fail_rate:.1f}%")
                print(f"Response rate:                    {len(responses)/symbol_count*100:.1f}%")

                if success_rate < 50:
                    print(f"\n🔴 КРИТИЧНО: Менее 50% подписок работают!")
                elif success_rate < 90:
                    print(f"\n⚠️  ПРОБЛЕМА: {100-success_rate:.1f}% подписок не работают")
                else:
                    print(f"\n✅ Success rate приемлемый")

                await ws.close()

                return {
                    'total': symbol_count,
                    'success': len(data_symbols),
                    'silent_fails': len(silent_fails),
                    'no_response': len(no_response),
                    'errors': len(errors),
                    'success_rate': success_rate
                }


async def main():
    print("=" * 80)
    print("ТЕСТ #6: ПОИСК ЛИМИТА МАССОВОЙ ПОДПИСКИ")
    print("=" * 80)
    print(f"Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("\nЦель: Найти точное количество символов где начинаются silent fails\n")

    tester = BinanceBulkSubscriptionTester()

    # Символы из логов бота (реальные проблемные)
    problematic_symbols = [
        'ALCHUSDT', 'ATAUSDT', 'MEMEUSDT', 'DUSKUSDT', 'ENJUSDT', 'MOVEUSDT',
        'MAVUSDT', 'ILVUSDT', 'SSVUSDT', 'B2USDT', 'USUALUSDT', 'ZETAUSDT',
        'TLMUSDT', 'KSMUSDT', 'EPICUSDT', 'DYMUSDT', 'TIAUSDT', 'FUSDT',
        'ACEUSDT', 'EGLDUSDT', 'XAIUSDT', 'PUNDIXUSDT', 'ZBTUSDT', 'LSKUSDT',
        'FLUXUSDT', 'FLMUSDT', 'SOMIUSDT', 'JASMYUSDT', 'SUSHIUSDT', 'DOLOUSDT',
        'NEARUSDT', 'NMRUSDT', 'SANDUSDT', 'CHZUSDT', 'YFIUSDT', 'RLCUSDT',
        'DAMUSDT', 'BLUAIUSDT', 'TANSSIUSDT', 'SYNUSDT', '1000FLOKIUSDT'
    ]

    # Добавим еще символов чтобы получить 47 как в логах
    additional_symbols = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT'
    ]

    all_symbols = problematic_symbols + additional_symbols

    # Test with exact count from logs (47)
    print("\n" + "="*80)
    print("ОСНОВНОЙ ТЕСТ: 47 символов (как в логах бота)")
    print("="*80)
    result_47 = await tester.test_bulk_with_count(all_symbols[:47], delay=0.1, wait_time=25)

    await asyncio.sleep(3)

    # Test with different delays
    print("\n" + "="*80)
    print("ДОПОЛНИТЕЛЬНЫЙ ТЕСТ: 47 символов с delay=0.5s")
    print("="*80)
    result_47_slow = await tester.test_bulk_with_count(all_symbols[:47], delay=0.5, wait_time=30)

    await asyncio.sleep(3)

    # Test with smaller count
    print("\n" + "="*80)
    print("КОНТРОЛЬНЫЙ ТЕСТ: 30 символов с delay=0.1s")
    print("="*80)
    result_30 = await tester.test_bulk_with_count(all_symbols[:30], delay=0.1, wait_time=20)

    # Summary
    print("\n" + "="*80)
    print("ИТОГОВОЕ СРАВНЕНИЕ")
    print("="*80)
    print(f"\n30 символов (delay=0.1s):  {result_30['success_rate']:.1f}% success, {result_30['silent_fails']} silent fails")
    print(f"47 символов (delay=0.1s):  {result_47['success_rate']:.1f}% success, {result_47['silent_fails']} silent fails")
    print(f"47 символов (delay=0.5s):  {result_47_slow['success_rate']:.1f}% success, {result_47_slow['silent_fails']} silent fails")

    print(f"\n{'='*80}")
    print("ВЫВОДЫ")
    print("="*80)

    if result_47['success_rate'] < 50:
        print("\n🔴 ПРОБЛЕМА ВОСПРОИЗВЕДЕНА!")
        print(f"   С 47 символами success rate только {result_47['success_rate']:.1f}%")
        print(f"   Silent fails: {result_47['silent_fails']} ({result_47['silent_fails']/result_47['total']*100:.1f}%)")

        if result_47_slow['success_rate'] > result_47['success_rate']:
            print(f"\n✅ Увеличение delay помогает:")
            print(f"   0.1s delay: {result_47['success_rate']:.1f}%")
            print(f"   0.5s delay: {result_47_slow['success_rate']:.1f}%")
            print(f"   Улучшение: +{result_47_slow['success_rate'] - result_47['success_rate']:.1f}%")
    else:
        print(f"\n⚠️  Проблема НЕ воспроизведена в тестовой среде")
        print(f"   Возможно это зависит от:")
        print(f"   - Времени суток / нагрузки на Binance")
        print(f"   - Статуса WebSocket соединения")
        print(f"   - Продолжительности соединения")


if __name__ == "__main__":
    asyncio.run(main())
