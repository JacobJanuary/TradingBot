# 🔍 РАССЛЕДОВАНИЕ: Просроченные позиции - проблема с ценой

**Дата:** 2025-10-12
**Проблема:** Для просроченной позиции не считывается реальная цена на бирже при принятии решения
**Статус:** ПОДТВЕРЖДЕНО - КРИТИЧЕСКАЯ ОШИБКА

---

## 📊 ОБНАРУЖЕННАЯ ПРОБЛЕМА

### Текущая логика работы

**Файл:** `core/position_manager.py`, метод `check_position_age()` (строки 1389-1464)

**Шаги обработки просроченной позиции:**

```python
# Строка 1407: Проверка возраста позиции
if position.age_hours >= max_age_hours:

    # Строки 1413-1418: Расчёт breakeven с использованием СТАРОЙ цены
    if position.side == 'long':
        breakeven_price = position.entry_price * (1 + commission_percent / 100)
        is_profitable = position.current_price >= breakeven_price  # ⚠️ ПРОБЛЕМА ТУТ!
    else:  # short
        breakeven_price = position.entry_price * (1 - commission_percent / 100)
        is_profitable = position.current_price <= breakeven_price  # ⚠️ ПРОБЛЕМА ТУТ!

    # Строки 1443-1458: Принятие решения на основе УСТАРЕВШЕЙ цены
    if is_profitable:
        # Закрыть по рынку (решение принято на основе старой цены!)
        await self.close_position(symbol, f'max_age_market_{max_age_hours}h')
    else:
        # Закрыть в убыток (решение принято на основе старой цены!)
        await self.close_position(symbol, f'max_age_expired_{max_age_hours}h')
```

### 🔴 КРИТИЧЕСКАЯ ОШИБКА

**`position.current_price` НЕ обновляется перед проверкой!**

Эта цена берётся из:
1. **Последнего WebSocket обновления** - может быть устаревшей на несколько минут
2. **Значения из БД при загрузке** - может быть устаревшей на часы
3. **НЕ ЗАПРАШИВАЕТСЯ С БИРЖИ** перед принятием критического решения о закрытии

---

## 🎯 ПРАКТИЧЕСКИЙ ПРИМЕР ПРОБЛЕМЫ

### Сценарий: Просроченная LONG позиция на BTC/USDT

**Параметры:**
- Биржа: Binance Futures Testnet
- Символ: BTC/USDT
- Позиция: LONG
- Размер: 0.001 BTC
- Цена входа: $50,000
- Комиссия: 0.1%
- Max age: 24 часа
- Текущее время: 24 часа 5 минут после открытия

**Breakeven цена:**
```
breakeven = $50,000 * (1 + 0.1/100) = $50,050
```

### ❌ ЧТО ПРОИСХОДИТ СЕЙЧАС (ОШИБКА)

**10:00:00** - Позиция открылась по $50,000
**10:00:05** - WebSocket обновление: current_price = $50,100
**10:15:00** - Последнее WebSocket обновление: current_price = $49,800

**🕐 ПОТОМ ДОЛГОЕ ВРЕМЯ БЕЗ ОБНОВЛЕНИЙ** (WebSocket может терять соединение, биржа может не слать обновления)

**10:00:00 (следующий день)** - Цена на бирже реально: **$51,200** (позиция в плюсе!)

**10:05:00** - `check_position_age()` запускается:

```python
# position.current_price = $49,800  ⚠️ УСТАРЕВШАЯ ЦЕНА (15+ часов назад)!
# Реальная цена на бирже: $51,200

breakeven_price = $50,050
is_profitable = $49,800 >= $50,050  # ❌ FALSE (но должно быть TRUE!)

# Логирование
logger.warning(
    f"⚠️ Expired position BTC/USDT at -0.5% loss. "  # ❌ НЕВЕРНО! Реально +2.4% profit
    f"Closing anyway due to age (24.08h > 24h)"
)

# ❌ Закрывает ПРИБЫЛЬНУЮ позицию как убыточную!
await self.close_position(symbol, 'max_age_expired_24h')
```

**Результат:**
- ❌ Позиция закрыта по рыночной цене ~$51,200
- ❌ Логи показывают "убыток", хотя реально прибыль
- ❌ Решение принято на основе цены 15-часовой давности
- ❌ Пользователь не понимает почему прибыльная позиция закрылась как убыточная

---

## 🔍 ОТКУДА ОБНОВЛЯЕТСЯ current_price

### 1. При загрузке позиций из БД

**Файл:** `core/position_manager.py:315`
```python
current_price=pos['current_price'] or pos['entry_price']
```
✅ **Выполняется:** При старте бота
❌ **НЕ выполняется:** Перед проверкой age

### 2. Через WebSocket обновления

**Файл:** `core/position_manager.py` - обработчики WebSocket
```python
def _handle_position_update(self, data):
    position.current_price = data.get('markPrice') or data.get('lastPrice')
```
✅ **Выполняется:** Когда биржа присылает обновление
❌ **НЕ гарантировано:**
- WebSocket может отключиться
- Биржа может не слать обновления если цена не меняется
- Задержка может быть часы для неликвидных инструментов

### 3. ❌ НЕ запрашивается перед check_position_age

**НЕТ** вызова `fetch_ticker()` или аналога перед:
```python
is_profitable = position.current_price >= breakeven_price
```

---

## 🚨 ПОСЛЕДСТВИЯ ОШИБКИ

### Для трейдинга:

1. **Неправильные решения о закрытии**
   - Прибыльные позиции могут закрываться как убыточные
   - Убыточные позиции могут держаться как прибыльные

2. **Неверная статистика**
   - Win rate рассчитывается неправильно
   - PnL расчёты неточные
   - Логи вводят в заблуждение

3. **Потеря денег**
   - Упущенная прибыль при преждевременном закрытии
   - Увеличенные убытки при позднем закрытии

### Для мониторинга:

4. **Недостоверные логи**
   ```
   ⚠️ Expired position BTC/USDT at -0.5% loss
   ```
   Может быть реально +2% прибыль!

5. **Невозможность отладки**
   - Нет информации о реальной цене на момент решения
   - Нет таймстампа последнего обновления цены

---

## 📋 СРАВНЕНИЕ: КАК ДОЛЖНО БЫТЬ

### ✅ ПРАВИЛЬНАЯ ЛОГИКА

```python
async def check_position_age(self):
    """Check and close positions that exceed max age with smart logic"""
    from datetime import datetime, timezone
    from decimal import Decimal

    max_age_hours = self.config.max_position_age_hours
    commission_percent = Decimal(str(self.config.commission_percent))

    for symbol, position in list(self.positions.items()):
        if position.opened_at:
            current_time = datetime.now(timezone.utc)
            position_age = current_time - position.opened_at
            position.age_hours = position_age.total_seconds() / 3600

            if position.age_hours >= max_age_hours:
                logger.warning(
                    f"⏰ Position {symbol} exceeded max age: {position.age_hours:.1f}h"
                )

                # ✅ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Получить АКТУАЛЬНУЮ цену с биржи
                exchange = self.exchanges.get(position.exchange)
                if not exchange:
                    logger.error(f"Exchange {position.exchange} not available")
                    continue

                try:
                    # ✅ FETCH REAL-TIME PRICE FROM EXCHANGE
                    ticker = await exchange.exchange.fetch_ticker(symbol)
                    real_time_price = ticker.get('last') or ticker.get('markPrice')

                    # Update position with fresh price
                    old_price = position.current_price
                    position.current_price = real_time_price

                    logger.info(
                        f"📊 Price check for {symbol}:"
                        f"\n  Old cached price: ${old_price:.2f}"
                        f"\n  Real-time price: ${real_time_price:.2f}"
                        f"\n  Difference: {((real_time_price - old_price) / old_price * 100):.2f}%"
                    )

                except Exception as e:
                    logger.error(f"Failed to fetch current price for {symbol}: {e}")
                    logger.warning(f"Using cached price ${position.current_price:.2f} (may be outdated)")

                # Теперь расчёт с АКТУАЛЬНОЙ ценой
                if position.side == 'long':
                    breakeven_price = position.entry_price * (1 + commission_percent / 100)
                    is_profitable = position.current_price >= breakeven_price
                else:
                    breakeven_price = position.entry_price * (1 - commission_percent / 100)
                    is_profitable = position.current_price <= breakeven_price

                logger.info(
                    f"💰 Position analysis for {symbol}:"
                    f"\n  Entry: ${position.entry_price:.2f}"
                    f"\n  Current: ${position.current_price:.2f}"
                    f"\n  Breakeven: ${breakeven_price:.2f}"
                    f"\n  Status: {'✅ PROFITABLE' if is_profitable else '❌ LOSS'}"
                )

                # Принятие решения на основе АКТУАЛЬНЫХ данных
                if is_profitable:
                    logger.info(f"✅ Closing profitable expired position {symbol}")
                    await self.close_position(symbol, f'max_age_market_{max_age_hours}h')
                else:
                    logger.warning(f"⚠️ Closing losing expired position {symbol}")
                    await self.close_position(symbol, f'max_age_expired_{max_age_hours}h')
```

---

## 🔧 ПЛАН ИСПРАВЛЕНИЯ

### Приоритет: 🔴 КРИТИЧЕСКИЙ

### Шаги:

1. **Добавить fetch_ticker() перед проверкой is_profitable**
   - Локация: `core/position_manager.py:1407-1420`
   - Изменения: ~15 строк кода
   - Время: 5 минут

2. **Добавить детальное логирование цен**
   - Показывать старую vs новую цену
   - Показывать источник цены (cache vs real-time)
   - Таймстамп последнего обновления

3. **Обработать ошибки получения цены**
   - Fallback на cached price с предупреждением
   - Retry logic если fetch_ticker() падает
   - Логировать когда используется устаревшая цена

4. **Обновить расчёт PnL**
   - Использовать актуальную цену для unrealized_pnl_percent
   - Синхронизировать с БД

---

## 📊 МЕТРИКИ ДЛЯ ТЕСТИРОВАНИЯ

После исправления проверить:

1. ✅ Цена запрашивается с биржи перед каждой проверкой age
2. ✅ Логи показывают старую и новую цену
3. ✅ Решение принимается на основе real-time цены
4. ✅ Обрабатываются ошибки fetch_ticker()
5. ✅ PnL рассчитывается корректно

---

## 🎯 ДОПОЛНИТЕЛЬНЫЕ НАХОДКИ

### Проблема #2: Метод _place_limit_close_order не используется

**Файл:** `core/position_manager.py:1302-1387`

**Найдено:**
- Метод `_place_limit_close_order` определён
- НО никогда не вызывается в коде!
- Все просроченные позиции закрываются по рынку через `close_position`

**Это означает:**
- Возможно планировалась стратегия с лимитными ордерами
- Но она не реализована
- Метод - мёртвый код

**Вопросы:**
- Нужно ли использовать лимитные ордера для просроченных позиций?
- Если да, когда? (только для прибыльных? для всех?)
- Какую цену использовать для limit order?

---

## ✅ ГОТОВО К ИСПРАВЛЕНИЮ

Жду вашего решения:
- ✅ Утвердить план исправления
- ⏸️ Запросить дополнительную информацию
- 🔄 Изменить приоритеты

**Рекомендация:** Исправить НЕМЕДЛЕННО - это критическая ошибка логики которая влияет на все решения по просроченным позициям.
