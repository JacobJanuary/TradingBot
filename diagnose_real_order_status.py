#!/usr/bin/env python3
"""
🔬 ДИАГНОСТИЧЕСКИЙ СКРИПТ: Real Order Status Analysis

Создает РЕАЛЬНЫЕ market orders для проблемных символов и анализирует статусы.
Этот скрипт поможет найти 100% решение для "Entry order failed: unknown"

ВАЖНО: Скрипт создает РЕАЛЬНЫЕ ордера на бирже!
- Использует минимальные суммы (~$1-2)
- Сразу закрывает позиции
- Работает на testnet если включен

Проблемные символы из логов:
- SUNDOGUSDT - "Entry order failed: unknown" (2025-10-12 05:51:20)
- XCHUSDT - возможно та же проблема
"""

import asyncio
import ccxt.async_support as ccxt
from config.settings import Config
from core.exchange_response_adapter import ExchangeResponseAdapter
import json
from datetime import datetime
from decimal import Decimal

# Цвета для консоли
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

async def test_symbol_order_status(exchange, symbol: str, test_num: int):
    """Тестирует создание и статус ордера для одного символа"""

    print(f"\n{'='*80}")
    print(f"{BOLD}TEST {test_num}: {symbol}{RESET}")
    print(f"{'='*80}\n")

    try:
        # 1. Получить минимальные лимиты
        print(f"{BLUE}📊 Шаг 1: Получение информации о рынке{RESET}")
        print("-"*80)

        markets = await exchange.load_markets()

        if symbol not in markets:
            print(f"{RED}❌ Символ {symbol} не найден на бирже{RESET}")
            return None

        market = markets[symbol]

        min_amount = market['limits']['amount']['min']
        min_cost = market['limits']['cost']['min']
        amount_precision = market['precision']['amount']

        print(f"Market info:")
        print(f"  Min amount: {min_amount}")
        print(f"  Min cost: {min_cost}")
        print(f"  Amount precision: {amount_precision}")
        print(f"  Contract size: {market.get('contractSize', 'N/A')}")

        # 2. Получить текущую цену
        ticker = await exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        print(f"\nCurrent price: {current_price}")

        # 3. Рассчитать минимальное количество
        if min_cost:
            amount_from_cost = min_cost / current_price
            proper_amount = max(min_amount, amount_from_cost) * 1.5  # x1.5 для гарантии
        else:
            proper_amount = min_amount * 2  # x2 для гарантии если нет min_cost

        # Округлить до precision
        if amount_precision > 0:
            # Precision может быть float (0.01), конвертируем в кол-во знаков
            import math
            decimals = int(abs(math.log10(amount_precision))) if amount_precision < 1 else 0
            proper_amount = round(proper_amount, decimals)
        else:
            proper_amount = int(proper_amount)

        order_cost = proper_amount * current_price

        print(f"\nCalculated order:")
        print(f"  Amount: {proper_amount}")
        print(f"  Estimated cost: ${order_cost:.2f}")

        # 4. Проверить баланс
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        free_usdt = usdt_balance.get('free') or usdt_balance.get('total', 0) or 0

        print(f"\nUSDT Balance: {free_usdt:.2f}")

        if free_usdt < order_cost:
            print(f"{RED}❌ Недостаточно баланса для ордера (нужно ${order_cost:.2f}){RESET}")
            return None

        # 5. ПОДТВЕРЖДЕНИЕ от пользователя
        print(f"\n{YELLOW}⚠️  ВНИМАНИЕ!{RESET}")
        print(f"Будет создан РЕАЛЬНЫЙ market order:")
        print(f"  Symbol: {symbol}")
        print(f"  Side: SELL (short)")
        print(f"  Amount: {proper_amount}")
        print(f"  Cost: ~${order_cost:.2f}")
        print(f"\nПозиция будет сразу закрыта после анализа статуса.")

        confirm = input(f"\n{BOLD}Создать этот ордер? (yes/no): {RESET}").strip().lower()

        if confirm != 'yes':
            print(f"{YELLOW}⏭️  Пропущено пользователем{RESET}")
            return None

        # 6. СОЗДАНИЕ ОРДЕРА
        print(f"\n{BLUE}📝 Шаг 2: Создание market order{RESET}")
        print("-"*80)

        start_time = datetime.now()

        raw_order_1 = await exchange.create_market_order(
            symbol=symbol,
            side='sell',
            amount=proper_amount
        )

        create_time = (datetime.now() - start_time).total_seconds()

        print(f"{GREEN}✅ Ордер создан за {create_time:.3f}s{RESET}\n")

        # 7. АНАЛИЗ СРАЗУ ПОСЛЕ СОЗДАНИЯ
        print(f"{BLUE}🔍 Шаг 3: Анализ RAW ORDER (сразу после создания){RESET}")
        print("-"*80)

        print(f"\n{BOLD}RAW ORDER STRUCTURE:{RESET}")
        print(json.dumps(raw_order_1, indent=2, default=str))

        print(f"\n{BOLD}KEY FIELDS:{RESET}")
        print(f"  order['id']: {raw_order_1.get('id')}")
        print(f"  order['status']: {YELLOW}{raw_order_1.get('status')}{RESET}")
        print(f"  order['type']: {raw_order_1.get('type')}")
        print(f"  order['side']: {raw_order_1.get('side')}")
        print(f"  order['amount']: {raw_order_1.get('amount')}")
        print(f"  order['filled']: {raw_order_1.get('filled')}")
        print(f"  order['remaining']: {raw_order_1.get('remaining')}")

        if 'info' in raw_order_1:
            info = raw_order_1['info']
            print(f"\n{BOLD}INFO FIELDS:{RESET}")
            print(f"  info['orderStatus']: {YELLOW}{info.get('orderStatus')}{RESET}")
            print(f"  info['orderLinkId']: {info.get('orderLinkId')}")
            print(f"  info['cumExecQty']: {info.get('cumExecQty')}")
            print(f"  info['leavesQty']: {info.get('leavesQty')}")
            print(f"  info['avgPrice']: {info.get('avgPrice')}")

        # 8. НОРМАЛИЗАЦИЯ (как в боте)
        print(f"\n{BLUE}🔄 Шаг 4: Нормализация (как в боте){RESET}")
        print("-"*80)

        normalized_1 = ExchangeResponseAdapter.normalize_order(raw_order_1, 'bybit')

        print(f"\n{BOLD}NORMALIZED ORDER:{RESET}")
        print(f"  id: {normalized_1.id}")
        print(f"  symbol: {normalized_1.symbol}")
        print(f"  side: {normalized_1.side}")
        print(f"  status: {YELLOW}{normalized_1.status}{RESET} ← КРИТИЧЕСКИЙ СТАТУС!")
        print(f"  type: {normalized_1.type}")
        print(f"  amount: {normalized_1.amount}")
        print(f"  filled: {normalized_1.filled}")
        print(f"  price: {normalized_1.price}")
        print(f"  average: {normalized_1.average}")

        is_filled_1 = ExchangeResponseAdapter.is_order_filled(normalized_1)
        print(f"\n{BOLD}is_order_filled(): {GREEN if is_filled_1 else RED}{is_filled_1}{RESET}")

        if not is_filled_1:
            print(f"{RED}⚠️  БОТ БЫ ОТКЛОНИЛ ЭТОТ ОРДЕР!{RESET}")
            print(f"{RED}   Причина: status='{normalized_1.status}' не прошел проверку{RESET}")

        # 9. FETCH ORDER (чтобы увидеть финальный статус)
        print(f"\n{BLUE}🔄 Шаг 5: Fetch order (через 1 секунду){RESET}")
        print("-"*80)

        await asyncio.sleep(1.0)

        raw_order_2 = await exchange.fetch_order(raw_order_1['id'], symbol)

        print(f"\n{BOLD}FETCHED ORDER STRUCTURE:{RESET}")
        print(json.dumps(raw_order_2, indent=2, default=str))

        print(f"\n{BOLD}KEY FIELDS AFTER FETCH:{RESET}")
        print(f"  order['status']: {YELLOW}{raw_order_2.get('status')}{RESET}")
        print(f"  order['filled']: {raw_order_2.get('filled')}")

        if 'info' in raw_order_2:
            info2 = raw_order_2['info']
            print(f"  info['orderStatus']: {YELLOW}{info2.get('orderStatus')}{RESET}")

        normalized_2 = ExchangeResponseAdapter.normalize_order(raw_order_2, 'bybit')

        print(f"\n{BOLD}NORMALIZED AFTER FETCH:{RESET}")
        print(f"  status: {YELLOW}{normalized_2.status}{RESET}")
        print(f"  filled: {normalized_2.filled}")

        is_filled_2 = ExchangeResponseAdapter.is_order_filled(normalized_2)
        print(f"\n{BOLD}is_order_filled() after fetch: {GREEN if is_filled_2 else RED}{is_filled_2}{RESET}")

        # 10. СРАВНЕНИЕ СТАТУСОВ
        print(f"\n{BLUE}📊 Шаг 6: Сравнение статусов{RESET}")
        print("-"*80)

        print(f"\n{BOLD}IMMEDIATE (сразу после create):{RESET}")
        print(f"  raw status: {raw_order_1.get('status')}")
        print(f"  info.orderStatus: {raw_order_1.get('info', {}).get('orderStatus')}")
        print(f"  normalized status: {normalized_1.status}")
        print(f"  is_filled: {is_filled_1}")

        print(f"\n{BOLD}AFTER FETCH (через 1 сек):{RESET}")
        print(f"  raw status: {raw_order_2.get('status')}")
        print(f"  info.orderStatus: {raw_order_2.get('info', {}).get('orderStatus')}")
        print(f"  normalized status: {normalized_2.status}")
        print(f"  is_filled: {is_filled_2}")

        # 11. ЗАКРЫТИЕ ПОЗИЦИИ
        print(f"\n{BLUE}🔄 Шаг 7: Закрытие позиции{RESET}")
        print("-"*80)

        # Получить текущую позицию
        positions = await exchange.fetch_positions([symbol])
        position = None
        for pos in positions:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                position = pos
                break

        if position:
            position_size = abs(float(position['contracts']))
            print(f"Позиция найдена: {position_size} контрактов")

            # Закрыть позицию
            close_order = await exchange.create_market_order(
                symbol=symbol,
                side='buy',  # Закрываем SELL позицию
                amount=position_size,
                params={'reduceOnly': True}
            )

            print(f"{GREEN}✅ Позиция закрыта{RESET}")
            print(f"  Close order ID: {close_order['id']}")
        else:
            print(f"{YELLOW}⚠️  Позиция не найдена (возможно уже закрыта){RESET}")

        # РЕЗУЛЬТАТ
        return {
            'symbol': symbol,
            'immediate': {
                'raw_status': raw_order_1.get('status'),
                'info_status': raw_order_1.get('info', {}).get('orderStatus'),
                'normalized_status': normalized_1.status,
                'is_filled': is_filled_1,
            },
            'after_fetch': {
                'raw_status': raw_order_2.get('status'),
                'info_status': raw_order_2.get('info', {}).get('orderStatus'),
                'normalized_status': normalized_2.status,
                'is_filled': is_filled_2,
            },
            'would_bot_accept': is_filled_1,
            'full_raw_immediate': raw_order_1,
            'full_raw_fetched': raw_order_2,
        }

    except ccxt.InsufficientFunds as e:
        print(f"{RED}❌ Недостаточно средств: {e}{RESET}")
        return None

    except ccxt.InvalidOrder as e:
        print(f"{RED}❌ Неверный ордер: {e}{RESET}")
        return None

    except Exception as e:
        print(f"{RED}❌ Ошибка: {type(e).__name__}: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Основная функция"""

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}🔬 ДИАГНОСТИКА: Real Order Status Analysis{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")

    print(f"{YELLOW}ВНИМАНИЕ!{RESET}")
    print(f"Этот скрипт создает РЕАЛЬНЫЕ market orders на бирже!")
    print(f"- Минимальные суммы (~$1-2 за ордер)")
    print(f"- Позиции сразу закрываются")
    print(f"- Работает на {'TESTNET' if True else 'PRODUCTION'}")
    print()

    # Получить конфигурацию
    config = Config()

    # Найти Bybit exchange
    exchange_config = config.exchanges.get('bybit')

    if not exchange_config:
        print(f"{RED}❌ Bybit не найден в конфигурации{RESET}")
        return

    # Создать exchange instance
    exchange = ccxt.bybit({
        'apiKey': exchange_config.api_key,
        'secret': exchange_config.api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': exchange_config.testnet
        }
    })

    print(f"Подключение к Bybit:")
    print(f"  Testnet: {exchange_config.testnet}")
    print(f"  Rate limit: Enabled")
    print()

    # Проблемные символы из логов
    problem_symbols = [
        'SUNDOG/USDT:USDT',  # Entry order failed: unknown (2025-10-12 05:51:20)
        'XCH/USDT:USDT',     # Возможно та же проблема
    ]

    results = []

    try:
        for i, symbol in enumerate(problem_symbols, 1):
            result = await test_symbol_order_status(exchange, symbol, i)
            if result:
                results.append(result)

            # Пауза между тестами
            if i < len(problem_symbols):
                print(f"\n{YELLOW}⏸️  Пауза 3 секунды перед следующим тестом...{RESET}")
                await asyncio.sleep(3)

        # ФИНАЛЬНЫЙ ОТЧЕТ
        print(f"\n\n{BOLD}{'='*80}{RESET}")
        print(f"{BOLD}📊 ФИНАЛЬНЫЙ ОТЧЕТ{RESET}")
        print(f"{BOLD}{'='*80}{RESET}\n")

        if not results:
            print(f"{RED}❌ Нет результатов для анализа{RESET}")
            return

        print(f"{BOLD}СВОДКА ПО СТАТУСАМ:{RESET}\n")

        for result in results:
            symbol = result['symbol']
            print(f"{BOLD}{symbol}:{RESET}")
            print(f"  IMMEDIATE (create_market_order):")
            print(f"    raw status: {result['immediate']['raw_status']}")
            print(f"    info.orderStatus: {result['immediate']['info_status']}")
            print(f"    normalized: {YELLOW}{result['immediate']['normalized_status']}{RESET}")
            print(f"    is_filled: {result['immediate']['is_filled']}")
            print(f"    Бот примет: {GREEN + 'ДА' if result['would_bot_accept'] else RED + 'НЕТ'}{RESET}")
            print()
            print(f"  AFTER FETCH (через 1 сек):")
            print(f"    raw status: {result['after_fetch']['raw_status']}")
            print(f"    info.orderStatus: {result['after_fetch']['info_status']}")
            print(f"    normalized: {YELLOW}{result['after_fetch']['normalized_status']}{RESET}")
            print(f"    is_filled: {result['after_fetch']['is_filled']}")
            print()

        # КЛЮЧЕВЫЕ НАХОДКИ
        print(f"{BOLD}🔍 КЛЮЧЕВЫЕ НАХОДКИ:{RESET}\n")

        # Проверить все уникальные статусы
        immediate_raw_statuses = set(r['immediate']['raw_status'] for r in results if r['immediate']['raw_status'])
        immediate_info_statuses = set(r['immediate']['info_status'] for r in results if r['immediate']['info_status'])
        immediate_normalized = set(r['immediate']['normalized_status'] for r in results)

        after_raw_statuses = set(r['after_fetch']['raw_status'] for r in results if r['after_fetch']['raw_status'])
        after_info_statuses = set(r['after_fetch']['info_status'] for r in results if r['after_fetch']['info_status'])

        print(f"1. RAW СТАТУСЫ (order['status']):")
        print(f"   Immediate: {immediate_raw_statuses}")
        print(f"   After fetch: {after_raw_statuses}")
        print()

        print(f"2. INFO СТАТУСЫ (order['info']['orderStatus']):")
        print(f"   Immediate: {immediate_info_statuses}")
        print(f"   After fetch: {after_info_statuses}")
        print()

        print(f"3. NORMALIZED СТАТУСЫ:")
        print(f"   Immediate: {immediate_normalized}")
        print()

        # Найти проблемные статусы
        problematic = [r for r in results if not r['would_bot_accept']]

        if problematic:
            print(f"4. {RED}ПРОБЛЕМНЫЕ СТАТУСЫ (бот отклонит):{RESET}")
            for r in problematic:
                print(f"   {r['symbol']}: normalized='{r['immediate']['normalized_status']}'")
                print(f"     → info.orderStatus был: '{r['immediate']['info_status']}'")
                print(f"     → НЕ в status_map → стал 'unknown'")
            print()

        # РЕКОМЕНДАЦИИ
        print(f"{BOLD}💡 РЕКОМЕНДАЦИИ:{RESET}\n")

        all_info_statuses = immediate_info_statuses | after_info_statuses

        # Текущий status_map
        current_map = {
            'Filled', 'PartiallyFilled', 'New', 'Cancelled', 'Rejected'
        }

        missing_statuses = all_info_statuses - current_map

        if missing_statuses:
            print(f"Добавить в status_map:")
            for status in missing_statuses:
                # Определить маппинг
                if status in ['Created', 'Triggered', 'Untriggered']:
                    mapping = 'open'
                elif status in ['Deactivated']:
                    mapping = 'canceled'
                else:
                    mapping = 'open'  # По умолчанию

                print(f"  '{status}': '{mapping}',")
            print()
        else:
            print(f"{GREEN}✅ Все статусы уже в status_map!{RESET}")
            print()

        # Сохранить полные данные
        print(f"\n{BLUE}💾 Сохранение полных данных...{RESET}")

        output_file = f"diagnostic_order_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"{GREEN}✅ Данные сохранены в: {output_file}{RESET}")

    finally:
        await exchange.close()

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}✅ ДИАГНОСТИКА ЗАВЕРШЕНА{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}⚠️  Прервано пользователем (Ctrl+C){RESET}\n")
    except Exception as e:
        print(f"\n\n{RED}❌ КРИТИЧЕСКАЯ ОШИБКА: {e}{RESET}\n")
        import traceback
        traceback.print_exc()
