# 🚨 БЫСТРОЕ РЕШЕНИЕ: Bybit UNIFIED Account

## Проблема
Ваш Bybit testnet аккаунт НЕ является UNIFIED, поэтому API не работает.

## Решение за 5 минут

### 1️⃣ Откройте Bybit Testnet
🔗 **https://testnet.bybit.com**

### 2️⃣ Войдите в аккаунт
Используйте существующие учетные данные testnet

### 3️⃣ Активируйте UNIFIED Account

1. Нажмите **Assets** в верхнем меню
2. Найдите блок **Account Type**
3. Вы увидите:
   ```
   Standard Account (Current) ← Это ваш текущий тип
   Unified Trading Account ← Нужно переключиться сюда
   ```
4. Нажмите кнопку **"Upgrade to Unified Account"**
5. Подтвердите переход (мгновенно)

### 4️⃣ Создайте НОВЫЕ API ключи

⚠️ **ВАЖНО**: Старые ключи НЕ будут работать с UNIFIED!

1. Перейдите в **Account & Security** → **API Management**
2. **Удалите** старые ключи
3. Нажмите **Create New Key**
4. Настройки:
   - Name: `TradingBot`
   - Permissions:
     - ✅ Read-Write
     - ✅ Spot Trading - Trade
     - ✅ USDT Perpetual - Trade
5. **Сохраните ключи!**

### 5️⃣ Обновите .env файл

```bash
BYBIT_API_KEY=новый-ключ-здесь
BYBIT_API_SECRET=новый-секрет-здесь
```

### 6️⃣ Получите тестовые средства

1. В разделе **Assets** найдите **Faucet** или **Test Coins**
2. Запросите **10,000 USDT**
3. Средства появятся мгновенно

### 7️⃣ Проверьте подключение

```bash
python test_bybit_unified.py
```

## Если ключи работали раньше

Ваши текущие ключи (`OX1dzf7b...`) созданы для Standard Account. После перехода на UNIFIED они перестанут работать. Это нормально - просто создайте новые.

## Статус вашего аккаунта

- **Account Type**: UNKNOWN (не UNIFIED)
- **Unified Status**: 5 (должен быть 1)
- **Решение**: Активировать UNIFIED и создать новые ключи

---

## Прямые ссылки

1. [Активация UNIFIED](https://testnet.bybit.com/en-US/assets/overview) - найдите "Account Type"
2. [Создание API ключей](https://testnet.bybit.com/en-US/user/security/api-management)
3. [Получение тестовых средств](https://testnet.bybit.com/en-US/faucet)

---

После выполнения этих шагов бот заработает!