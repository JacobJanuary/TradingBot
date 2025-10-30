#!/usr/bin/env python3
"""
Тест для верификации фикса Bybit OI в продакшен-боте.

Дата: 2025-10-29
Цель: Убедиться что метод _fetch_open_interest_usdt корректно работает для Bybit
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


async def test_bybit_oi_fix():
    """Тест фикса Bybit OI."""

    print("=" * 80)
    print("🧪 ТЕСТ BYBIT OI FIX")
    print("=" * 80)

    try:
        # Import после добавления в path
        from core.wave_signal_processor import WaveSignalProcessor
        from core.exchange_manager import ExchangeManager
        from config.settings import config

        # Create instances
        processor = WaveSignalProcessor(config)

        # Test Bybit symbols
        test_symbols = [
            'BTC/USDT:USDT',
            'ETH/USDT:USDT',
            'SOL/USDT:USDT'
        ]

        # Create Bybit exchange manager
        print("\n📡 Создание Bybit exchange manager...")
        exchange_manager = ExchangeManager('bybit', config)
        await exchange_manager.initialize()

        print("\n" + "=" * 80)
        print("🧪 ТЕСТИРОВАНИЕ BYBIT OI ПОЛУЧЕНИЯ")
        print("=" * 80)

        results = []

        for symbol in test_symbols:
            print(f"\n📊 Тестирование: {symbol}")
            print("-" * 80)

            try:
                # Get current price first
                ticker = await exchange_manager.fetch_ticker(symbol)
                current_price = ticker.get('last', 0)

                print(f"  💰 Current Price: ${current_price:,.2f}")

                # Test OI fetch
                oi_usdt = await processor._fetch_open_interest_usdt(
                    exchange_manager,
                    symbol,
                    'bybit',
                    current_price
                )

                if oi_usdt is not None and oi_usdt > 0:
                    print(f"  ✅ OI (USDT): ${oi_usdt:,.0f}")
                    print(f"  ✅ OI >= $1M: {oi_usdt >= 1_000_000}")
                    results.append({
                        'symbol': symbol,
                        'success': True,
                        'oi_usdt': oi_usdt,
                        'price': current_price
                    })
                else:
                    print(f"  ❌ OI fetch failed: {oi_usdt}")
                    results.append({
                        'symbol': symbol,
                        'success': False,
                        'oi_usdt': oi_usdt,
                        'price': current_price
                    })

            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                results.append({
                    'symbol': symbol,
                    'success': False,
                    'error': str(e)
                })

        # Close exchange
        await exchange_manager.close()

        # Summary
        print("\n" + "=" * 80)
        print("📊 РЕЗУЛЬТАТЫ")
        print("=" * 80)

        success_count = sum(1 for r in results if r.get('success'))
        total_count = len(results)

        print(f"\n✅ Успешно: {success_count}/{total_count}")

        if success_count == total_count:
            print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ! Bybit OI fix работает!")
            return 0
        elif success_count > 0:
            print("\n⚠️  ЧАСТИЧНЫЙ УСПЕХ: Некоторые тесты прошли")
            return 1
        else:
            print("\n❌ ВСЕ ТЕСТЫ ПРОВАЛИЛИСЬ")
            return 2

    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 3


if __name__ == '__main__':
    exit_code = asyncio.run(test_bybit_oi_fix())
    sys.exit(exit_code)
