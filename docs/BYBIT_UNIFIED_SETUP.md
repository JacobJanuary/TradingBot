# Bybit UNIFIED Account Setup Guide

## 📋 Содержание
1. [Что такое UNIFIED Account](#что-такое-unified-account)
2. [Настройка Testnet](#настройка-testnet)
3. [Получение API ключей](#получение-api-ключей)
4. [Конфигурация в боте](#конфигурация-в-боте)
5. [Решение проблем](#решение-проблем)

---

## Что такое UNIFIED Account

**UNIFIED Account** - это единый торговый аккаунт Bybit, который объединяет:
- Spot Trading (спот)
- Derivatives Trading (деривативы)
- Options Trading (опционы)
- USDC Contracts

### Преимущества UNIFIED Account:
- ✅ Единый баланс для всех типов торговли
- ✅ Кросс-маржа между позициями
- ✅ Упрощенное управление рисками
- ✅ Более эффективное использование капитала

### Standard Account vs UNIFIED Account:
| Параметр | Standard Account | UNIFIED Account |
|----------|-----------------|-----------------|
| Балансы | Разделены по типам | Единый баланс |
| API | Разные endpoint'ы | Унифицированные v5 API |
| Маржа | Изолированная | Кросс-маржа доступна |
| Testnet | Ограниченная поддержка | Полная поддержка |

---

## Настройка Testnet

### Шаг 1: Регистрация на Bybit Testnet

1. Перейдите на **[testnet.bybit.com](https://testnet.bybit.com)**
2. Нажмите **"Register"** (Регистрация)
3. Используйте email (можно тот же, что и на mainnet)
4. Подтвердите email

⚠️ **ВАЖНО**: Testnet - это отдельная среда. Аккаунты mainnet и testnet независимы!

### Шаг 2: Активация UNIFIED Account

1. Войдите в testnet аккаунт
2. Перейдите в **Assets** → **Account Type**
3. Вы увидите опции:
   ```
   [ ] Standard Account (Classic)
   [✓] Unified Trading Account (Recommended)
   ```
4. Выберите **Unified Trading Account**
5. Нажмите **Upgrade Now**

### Шаг 3: Получение тестовых средств

1. Перейдите в **Assets** → **Faucet** (или **Test Coins**)
2. Запросите тестовые токены:
   - **USDT**: 10,000 USDT (для торговли)
   - **BTC**: 1 BTC (опционально)
   - **ETH**: 100 ETH (опционально)
3. Средства появятся мгновенно

---

## Получение API ключей

### Шаг 1: Создание API ключей для UNIFIED Account

1. В testnet аккаунте перейдите в **Account & Security** → **API Management**
2. Нажмите **Create New Key**
3. Выберите тип: **System-generated API Keys**
4. Настройки API ключа:

   **API Key Information:**
   - Name: `TradingBot_Testnet`
   - IP restriction: `No Restriction` (для тестирования)
   
   **API Key Permissions:**
   ```
   ✅ Read-Write (необходимо для торговли)
   
   Unified Trading:
   ✅ Spot Trading - Trade
   ✅ USDT Perpetual - Trade
   ✅ USDC Perpetual - Trade
   ✅ USDC Options - Trade
   
   Account Permissions:
   ✅ Wallet - Account Transfer (опционально)
   ✅ Exchange - Exchange History
   ✅ NFT (можно не включать)
   ```

5. Нажмите **Submit**
6. **СОХРАНИТЕ**:
   - **API Key**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - **API Secret**: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

⚠️ **ВАЖНО**: Secret показывается только один раз! Сохраните его сразу!

### Шаг 2: Проверка типа аккаунта через API

```bash
# Проверка типа аккаунта
curl -X GET "https://api-testnet.bybit.com/v5/account/info" \
  -H "X-BAPI-API-KEY: your-api-key" \
  -H "X-BAPI-TIMESTAMP: 1234567890000" \
  -H "X-BAPI-SIGN: your-signature"
```

Ответ должен содержать:
```json
{
  "retCode": 0,
  "result": {
    "unifiedMarginStatus": 1,  // 1 = UNIFIED, 0 = Classic
    "accountType": "UNIFIED"    // Должен быть UNIFIED
  }
}
```

---

## Конфигурация в боте

### 1. Файл `.env`:
```bash
# Bybit Testnet API Credentials (UNIFIED Account)
BYBIT_TESTNET_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
BYBIT_TESTNET_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Убедитесь, что используется testnet
BYBIT_TESTNET=true
```

### 2. Файл `config/config.yaml`:
```yaml
exchanges:
  bybit:
    enabled: true
    testnet: true
    api_key: ${BYBIT_TESTNET_API_KEY}
    api_secret: ${BYBIT_TESTNET_API_SECRET}
    
    # ВАЖНО: Указать тип аккаунта
    options:
      defaultType: 'future'    # Для деривативов
      accountType: 'UNIFIED'   # Обязательно для v5 API
      
    # Правильные URL для testnet
    urls:
      api: 'https://api-testnet.bybit.com'
      public: 'https://api-testnet.bybit.com'
      private: 'https://api-testnet.bybit.com'
      
    # WebSocket URLs
    ws_urls:
      public: 'wss://stream-testnet.bybit.com/v5/public'
      private: 'wss://stream-testnet.bybit.com/v5/private'
```

### 3. Код инициализации (`exchange_manager.py`):
```python
async def initialize_bybit(self):
    """Initialize Bybit with UNIFIED account"""
    
    # Проверка testnet
    if self.config.get('testnet'):
        self.exchange.set_sandbox_mode(True)
        
        # Установка правильных URL для testnet
        self.exchange.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com'
        }
    
    # ВАЖНО: Установка типа аккаунта
    self.exchange.options['defaultType'] = 'future'  # или 'spot'
    self.exchange.options['accountType'] = 'UNIFIED'  # Обязательно!
    
    # Проверка подключения
    try:
        account_info = await self.exchange.fetch_balance()
        logger.info(f"Bybit UNIFIED account connected: {account_info}")
    except Exception as e:
        if "accountType only support UNIFIED" in str(e):
            logger.error("Ошибка: Требуется UNIFIED аккаунт!")
            logger.error("Перейдите на testnet.bybit.com и активируйте UNIFIED account")
        raise
```

---

## Решение проблем

### Ошибка: "accountType only support UNIFIED"

**Причина**: API ключи созданы для Standard Account, а не UNIFIED.

**Решение**:
1. Войдите в [testnet.bybit.com](https://testnet.bybit.com)
2. Проверьте тип аккаунта в **Assets**
3. Если Standard - переключитесь на UNIFIED
4. Создайте **новые** API ключи после переключения

### Ошибка: "Invalid API key"

**Возможные причины**:
1. Используются mainnet ключи для testnet (или наоборот)
2. Ключи скопированы с ошибкой
3. Не включены нужные permissions

**Решение**:
```python
# Проверка ключей
import ccxt

exchange = ccxt.bybit({
    'apiKey': 'your-key',
    'secret': 'your-secret',
    'testnet': True,
    'options': {
        'defaultType': 'future',
        'accountType': 'UNIFIED'
    }
})

# Установка sandbox mode для CCXT
exchange.set_sandbox_mode(True)

# Тест подключения
try:
    balance = exchange.fetch_balance()
    print("✅ Подключение успешно!")
    print(f"USDT Balance: {balance['USDT']['free']}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
```

### Ошибка: "Insufficient balance"

**Решение**:
1. Перейдите в **Assets** → **Faucet**
2. Запросите тестовые USDT
3. Проверьте, что средства в **Unified Account**, а не в **Funding Account**
4. Если нужно, сделайте internal transfer

### WebSocket не подключается

**Проверьте URL**:
- Testnet WebSocket: `wss://stream-testnet.bybit.com/v5/private`
- Mainnet WebSocket: `wss://stream.bybit.com/v5/private`

**Проверьте подпись**:
```python
import hmac
import hashlib
import time

def generate_signature(secret, timestamp):
    param_str = f"GET/realtime{timestamp}"
    return hmac.new(
        secret.encode('utf-8'),
        param_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
```

---

## Полезные ссылки

### Официальная документация:
- [Bybit Testnet](https://testnet.bybit.com)
- [Bybit V5 API Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Unified Account Guide](https://www.bybit.com/en-US/help-center/article/Introduction-to-Unified-Trading-Account)
- [API Management Guide](https://www.bybit.com/en-US/help-center/article/How-to-create-API-key)

### Инструменты:
- [Postman Collection](https://github.com/bybit-exchange/postman-collections)
- [API Explorer](https://bybit-exchange.github.io/docs/v5/explorer)
- [WebSocket Test Tool](https://testnet.bybit.com/en-US/wstest)

### Поддержка:
- [Bybit API Telegram](https://t.me/BybitAPI)
- [GitHub Issues](https://github.com/bybit-exchange/bybit-api-docs/issues)

---

## Чеклист настройки

- [ ] Зарегистрирован на testnet.bybit.com
- [ ] Активирован UNIFIED Account
- [ ] Получены тестовые средства (USDT)
- [ ] Созданы API ключи с правильными permissions
- [ ] API ключи сохранены в `.env`
- [ ] Настроен `config.yaml` с `accountType: 'UNIFIED'`
- [ ] Проверено подключение через тестовый скрипт
- [ ] WebSocket успешно подключается

---

## Пример тестового скрипта

```python
#!/usr/bin/env python3
"""Test Bybit UNIFIED Account Connection"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def test_bybit_unified():
    """Test Bybit UNIFIED account connection"""
    
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_TESTNET_API_KEY'),
        'secret': os.getenv('BYBIT_TESTNET_API_SECRET'),
        'testnet': True,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'  # ВАЖНО!
        }
    })
    
    # Включаем testnet mode
    exchange.set_sandbox_mode(True)
    
    try:
        # Проверка баланса
        print("Checking balance...")
        balance = await exchange.fetch_balance()
        print(f"✅ USDT Balance: {balance['USDT']['free']:.2f}")
        
        # Проверка информации об аккаунте
        print("\nFetching account info...")
        account_info = await exchange.private_get_v5_account_info()
        account_type = account_info['result']['accountType']
        print(f"✅ Account Type: {account_type}")
        
        if account_type != 'UNIFIED':
            print("⚠️ WARNING: Not a UNIFIED account!")
            print("Please upgrade to UNIFIED account on testnet.bybit.com")
        
        # Проверка рынков
        print("\nFetching markets...")
        markets = await exchange.fetch_markets()
        futures_markets = [m for m in markets if m['future']]
        print(f"✅ Available futures markets: {len(futures_markets)}")
        
        # Тестовый ордер (не выполняется)
        print("\nTesting order placement (dry run)...")
        symbol = 'BTC/USDT:USDT'
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last'] * 0.9  # 10% ниже рынка
        
        print(f"Would place order: BUY 0.001 BTC at ${price:.2f}")
        print("✅ All checks passed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
        if "accountType only support UNIFIED" in str(e):
            print("\n📋 TO FIX THIS ERROR:")
            print("1. Go to testnet.bybit.com")
            print("2. Login to your account")
            print("3. Go to Assets → Account Type")
            print("4. Switch to UNIFIED Account")
            print("5. Create new API keys")
            print("6. Update your .env file")
    
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_bybit_unified())
```

Сохраните этот скрипт как `test_bybit_unified.py` и запустите для проверки подключения.