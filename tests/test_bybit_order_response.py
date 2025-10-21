#!/usr/bin/env python3
"""
Тестовый скрипт для исследования структуры ответа Bybit API

Цель: Понять почему extract_execution_price возвращает 0 для Bybit market orders
"""
import json

# Симуляция ответа Bybit API v5 для create_market_order
# Основано на документации: https://bybit-exchange.github.io/docs/v5/order/create-order

# THEORY 1: Bybit API v5 возвращает минимальный ответ при создании ордера
bybit_create_order_response_v5 = {
    'id': '1234567890',
    'clientOrderId': 'my-order-123',
    'timestamp': 1729000000000,
    'datetime': '2024-10-15T12:00:00.000Z',
    'lastTradeTimestamp': None,
    'symbol': 'BLAST/USDT:USDT',
    'type': 'market',
    'timeInForce': 'GTC',
    'postOnly': False,
    'reduceOnly': False,
    'side': 'sell',
    'price': None,  # Market order не имеет price
    'stopPrice': None,
    'triggerPrice': None,
    'amount': 10.0,
    'cost': None,  # НЕ ИЗВЕСТНО сразу после создания!
    'average': None,  # НЕ ИЗВЕСТНО сразу после создания!
    'filled': None,  # НЕ ИЗВЕСТНО сразу после создания!
    'remaining': None,
    'status': 'open',  # или None для v5
    'fee': None,
    'trades': None,
    'fees': [],
    'info': {
        'retCode': 0,
        'retMsg': 'OK',
        'result': {
            'orderId': '1234567890',
            'orderLinkId': 'my-order-123',
            # КРИТИЧНО: avgPrice отсутствует в ответе create_order!
            # Он появляется только при get_order или в websocket updates!
        },
        'retExtInfo': {},
        'time': 1729000000000
    }
}

# THEORY 2: Реальная цена исполнения доступна только через get_order
bybit_get_order_response_v5 = {
    'id': '1234567890',
    'clientOrderId': 'my-order-123',
    'timestamp': 1729000000000,
    'datetime': '2024-10-15T12:00:00.000Z',
    'lastTradeTimestamp': 1729000001000,
    'symbol': 'BLAST/USDT:USDT',
    'type': 'market',
    'side': 'sell',
    'price': None,
    'amount': 10.0,
    'cost': 0.01696,  # ТЕПЕРЬ ИЗВЕСТНО!
    'average': 0.001696,  # ТЕПЕРЬ ИЗВЕСТНО!
    'filled': 10.0,  # ТЕПЕРЬ ИЗВЕСТНО!
    'remaining': 0.0,
    'status': 'closed',  # Filled
    'fee': {
        'cost': 0.00001696,
        'currency': 'USDT'
    },
    'info': {
        'retCode': 0,
        'retMsg': 'OK',
        'result': {
            'orderId': '1234567890',
            'orderLinkId': 'my-order-123',
            'symbol': 'BLASTUSDT',
            'price': '0',
            'qty': '10',
            'side': 'Sell',
            'orderType': 'Market',
            'orderStatus': 'Filled',
            'cumExecQty': '10',
            'cumExecValue': '0.01696',
            'avgPrice': '0.001696',  # ВОТ ОНА ЦЕНА!
            'timeInForce': 'GTC',
            'orderCategory': 'linear',
            'createdTime': '1729000000000',
            'updatedTime': '1729000001000'
        }
    }
}


def test_extract_execution_price_from_create():
    """
    Тест: что вернет extract_execution_price для ответа create_order
    """
    print("=" * 100)
    print("TEST 1: extract_execution_price from create_market_order response")
    print("=" * 100)

    data = bybit_create_order_response_v5
    info = data.get('info', {})

    print(f"\nChecking fields:")
    print(f"  data['average']: {data.get('average')}")
    print(f"  data['price']: {data.get('price')}")
    print(f"  info.get('avgPrice'): {info.get('result', {}).get('avgPrice')}")
    print(f"  info.get('lastExecPrice'): {info.get('result', {}).get('lastExecPrice')}")
    print(f"  data.get('lastTradePrice'): {data.get('lastTradePrice')}")

    # Симуляция логики extract_execution_price
    if data.get('average') and data.get('average') > 0:
        result = data.get('average')
    elif data.get('price') and data.get('price') > 0:
        result = data.get('price')
    else:
        # Fallback
        possible_prices = [
            info.get('result', {}).get('avgPrice'),
            info.get('result', {}).get('lastExecPrice'),
            info.get('result', {}).get('price'),
            data.get('lastTradePrice')
        ]
        result = None
        for p in possible_prices:
            if p:
                try:
                    p_float = float(p)
                    if p_float > 0:
                        result = p_float
                        break
                except (ValueError, TypeError):
                    continue

        if result is None:
            result = 0.0

    print(f"\n🎯 RESULT: {result}")
    print(f"❌ ПРОБЛЕМА: Цена исполнения = {result} (НЕТ ДАННЫХ В create_order!)")


def test_extract_execution_price_from_get():
    """
    Тест: что вернет extract_execution_price для ответа get_order
    """
    print("\n" + "=" * 100)
    print("TEST 2: extract_execution_price from get_order response")
    print("=" * 100)

    data = bybit_get_order_response_v5
    info = data.get('info', {})

    print(f"\nChecking fields:")
    print(f"  data['average']: {data.get('average')}")
    print(f"  data['price']: {data.get('price')}")
    print(f"  info['result']['avgPrice']: {info.get('result', {}).get('avgPrice')}")

    # Симуляция логики extract_execution_price
    if data.get('average') and data.get('average') > 0:
        result = data.get('average')
    else:
        result = 0.0

    print(f"\n🎯 RESULT: {result}")
    print(f"✅ УСПЕХ: Цена исполнения = {result}")


def analyze_problem():
    """
    Анализ корневой причины проблемы
    """
    print("\n" + "=" * 100)
    print("АНАЛИЗ ПРОБЛЕМЫ")
    print("=" * 100)

    print("""
🔴 КОРНЕВАЯ ПРИЧИНА:

1. AtomicPositionManager вызывает exchange.create_market_order()
2. Bybit API v5 возвращает МИНИМАЛЬНЫЙ ответ:
   - orderId: есть
   - avgPrice: ОТСУТСТВУЕТ! (будет позже)
   - average: None
   - filled: None

3. ExchangeResponseAdapter.normalize_order():
   - Пытается извлечь average из data['average'] → None
   - Пытается извлечь из info['avgPrice'] → ОТСУТСТВУЕТ
   - Результат: average = None, price = None

4. ExchangeResponseAdapter.extract_execution_price():
   - Проверяет order.average → None
   - Проверяет order.price → None
   - Fallback в raw_data → НЕТ ДАННЫХ
   - Возвращает 0.0 ❌

5. atomic_position_manager.py:229
   - exec_price = 0.0

6. position_manager.py:1029
   - entry_price=position.entry_price → 0.0

7. Результат: TS создается с entry_price=0 ❌

📊 ПОЧЕМУ ДЛЯ BINANCE РАБОТАЕТ:

Binance API возвращает avgPrice сразу в ответе create_order для FILLED orders!

🎯 РЕШЕНИЕ:

ВАРИАНТ 1: Fetch order after creation (для Bybit)
   После create_market_order делать get_order() чтобы получить avgPrice

ВАРИАНТ 2: Extract from position
   Использовать exchange.fetch_position() для получения real entry price

ВАРИАНТ 3: Use WebSocket update
   Дождаться WebSocket update с execution details

ВАРИАНТ 4 (РЕКОМЕНДУЕМЫЙ): Immediate fetch for Bybit
   if exchange == 'bybit' and exec_price == 0:
       order = await exchange.fetch_order(order_id, symbol)
       exec_price = extract_execution_price(order)

⚠️ ВРЕМЕННОЕ РЕШЕНИЕ (используется сейчас):
   Ручное исправление entry_price в БД после создания позиции

✅ ПРАВИЛЬНОЕ РЕШЕНИЕ:
   Добавить fetch_order для Bybit сразу после create_market_order
    """)


def test_theories():
    """
    Проверка теорий о получении цены
    """
    print("\n" + "=" * 100)
    print("ПРОВЕРКА ТЕОРИЙ")
    print("=" * 100)

    theories = [
        {
            'name': 'THEORY 1: Wait for WebSocket',
            'pros': ['Не нужен дополнительный API call', 'Real-time data'],
            'cons': ['Задержка (может быть секунды)', 'Нужна синхронизация', 'Сложная реализация'],
            'verdict': '❌ Не подходит - TS создается НЕМЕДЛЕННО'
        },
        {
            'name': 'THEORY 2: Fetch order after creation',
            'pros': ['Гарантированно точная цена', 'Простая реализация', 'Надежно'],
            'cons': ['Дополнительный API call', '+100-200ms задержка'],
            'verdict': '✅ РЕКОМЕНДУЕТСЯ - лучший баланс'
        },
        {
            'name': 'THEORY 3: Fetch position',
            'pros': ['Получаем entry price из позиции'],
            'cons': ['Может быть задержка', 'Позиция может еще не появиться', 'Ненадежно'],
            'verdict': '⚠️ Ненадежно - race condition'
        },
        {
            'name': 'THEORY 4: Use signal entry_price',
            'pros': ['Уже есть в данных', 'Нет задержки'],
            'cons': ['НЕ РЕАЛЬНАЯ цена исполнения!', 'Slippage не учитывается', 'Может отличаться на 0.1-1%'],
            'verdict': '❌ Неточно - нужна РЕАЛЬНАЯ цена'
        }
    ]

    for i, theory in enumerate(theories, 1):
        print(f"\n{i}. {theory['name']}")
        print(f"   Плюсы: {', '.join(theory['pros'])}")
        print(f"   Минусы: {', '.join(theory['cons'])}")
        print(f"   {theory['verdict']}")


if __name__ == '__main__':
    test_extract_execution_price_from_create()
    test_extract_execution_price_from_get()
    analyze_problem()
    test_theories()

    print("\n" + "=" * 100)
    print("🎯 ИТОГОВАЯ РЕКОМЕНДАЦИЯ")
    print("=" * 100)
    print("""
МЕСТО ИСПРАВЛЕНИЯ: core/atomic_position_manager.py:229

ТЕКУЩИЙ КОД:
    exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)

ИСПРАВЛЕННЫЙ КОД:
    exec_price = ExchangeResponseAdapter.extract_execution_price(entry_order)

    # FIX: Bybit API v5 не возвращает avgPrice в create_order
    # Нужно fetch order для получения реальной цены исполнения
    if exchange == 'bybit' and (not exec_price or exec_price == 0):
        logger.info(f"📊 Fetching order details for {symbol} to get execution price")
        try:
            fetched_order = await exchange_instance.fetch_order(entry_order.id, symbol)
            fetched_normalized = ExchangeResponseAdapter.normalize_order(fetched_order, exchange)
            exec_price = ExchangeResponseAdapter.extract_execution_price(fetched_normalized)
            logger.info(f"✅ Got execution price from fetch_order: {exec_price}")
        except Exception as e:
            logger.error(f"❌ Failed to fetch order for execution price: {e}")
            # Fallback: use position entry price from signal
            exec_price = entry_price

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- Bybit позиции будут иметь корректный entry_price
- TS будет создаваться с правильными данными
- Больше не будет corrupted data с entry_price=0
    """)
