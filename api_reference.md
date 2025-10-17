# API Reference для Trading Bot

## Используемые библиотеки
- **CCXT**: v4.1.22 - Унифицированная библиотека для работы с биржами
- **python-binance**: v1.0.19 - Native Binance connector
- **pybit**: v5.6.2 - Native Bybit connector

## CCXT API методы

### exchange.create_order()
**Описание**: Создание нового ордера на бирже

**Параметры**:
```python
order = await exchange.create_order(
    symbol,      # str: 'BTC/USDT' или 'BTC/USDT:USDT' для futures
    type,        # str: 'market', 'limit', 'stop_market', 'stop_limit'
    side,        # str: 'buy', 'sell'
    amount,      # float: количество
    price,       # float: цена (для limit orders)
    params       # dict: дополнительные параметры
)
```

**Важные params для Binance**:
- `reduceOnly`: bool - только уменьшение позиции (важно для SL!)
- `stopPrice`: float - цена триггера для стоп-ордеров
- `workingType`: str - 'MARK_PRICE' или 'CONTRACT_PRICE'
- `timeInForce`: str - 'GTC', 'IOC', 'FOK'
- `positionSide`: str - 'LONG', 'SHORT', 'BOTH'

**Важные params для Bybit**:
- `reduceOnly`: bool - аналогично Binance
- `triggerPrice`: float - цена активации для стоп-ордеров
- `triggerBy`: str - 'MarkPrice', 'LastPrice', 'IndexPrice'
- `tpslMode`: str - 'Full' или 'Partial'
- `stopLoss`: float - цена стоп-лосса
- `takeProfit`: float - цена тейк-профита

**Возвращает**:
```python
{
    'id': '12345678',           # ID ордера
    'clientOrderId': 'x-1234',  # Client Order ID
    'symbol': 'BTC/USDT',
    'type': 'limit',
    'side': 'buy',
    'price': 30000.0,
    'amount': 0.001,
    'status': 'open',           # 'open', 'closed', 'canceled'
    'filled': 0.0,
    'remaining': 0.001,
    'timestamp': 1234567890,
    'datetime': '2024-01-01T00:00:00Z'
}
```

**Ошибки**:
- `-1013` (Binance): Invalid quantity
- `-2010` (Binance): Insufficient balance
- `-2021` (Binance): Order would immediately trigger
- `10001` (Bybit): Parameter error
- `110007` (Bybit): Insufficient balance

### exchange.cancel_order()
**Описание**: Отмена существующего ордера

**Параметры**:
```python
result = await exchange.cancel_order(
    id,         # str: ID ордера (или None если используется clientOrderId)
    symbol,     # str: символ торговой пары
    params      # dict: дополнительные параметры
)
```

**Params**:
- `clientOrderId`: str - использовать Client Order ID вместо ID
- `origClientOrderId`: str - для Binance

**Возвращает**:
```python
{
    'id': '12345678',
    'status': 'canceled',
    'info': {}  # Raw response from exchange
}
```

### exchange.fetch_positions()
**Описание**: Получение открытых позиций

**Параметры**:
```python
positions = await exchange.fetch_positions(
    symbols,    # list или None: список символов или все
    params      # dict: дополнительные параметры
)
```

**Возвращает**:
```python
[{
    'symbol': 'BTC/USDT:USDT',
    'side': 'long',           # 'long' или 'short'
    'contracts': 0.001,       # размер позиции в контрактах
    'contractSize': 1.0,
    'unrealizedPnl': 50.0,
    'percentage': 5.0,        # процент PnL
    'entryPrice': 30000.0,
    'markPrice': 31500.0,
    'liquidationPrice': 25000.0,
    'marginMode': 'isolated', # или 'cross'
    'leverage': 10,
    'timestamp': 1234567890
}]
```

### exchange.fetch_balance()
**Описание**: Получение баланса аккаунта

**Возвращает**:
```python
{
    'USDT': {
        'free': 1000.0,    # доступный баланс
        'used': 100.0,     # используемый в ордерах
        'total': 1100.0    # общий баланс
    },
    'info': {}  # Raw response
}
```

**Для Bybit Unified Account**:
```python
# Баланс может быть в info для unified account
balance['info']['result']['list'][0]['totalAvailableBalance']
```

### exchange.fetch_open_orders()
**Описание**: Получение открытых ордеров

**Параметры**:
```python
orders = await exchange.fetch_open_orders(
    symbol,     # str: символ или None для всех
    since,      # int: timestamp с какого времени
    limit,      # int: максимум ордеров
    params      # dict: дополнительные параметры
)
```

### exchange.fetch_order()
**Описание**: Получение информации о конкретном ордере

**Параметры**:
```python
order = await exchange.fetch_order(
    id,         # str: ID ордера
    symbol,     # str: символ
    params      # dict: дополнительные параметры
)
```

## Rate Limits

### Binance
- REST API: 1200 requests per minute (weight-based)
- Order placement: 50 orders per 10 seconds
- Order cancellation: 100 orders per 10 seconds

### Bybit
- REST API: 120 requests per minute для большинства endpoints
- Order placement: 100 orders per minute
- WebSocket connections: 20 per IP

## Критические особенности

### 1. Stop Loss на Binance
- **ВСЕГДА** использовать `reduceOnly: true` для SL ордеров
- При обновлении SL: сначала cancel, потом create новый
- Проверять что SL не слишком близко к текущей цене (минимум 0.2%)
- Использовать `workingType: 'MARK_PRICE'` для защиты от манипуляций

### 2. Stop Loss на Bybit
- Использовать `triggerPrice` вместо `stopPrice`
- Параметр `triggerBy: 'MarkPrice'` предпочтительнее
- Для V5 API обязательно указывать `category: 'linear'`

### 3. Символы
- Spot: 'BTC/USDT'
- Futures Binance: 'BTC/USDT:USDT'
- Futures Bybit: 'BTCUSDT' или 'BTC/USDT:USDT'
- **ВАЖНО**: Нормализация символов между БД и биржей

### 4. Обработка ошибок
- Всегда проверять `retCode` для Bybit (0 = успех)
- Для Binance проверять поле `status` в ответе
- Реализовать retry логику с экспоненциальной задержкой
- Логировать все ошибки API для анализа

### 5. WebSocket reconnection
- Автоматический реконнект после разрыва
- Восстановление подписок после реконнекта
- Heartbeat/pong для поддержания соединения
- Буферизация событий при разрыве