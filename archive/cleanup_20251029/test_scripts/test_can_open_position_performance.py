#!/usr/bin/env python3
"""
ТЕСТОВЫЙ СКРИПТ: Измерение производительности can_open_position()

Измеряет:
1. Время каждого API вызова (fetch_balance, fetch_positions, positionRisk)
2. Общее время can_open_position()
3. Сравнение последовательных vs параллельных вызовов
4. Влияние на скорость открытия позиций

КРИТИЧЕСКИ ВАЖНО: ТОЛЬКО ИЗМЕРЕНИЕ! БЕЗ ИЗМЕНЕНИЯ КОДА!
"""
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager


async def measure_api_call(name: str, coro, timeout: float = 10.0) -> Dict:
    """Измерить время API вызова"""
    start = time.time()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        duration = time.time() - start
        return {
            'name': name,
            'success': True,
            'duration': duration,
            'result_size': len(result) if isinstance(result, (list, dict)) else 1
        }
    except asyncio.TimeoutError:
        duration = time.time() - start
        return {
            'name': name,
            'success': False,
            'duration': duration,
            'error': f'Timeout after {timeout}s'
        }
    except Exception as e:
        duration = time.time() - start
        return {
            'name': name,
            'success': False,
            'duration': duration,
            'error': str(e)[:100]
        }


async def test_individual_api_calls(exchange: ExchangeManager):
    """Тест 1: Измерить каждый API вызов отдельно"""
    print("\n" + "="*80)
    print("ТЕСТ 1: ИНДИВИДУАЛЬНЫЕ API ВЫЗОВЫ")
    print("="*80)

    results = []

    # Test 1.1: fetch_balance()
    print("\n📊 Testing: fetch_balance()")
    result = await measure_api_call(
        'fetch_balance',
        exchange.exchange.fetch_balance()
    )
    results.append(result)

    if result['success']:
        print(f"  ✅ Success: {result['duration']*1000:.2f}ms")
    else:
        print(f"  ❌ Error: {result['error']}")

    # Test 1.2: fetch_positions()
    print("\n📊 Testing: fetch_positions()")
    result = await measure_api_call(
        'fetch_positions',
        exchange.exchange.fetch_positions()
    )
    results.append(result)

    if result['success']:
        print(f"  ✅ Success: {result['duration']*1000:.2f}ms ({result['result_size']} positions)")
    else:
        print(f"  ❌ Error: {result['error']}")

    # Test 1.3: fapiPrivateV2GetPositionRisk() (Binance specific)
    if exchange.name == 'binance':
        print("\n📊 Testing: fapiPrivateV2GetPositionRisk()")
        try:
            result = await measure_api_call(
                'fapiPrivateV2GetPositionRisk',
                exchange.exchange.fapiPrivateV2GetPositionRisk({})
            )
            results.append(result)

            if result['success']:
                print(f"  ✅ Success: {result['duration']*1000:.2f}ms")
            else:
                print(f"  ❌ Error: {result['error']}")
        except Exception as e:
            print(f"  ⚠️  Skipped: {e}")

    # Summary
    print("\n" + "-"*80)
    print("ИТОГИ:")
    successful = [r for r in results if r['success']]
    if successful:
        total_time = sum(r['duration'] for r in successful)
        print(f"  Всего API вызовов: {len(successful)}")
        print(f"  Суммарное время: {total_time*1000:.2f}ms")
        print(f"  Среднее время: {(total_time/len(successful))*1000:.2f}ms")

    return results


async def test_can_open_position_single(exchange: ExchangeManager, symbol: str, size_usd: float):
    """Тест 2: Одиночный can_open_position()"""
    print("\n" + "="*80)
    print("ТЕСТ 2: ОДИНОЧНЫЙ can_open_position()")
    print("="*80)
    print(f"Symbol: {symbol}, Size: ${size_usd}")

    start = time.time()
    try:
        can_open, reason = await asyncio.wait_for(
            exchange.can_open_position(symbol, size_usd),
            timeout=10.0
        )
        duration = time.time() - start

        print(f"\n  ✅ Result: {can_open}")
        print(f"  Reason: {reason}")
        print(f"  ⏱️  Duration: {duration*1000:.2f}ms")

        return {
            'success': True,
            'duration': duration,
            'can_open': can_open,
            'reason': reason
        }
    except asyncio.TimeoutError:
        duration = time.time() - start
        print(f"\n  ❌ TIMEOUT after {duration:.2f}s")
        return {
            'success': False,
            'duration': duration,
            'error': 'Timeout'
        }
    except Exception as e:
        duration = time.time() - start
        print(f"\n  ❌ ERROR: {e}")
        return {
            'success': False,
            'duration': duration,
            'error': str(e)[:100]
        }


async def test_can_open_position_sequential(exchange: ExchangeManager, symbols: List[str], size_usd: float):
    """Тест 3: Последовательные can_open_position() (как сейчас)"""
    print("\n" + "="*80)
    print("ТЕСТ 3: ПОСЛЕДОВАТЕЛЬНЫЕ can_open_position()")
    print("="*80)
    print(f"Symbols: {', '.join(symbols)}, Size: ${size_usd}")

    results = []
    start_total = time.time()

    for i, symbol in enumerate(symbols, 1):
        print(f"\n  [{i}/{len(symbols)}] Checking {symbol}...")
        start = time.time()

        try:
            can_open, reason = await asyncio.wait_for(
                exchange.can_open_position(symbol, size_usd),
                timeout=10.0
            )
            duration = time.time() - start

            print(f"    ✅ {can_open}: {reason} ({duration*1000:.2f}ms)")

            results.append({
                'symbol': symbol,
                'success': True,
                'duration': duration,
                'can_open': can_open
            })
        except Exception as e:
            duration = time.time() - start
            print(f"    ❌ ERROR: {e} ({duration*1000:.2f}ms)")
            results.append({
                'symbol': symbol,
                'success': False,
                'duration': duration,
                'error': str(e)[:50]
            })

    total_duration = time.time() - start_total

    # Summary
    print("\n" + "-"*80)
    print("ИТОГИ:")
    successful = [r for r in results if r['success']]
    print(f"  Успешных проверок: {len(successful)}/{len(symbols)}")
    print(f"  Суммарное время: {total_duration*1000:.2f}ms")
    print(f"  Среднее на символ: {(total_duration/len(symbols))*1000:.2f}ms")

    if successful:
        durations = [r['duration'] for r in successful]
        print(f"  Min: {min(durations)*1000:.2f}ms")
        print(f"  Max: {max(durations)*1000:.2f}ms")

    return {
        'total_duration': total_duration,
        'avg_duration': total_duration / len(symbols),
        'results': results
    }


async def test_can_open_position_parallel(exchange: ExchangeManager, symbols: List[str], size_usd: float):
    """Тест 4: Параллельные can_open_position() (оптимизация)"""
    print("\n" + "="*80)
    print("ТЕСТ 4: ПАРАЛЛЕЛЬНЫЕ can_open_position() (если бы делали)")
    print("="*80)
    print(f"Symbols: {', '.join(symbols)}, Size: ${size_usd}")

    async def check_single(symbol):
        start = time.time()
        try:
            can_open, reason = await asyncio.wait_for(
                exchange.can_open_position(symbol, size_usd),
                timeout=10.0
            )
            duration = time.time() - start
            return {
                'symbol': symbol,
                'success': True,
                'duration': duration,
                'can_open': can_open,
                'reason': reason
            }
        except Exception as e:
            duration = time.time() - start
            return {
                'symbol': symbol,
                'success': False,
                'duration': duration,
                'error': str(e)[:50]
            }

    start_total = time.time()
    results = await asyncio.gather(*[check_single(s) for s in symbols])
    total_duration = time.time() - start_total

    # Display results
    print()
    for r in results:
        if r['success']:
            print(f"  ✅ {r['symbol']}: {r['can_open']} ({r['duration']*1000:.2f}ms)")
        else:
            print(f"  ❌ {r['symbol']}: ERROR ({r['duration']*1000:.2f}ms)")

    # Summary
    print("\n" + "-"*80)
    print("ИТОГИ:")
    successful = [r for r in results if r['success']]
    print(f"  Успешных проверок: {len(successful)}/{len(symbols)}")
    print(f"  Общее время (параллельно): {total_duration*1000:.2f}ms")

    if successful:
        durations = [r['duration'] for r in successful]
        avg_duration = sum(durations) / len(durations)
        print(f"  Среднее на символ: {avg_duration*1000:.2f}ms")
        print(f"  Max: {max(durations)*1000:.2f}ms (это и есть wall-clock time)")

    return {
        'total_duration': total_duration,
        'results': results
    }


async def main():
    print("="*80)
    print("ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ can_open_position()")
    print("="*80)
    print()
    print("Этот скрипт измеряет влияние can_open_position() на скорость волны")
    print()
    print("⚠️  ВАЖНО: Этот скрипт ТОЛЬКО ИЗМЕРЯЕТ, никаких изменений не делает!")
    print()

    # Initialize exchange
    config = Config()
    binance_config = config.get_exchange_config('binance')

    exchange = ExchangeManager('binance', {
        'api_key': binance_config.api_key,
        'api_secret': binance_config.api_secret,
        'testnet': binance_config.testnet,
        'rate_limit': binance_config.rate_limit
    })
    await exchange.initialize()

    print(f"✅ Подключено к Binance (testnet={binance_config.testnet})")

    # Test symbols (из реальной волны)
    test_symbols = ['FORMUSDT', 'ALICEUSDT', 'BNBUSDT', 'NEOUSDT', 'ALGOUSDT', 'FILUSDT']
    test_size = 200.0  # $200 как в реальной волне

    # Run tests
    api_results = await test_individual_api_calls(exchange)

    single_result = await test_can_open_position_single(exchange, 'FORMUSDT', test_size)

    sequential_result = await test_can_open_position_sequential(exchange, test_symbols, test_size)

    parallel_result = await test_can_open_position_parallel(exchange, test_symbols, test_size)

    # FINAL COMPARISON
    print("\n" + "="*80)
    print("ФИНАЛЬНОЕ СРАВНЕНИЕ")
    print("="*80)

    print("\n📊 ИНДИВИДУАЛЬНЫЕ API ВЫЗОВЫ:")
    successful_api = [r for r in api_results if r['success']]
    if successful_api:
        total_api = sum(r['duration'] for r in successful_api)
        print(f"  Время на 1 позицию (3 API): {total_api*1000:.2f}ms")
        print(f"  Время на 6 позиций: {total_api*6*1000:.2f}ms")

    print("\n📊 can_open_position() ПОСЛЕДОВАТЕЛЬНО (текущий подход):")
    print(f"  Время на 6 позиций: {sequential_result['total_duration']*1000:.2f}ms")
    print(f"  Среднее на позицию: {sequential_result['avg_duration']*1000:.2f}ms")

    print("\n📊 can_open_position() ПАРАЛЛЕЛЬНО (оптимизация):")
    print(f"  Время на 6 позиций: {parallel_result['total_duration']*1000:.2f}ms")

    # Calculate speedup
    if sequential_result['total_duration'] > 0 and parallel_result['total_duration'] > 0:
        speedup = sequential_result['total_duration'] / parallel_result['total_duration']
        saved_time = sequential_result['total_duration'] - parallel_result['total_duration']

        print("\n🚀 ВЫИГРЫШ ОТ ПАРАЛЛЕЛИЗАЦИИ:")
        print(f"  Ускорение: {speedup:.2f}x")
        print(f"  Экономия времени: {saved_time*1000:.2f}ms ({saved_time:.2f}s)")

    # Recommendations
    print("\n📋 РЕКОМЕНДАЦИИ:")

    if sequential_result['total_duration'] > 2.0:  # >2s считаем медленным
        print("  ⚠️  can_open_position() МЕДЛЕННЫЙ (>2s для 6 позиций)")
        print("  💡 Рекомендуется оптимизация:")
        print("     1. Кэшировать fetch_positions() на время волны")
        print("     2. Делать валидацию параллельно")
        print("     3. Пропускать positionRisk если не нужен")
    else:
        print("  ✅ can_open_position() приемлемо быстрый (<2s)")

    if parallel_result['total_duration'] < sequential_result['total_duration'] * 0.5:
        print("  🚀 Параллелизация даст значительный выигрыш (>50%)")
    else:
        print("  ⚠️  Параллелизация не сильно поможет (узкое место в другом)")

    await exchange.close()

    print("\n" + "="*80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("="*80)


if __name__ == '__main__':
    asyncio.run(main())
