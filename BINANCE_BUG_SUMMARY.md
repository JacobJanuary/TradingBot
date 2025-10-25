# 🔴 КРИТИЧЕСКИЙ БАГ: Binance Mark Price Updates

**Дата**: 2025-10-25
**Статус**: БАГ НАЙДЕН, РЕШЕНИЕ ГОТОВО
**Приоритет**: КРИТИЧЕСКИЙ

---

## 📊 Проблема

**7 позиций на Binance** перестали получать обновления mark_price после переподключения WebSocket в 23:21:07.

**Затронуто**: $35.60 USD в 6 позициях без защиты Trailing Stop

---

## 🔍 Что произошло

### Timeline:
```
22:51-23:19  ✅ Все 7 позиций подписаны, обновления идут нормально
23:21:07     🔴 Mark Price WebSocket переподключается
23:21:13     ✅ WebSocket подключён, НО...
23:21:13+    ❌ Подписки НЕ восстановлены!
Сейчас       ❌ 6 из 7 позиций не получают обновления
```

### Затронутые позиции:
```
❌ ZBTUSDT   - заморожено с 23:21:07 (~88 сек назад)
❌ ZRXUSDT   - заморожено с 23:21:07 (~87 сек назад)
❌ SFPUSDT   - заморожено с 23:21:07 (~87 сек назад)
❌ ALICEUSDT - заморожено с 23:21:07 (~86 сек назад)
❌ WOOUSDT   - заморожено с 23:21:07 (~86 сек назад)
❌ REZUSDT   - заморожено с 23:21:07 (~86 сек назад)
⚠️  KAITOUSDT - работает (последний подписанный)
```

---

## 🐛 Root Cause

**Файл**: `websocket/binance_hybrid_stream.py`
**Метод**: `_run_mark_stream()` (строка 383)

**Проблема**: После переподключения WebSocket подписки НЕ восстанавливаются автоматически.

```python
async def _run_mark_stream(self):
    while self.running:
        try:
            # Connect
            self.mark_ws = await self.mark_session.ws_connect(url, ...)
            self.mark_connected = True
            logger.info("✅ [MARK] Connected")

            # ❌ ПРОБЛЕМА: Здесь должен быть вызов _restore_subscriptions()!

            # Receive loop
            async for msg in self.mark_ws:
                # ...
```

---

## ✅ Решение

### Добавить метод восстановления подписок:

```python
async def _restore_subscriptions(self):
    """Restore all mark price subscriptions after reconnect"""
    if not self.subscribed_symbols:
        return

    symbols_to_restore = list(self.subscribed_symbols)
    logger.info(f"🔄 [MARK] Restoring {len(symbols_to_restore)} subscriptions...")

    self.subscribed_symbols.clear()

    restored = 0
    for symbol in symbols_to_restore:
        try:
            await self._subscribe_mark_price(symbol)
            restored += 1
            if restored < len(symbols_to_restore):
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"❌ Failed to restore {symbol}: {e}")

    logger.info(f"✅ [MARK] Restored {restored}/{len(symbols_to_restore)} subscriptions")
```

### Вызвать после переподключения:

```python
async def _run_mark_stream(self):
    while self.running:
        try:
            # Connect
            self.mark_ws = await self.mark_session.ws_connect(url, ...)
            self.mark_connected = True
            logger.info("✅ [MARK] Connected")

            # ✅ FIX: Restore subscriptions
            await self._restore_subscriptions()

            # Receive loop
            async for msg in self.mark_ws:
                # ...
```

---

## 📝 План действий

### 1. Изменения кода (2 места)

**Место 1**: Добавить метод (после строки ~545)
```python
async def _restore_subscriptions(self):
    # ... код выше
```

**Место 2**: Вызвать метод (строка ~408)
```python
logger.info("✅ [MARK] Connected")
await self._restore_subscriptions()  # ← ДОБАВИТЬ ЭТУ СТРОКУ
```

### 2. Тестирование

- [ ] Unit test для `_restore_subscriptions()`
- [ ] Integration test - симуляция reconnect
- [ ] Manual test - реальное переподключение

### 3. Деплой

1. Остановить бота
2. Применить изменения
3. Запустить manual reconnect test
4. Запустить бота
5. Мониторить 30 минут

---

## 📊 Ожидаемый результат

### После фикса (логи):
```
23:45:35 - 🌐 [MARK] Connecting...
23:45:36 - ✅ [MARK] Connected
23:45:36 - 🔄 [MARK] Restoring 7 subscriptions...
23:45:36 - ✅ [MARK] Subscribed to ZBTUSDT
23:45:36 - ✅ [MARK] Subscribed to ZRXUSDT
23:45:36 - ✅ [MARK] Subscribed to SFPUSDT
23:45:37 - ✅ [MARK] Subscribed to ALICEUSDT
23:45:37 - ✅ [MARK] Subscribed to WOOUSDT
23:45:37 - ✅ [MARK] Subscribed to REZUSDT
23:45:37 - ✅ [MARK] Subscribed to KAITOUSDT
23:45:37 - ✅ [MARK] Restored 7/7 subscriptions
23:45:38 - position.update: ZBTUSDT, mark_price=0.27120000
23:45:38 - position.update: ZRXUSDT, mark_price=0.19750000
```

### В БД:
```
Все позиции получают обновления каждые 1-3 секунды
Trailing Stop активен и работает корректно
```

---

## 💰 Impact

| До фикса | После фикса |
|----------|-------------|
| ❌ 6/7 позиций без обновлений | ✅ 7/7 позиций обновляются |
| ❌ Trailing Stop НЕ работает | ✅ Trailing Stop активен |
| ❌ $35.60 в зоне риска | ✅ Все позиции защищены |
| ❌ Устаревший PnL | ✅ Актуальный PnL |

---

## 📚 Документация

**Полный forensic отчёт**: `FORENSIC_BINANCE_MARK_PRICE_BUG.md`

**Содержит**:
- Детальный timeline событий
- Код-анализ проблемы
- Полный план тестирования
- Мониторинг после деплоя
- Rollback план

---

**Время исправления**: ~30 минут
**Сложность**: Низкая
**Риск**: Минимальный (простое добавление вызова)

**READY FOR IMPLEMENTATION** 🚀
