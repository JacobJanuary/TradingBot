#!/usr/bin/env python3
"""
Диагностический патч для atomic_position_manager.py
Добавляет детальное логирование raw_order от биржи

ИСПОЛЬЗОВАНИЕ:
1. Найти в atomic_position_manager.py строку:
   raw_order = await exchange_instance.create_market_order(...)

2. ПОСЛЕ этой строки добавить:

   # ДИАГНОСТИКА: Детальное логирование raw_order
   import json
   logger.critical("🔍 DIAGNOSTIC: RAW ORDER FROM EXCHANGE:")
   logger.critical(f"   raw_order type: {type(raw_order)}")
   logger.critical(f"   raw_order is None: {raw_order is None}")
   if raw_order:
       logger.critical(f"   raw_order keys: {list(raw_order.keys()) if isinstance(raw_order, dict) else 'NOT A DICT'}")
       logger.critical(f"   raw_order.get('status'): {raw_order.get('status') if isinstance(raw_order, dict) else 'N/A'}")
       logger.critical(f"   raw_order.get('info'): {raw_order.get('info') if isinstance(raw_order, dict) else 'N/A'}")
       if isinstance(raw_order, dict) and 'info' in raw_order:
           info = raw_order['info']
           logger.critical(f"   info.get('orderStatus'): {info.get('orderStatus') if isinstance(info, dict) else 'N/A'}")
           logger.critical(f"   info.get('orderLinkId'): {info.get('orderLinkId') if isinstance(info, dict) else 'N/A'}")
       try:
           logger.critical(f"   JSON: {json.dumps(raw_order, indent=2, default=str)}")
       except Exception as e:
           logger.critical(f"   JSON serialization failed: {e}")

3. Запустить бота и дождаться ошибки
4. Проверить логи - там будет ПОЛНАЯ информация о raw_order

Это позволит увидеть:
- Какая структура возвращается
- Какой статус в ней
- Все ключи и значения
"""

import json

# Пример анализа логов:
EXAMPLE_BYBIT_MARKET_ORDER = {
    'id': '1234567890',
    'clientOrderId': None,
    'timestamp': 1728700000000,
    'datetime': '2024-10-12T02:00:00.000Z',
    'lastTradeTimestamp': None,
    'symbol': 'SUNDOG/USDT:USDT',
    'type': 'market',
    'timeInForce': 'GTC',
    'postOnly': False,
    'reduceOnly': False,
    'side': 'sell',
    'price': None,
    'stopPrice': None,
    'amount': 3870.0,
    'cost': 200.0,
    'average': 0.05167,
    'filled': 3870.0,
    'remaining': 0.0,
    'status': 'closed',  # ← Это ключевое поле!
    'fee': None,
    'trades': [],
    'fees': [],
    'info': {
        'orderId': '1234567890',
        'orderLinkId': '',
        'symbol': 'SUNDOGUSDT',
        'orderStatus': 'Filled',  # ← И это!
        'side': 'Sell',
        'orderType': 'Market',
        'price': '0',
        'qty': '3870',
        'cumExecQty': '3870',
        'cumExecValue': '200.0',
        'cumExecFee': '0.12',
        'timeInForce': 'GTC',
        'createTime': '1728700000000',
        'updateTime': '1728700000000',
        'reduceOnly': False,
        'closeOnTrigger': False,
        'leavesQty': '0',
        'leavesValue': '0',
        'avgPrice': '0.05167'
    }
}

POSSIBLE_BYBIT_STATUSES = [
    'Created',      # Ордер создан но не размещен
    'New',          # Ордер размещен на бирже
    'Rejected',     # Ордер отклонен
    'PartiallyFilled',  # Частично исполнен
    'Filled',       # Полностью исполнен
    'Cancelled',    # Отменен
    'Untriggered',  # Условный ордер не сработал
    'Triggered',    # Условный ордер сработал
    'Deactivated',  # Деактивирован
]

def analyze_status_mapping():
    """Анализирует какие статусы обрабатываются"""
    print("="*80)
    print("АНАЛИЗ: Status Mapping в exchange_response_adapter.py")
    print("="*80)
    print()

    status_map = {
        'Filled': 'closed',
        'PartiallyFilled': 'open',
        'New': 'open',
        'Cancelled': 'canceled',
        'Rejected': 'canceled',
    }

    print("✅ Обрабатываемые статусы:")
    for bybit_status, normalized in status_map.items():
        print(f"   {bybit_status:20} → {normalized}")
    print()

    print("❌ НЕ обрабатываемые статусы (станут 'unknown'):")
    for status in POSSIBLE_BYBIT_STATUSES:
        if status not in status_map:
            print(f"   {status:20} → unknown ⚠️")
    print()

    print("🔍 ЧТО МОЖЕТ ПОЙТИ НЕ ТАК:")
    print()
    print("1. Статус 'Created':")
    print("   - Ордер создан но еще не размещен на бирже")
    print("   - Будет 'unknown' → ошибка 'Entry order failed: unknown'")
    print()
    print("2. Статус 'Untriggered':")
    print("   - Для условных ордеров (stop-loss, take-profit)")
    print("   - Не должен быть у market orders")
    print()
    print("3. Статус 'Triggered':")
    print("   - Условный ордер сработал и превратился в market order")
    print("   - Может быть промежуточным статусом")
    print()
    print("4. Статус None:")
    print("   - Если биржа не вернула статус")
    print("   - Или ccxt не смог его извлечь")
    print()

    print("="*80)
    print("РЕКОМЕНДАЦИЯ:")
    print("="*80)
    print()
    print("1. Добавить детальное логирование в atomic_position_manager.py")
    print("2. Запустить бота и дождаться ошибки")
    print("3. Проанализировать логи - посмотреть raw_order['status'] и raw_order['info']['orderStatus']")
    print("4. Добавить недостающие статусы в status_map")
    print()

if __name__ == "__main__":
    analyze_status_mapping()

    print()
    print("="*80)
    print("ПРИМЕР УСПЕШНОГО MARKET ORDER ОТ BYBIT:")
    print("="*80)
    print()
    print(json.dumps(EXAMPLE_BYBIT_MARKET_ORDER, indent=2))
    print()
