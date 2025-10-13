#!/usr/bin/env python3
"""
ДИАГНОСТИКА: Проверка _validate_and_adjust_amount()

Цель: 100% подтвердить что проблема в округлении до 0.0
"""

import asyncio
from decimal import Decimal, ROUND_DOWN
from config.settings import Config
from core.exchange_manager import ExchangeManager

async def test_validation():
    print("=" * 80)
    print("🔍 ДИАГНОСТИКА: _validate_and_adjust_amount()")
    print("=" * 80)
    print()

    config = Config()

    # Инициализируем exchange managers
    exchanges = {}
    for name in ['binance', 'bybit']:
        if name in config.exchanges:
            ex_config = config.exchanges[name]
            # Convert ExchangeConfig to dict
            config_dict = {
                'api_key': ex_config.api_key,
                'api_secret': ex_config.api_secret,
                'testnet': ex_config.testnet
            }
            exchanges[name] = ExchangeManager(name, config_dict)
            await exchanges[name].initialize()

    # Проблемные символы из логов
    test_cases = [
        ('bybit', 'FRAGUSDT', 1298, 'Entry ордер работал, SL failed'),
        ('bybit', 'ORBSUSDT', 11990, 'Entry ордер работал, SL failed'),
        ('bybit', 'PEAQUSDT', 1280, 'Entry ордер работал, SL failed'),
        ('bybit', 'SOLAYERUSDT', 173, 'Entry ордер работал, SL failed'),
        ('bybit', 'WAVESUSDT', 200, 'Entry ордер работал, SL failed'),
    ]

    print("Тестируем проблемные символы:")
    print()

    failures = []

    for exchange_name, symbol, expected_amount, note in test_cases:
        exchange = exchanges.get(exchange_name)
        if not exchange:
            print(f"⚠️  {exchange_name} не инициализирован, пропускаем {symbol}")
            continue

        # Форматируем символ для биржи
        exchange_symbol = exchange.find_exchange_symbol(symbol)
        if not exchange_symbol:
            print(f"❌ {symbol} не найден на {exchange_name}")
            continue

        print(f"📊 Тестируем: {symbol} ({exchange_name})")
        print(f"   Входной amount: {expected_amount}")
        print(f"   Примечание: {note}")

        try:
            # Получаем market info
            market = exchange.exchange.market(exchange_symbol)
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            min_amount = amount_limits.get('min', 0)
            max_amount = amount_limits.get('max', float('inf'))

            # Получаем precision
            precision = market.get('precision', {})
            amount_precision = precision.get('amount', 8)

            print(f"   Market info:")
            print(f"     - Min amount: {min_amount}")
            print(f"     - Max amount: {max_amount}")
            print(f"     - Precision: {amount_precision}")

            # Вызываем валидацию
            validated_amount = await exchange._validate_and_adjust_amount(
                exchange_symbol,
                float(expected_amount)
            )

            print(f"   Результат валидации: {validated_amount}")

            # Проверяем результат
            if validated_amount == 0.0:
                print(f"   ❌ ПРОБЛЕМА! Amount стал 0.0")
                failures.append({
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'input': expected_amount,
                    'output': validated_amount,
                    'min': min_amount,
                    'precision': amount_precision
                })
            elif validated_amount < min_amount:
                print(f"   ⚠️  Amount {validated_amount} < min {min_amount}")
                failures.append({
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'input': expected_amount,
                    'output': validated_amount,
                    'min': min_amount,
                    'precision': amount_precision
                })
            else:
                print(f"   ✅ OK - Amount прошел валидацию")

            # Тестируем quantize напрямую для понимания
            print(f"   Тестируем quantize с ROUND_DOWN:")
            safe_precision = max(0, min(int(amount_precision), 18))
            step_size = 10 ** -safe_precision
            amount_decimal = Decimal(str(expected_amount))
            step_decimal = Decimal(str(step_size))
            quantized = float(amount_decimal.quantize(step_decimal, rounding=ROUND_DOWN))
            print(f"     - Safe precision: {safe_precision}")
            print(f"     - Step size: {step_size}")
            print(f"     - Quantized result: {quantized}")

            print()

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            print()
            import traceback
            traceback.print_exc()

    # Итоги
    print("=" * 80)
    print("📊 ИТОГОВЫЙ ДИАГНОЗ")
    print("=" * 80)
    print()

    if failures:
        print(f"❌ Найдено {len(failures)} проблем:")
        print()
        for f in failures:
            print(f"  {f['symbol']} ({f['exchange']}):")
            print(f"    Input: {f['input']} → Output: {f['output']}")
            print(f"    Min required: {f['min']}")
            print(f"    Precision: {f['precision']}")
            print()

        print("🎯 ДИАГНОЗ ПОДТВЕРЖДЕН:")
        print("  - _validate_and_adjust_amount() возвращает 0.0 или amount < min")
        print("  - Проблема в округлении с ROUND_DOWN")
        print("  - Нужен фикс!")
    else:
        print("✅ Все тесты прошли успешно")
        print("⚠️  Проблема НЕ воспроизводится - возможно изменились условия")

    # Закрываем connections
    for exchange in exchanges.values():
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_validation())
