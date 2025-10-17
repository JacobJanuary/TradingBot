# Best Practices из референсных реализаций

## Источники
- Freqtrade - популярный open-source торговый бот
- CCXT официальная документация и примеры
- Binance/Bybit официальные коннекторы

## Обработка WebSocket disconnections

### Как делает Freqtrade
- Автоматический реконнект с экспоненциальной задержкой (5s, 10s, 20s, 40s...)
- Максимум попыток реконнекта: 10
- При реконнекте восстанавливаются все подписки
- Heartbeat каждые 30 секунд для поддержания соединения
- При отсутствии pong в течение 60 секунд - принудительный реконнект

### Как делают другие
- Binance connector: ping/pong каждые 30 секунд
- Bybit connector: heartbeat каждые 20 секунд
- Буферизация сообщений во время разрыва соединения

### Рекомендации
1. Реализовать автоматический реконнект
2. Использовать heartbeat/keepalive
3. Логировать все разрывы соединения
4. Восстанавливать состояние после реконнекта
5. Иметь fallback на REST API при длительных проблемах

## Trailing Stop реализация

### Формулы и алгоритмы (Freqtrade)
```python
# Для LONG позиции
if current_price > highest_price:
    highest_price = current_price
    new_stop_loss = highest_price * (1 - trailing_percent)

# Для SHORT позиции
if current_price < lowest_price:
    lowest_price = current_price
    new_stop_loss = lowest_price * (1 + trailing_percent)
```

### Edge cases
1. **Минимальное изменение**: Не обновлять SL если изменение < 0.1%
2. **Минимальный интервал**: Не чаще чем раз в 60 секунд
3. **Проверка расстояния**: SL должен быть минимум 0.2% от текущей цены
4. **Защита от всплесков**: Использовать mark price, а не last price

### Реализация Freqtrade
- **НЕ** использует native trailing stop биржи
- Вместо этого: cancel старого SL + create нового
- Проверка и обновление каждую минуту
- Транзакционность: если cancel успешен, но create провалился - экстренное закрытие

## Синхронизация состояния

### Паттерны
1. **Source of Truth**: Биржа - главный источник истины
2. **Reconciliation**: Периодическая синхронизация БД с биржей
3. **Event-driven updates**: Обновление через WebSocket события
4. **Polling fallback**: REST API polling при проблемах с WebSocket

### Freqtrade подход
```python
# Каждые 5 минут
positions_exchange = exchange.fetch_positions()
positions_db = db.get_positions()

# Reconciliation
for pos in positions_exchange:
    if pos not in positions_db:
        # Добавить в БД
    else:
        # Обновить в БД

for pos in positions_db:
    if pos not in positions_exchange:
        # Пометить как закрытую в БД
```

## Обработка ошибок API

### Retry стратегия (Freqtrade)
```python
MAX_RETRIES = 3
RETRY_DELAYS = [1, 3, 10]  # секунды

for attempt in range(MAX_RETRIES):
    try:
        result = await exchange.create_order(...)
        break
    except NetworkError:
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_DELAYS[attempt])
        else:
            raise
    except ExchangeNotAvailable:
        # Биржа на обслуживании
        await asyncio.sleep(60)
    except InsufficientFunds:
        # Не retry, сразу логировать
        raise
```

### Классификация ошибок
1. **Retriable**: Network errors, rate limits, temporary failures
2. **Non-retriable**: Insufficient funds, invalid parameters, permissions
3. **Critical**: Authentication failures, exchange maintenance

## Защита от незащищенных позиций

### Freqtrade
- Проверка каждые 60 секунд
- Если позиция без SL более 60 секунд - создать SL немедленно
- Логирование всех инцидентов как WARNING

### Рекомендации
1. Атомарные операции: entry + SL в одной транзакции
2. Если невозможно - максимум 60 секунд между entry и SL
3. Мониторинг и алерты при обнаружении
4. Fallback SL на уровне -2% если основной не создался

## Zombie Order Cleanup

### Определение зомби
- Ордер существует на бирже, но нет соответствующей позиции
- Ордер старше 24 часов и не исполнен
- Stop loss ордер без родительской позиции

### Freqtrade подход
```python
# Каждые 30 минут
open_orders = exchange.fetch_open_orders()
positions = exchange.fetch_positions()

for order in open_orders:
    # Проверка 1: Старые неисполненные
    if order.age > 24_hours and order.filled == 0:
        cancel_order(order)

    # Проверка 2: SL без позиции
    if order.type == 'stop_loss':
        if not has_position(order.symbol):
            cancel_order(order)
```

## Position Age Management

### Стратегии закрытия старых позиций
1. **Breakeven после X часов**: Переставить лимитку на entry price
2. **Gradual liquidation**: Постепенно ужесточать цену выхода
3. **Force close**: Принудительное закрытие market ордером

### Freqtrade реализация
```python
if position.age > 3_hours:
    if position.profit > 0:
        # Защитить профит
        set_sl_at_breakeven()
    else:
        # Начать градуальную ликвидацию
        every_hour:
            new_price = current_price * (1 - loss_step)
            update_limit_order(new_price)
```

## Rate Limiting

### Best Practices
1. Использовать weight-based limiting для Binance
2. Реализовать bucket token algorithm
3. Приоритезация критичных запросов (SL создание)
4. Батчинг запросов где возможно

### Реализация
```python
class RateLimiter:
    def __init__(self, max_requests, time_window):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()

    async def acquire(self, weight=1):
        now = time.time()
        # Удалить старые запросы
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()

        # Проверить лимит
        if len(self.requests) >= self.max_requests:
            sleep_time = self.requests[0] + self.time_window - now
            await asyncio.sleep(sleep_time)

        self.requests.append(now)
```

## Логирование и мониторинг

### Что логировать (Freqtrade)
- ВСЕ операции с позициями (открытие, SL, TP, закрытие)
- ВСЕ ошибки API с полным контекстом
- Изменения состояния (позиции, баланс)
- WebSocket события (connect, disconnect, reconnect)
- Performance метрики (latency, успешность)

### Формат логов
```
2024-01-01 12:00:00,123 - INFO - position.opened - BTCUSDT LONG 0.001 @ 30000 [signal_id: 123]
2024-01-01 12:00:01,456 - INFO - sl.created - BTCUSDT SL @ 29400 [order_id: 456]
2024-01-01 12:00:02,789 - WARNING - sl.creation.failed - BTCUSDT retry 1/3 [error: -2021]
```

## Тестирование

### Freqtrade подход
1. **Dry-run режим**: Симуляция без реальных ордеров
2. **Paper trading**: Testnet биржи
3. **Backtesting**: Исторические данные
4. **Unit tests**: Для каждого модуля
5. **Integration tests**: Полный флоу