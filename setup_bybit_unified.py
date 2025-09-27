#!/usr/bin/env python3
"""
Автоматическая настройка и проверка Bybit UNIFIED Account
Этот скрипт поможет настроить всё необходимое для работы с Bybit Testnet
"""

import asyncio
import ccxt.async_support as ccxt
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


class BybitUnifiedSetup:
    """Настройка Bybit UNIFIED аккаунта"""
    
    def __init__(self):
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET')
        self.exchange = None
        
    def print_header(self, text):
        """Красивый заголовок"""
        print("\n" + "="*60)
        print(f"  {text}")
        print("="*60)
    
    def print_step(self, number, text):
        """Шаг процесса"""
        print(f"\n📌 ШАГ {number}: {text}")
        print("-"*40)
    
    async def check_current_setup(self):
        """Проверка текущей настройки"""
        self.print_header("ПРОВЕРКА ТЕКУЩЕЙ КОНФИГУРАЦИИ")
        
        # Проверка переменных окружения
        print("\n1️⃣ Переменные окружения:")
        if self.api_key:
            print(f"   ✅ BYBIT_API_KEY найден: {self.api_key[:8]}...")
        else:
            print("   ❌ BYBIT_API_KEY не найден")
            
        if self.api_secret:
            print(f"   ✅ BYBIT_API_SECRET найден: ***")
        else:
            print("   ❌ BYBIT_API_SECRET не найден")
        
        if not self.api_key or not self.api_secret:
            return False
            
        # Проверка подключения
        print("\n2️⃣ Проверка подключения к Bybit Testnet:")
        
        self.exchange = ccxt.bybit({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'testnet': True,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'accountType': 'UNIFIED'  # Пробуем с UNIFIED
            }
        })
        
        self.exchange.set_sandbox_mode(True)
        self.exchange.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com'
        }
        
        try:
            # Пробуем получить информацию об аккаунте
            account_info = await self.exchange.private_get_v5_account_info()
            result = account_info.get('result', {})
            
            print(f"   ✅ Подключение успешно")
            print(f"   Account Type: {result.get('accountType', 'UNKNOWN')}")
            print(f"   Unified Status: {result.get('unifiedMarginStatus', 0)}")
            
            if result.get('accountType') == 'UNIFIED':
                print(f"\n   🎉 У вас уже UNIFIED аккаунт!")
                return True
            else:
                print(f"\n   ⚠️ У вас НЕ UNIFIED аккаунт")
                return False
                
        except Exception as e:
            error_msg = str(e)
            if "accountType only support UNIFIED" in error_msg:
                print(f"   ❌ API требует UNIFIED аккаунт")
                print(f"   Необходимо активировать UNIFIED на testnet.bybit.com")
                return False
            else:
                print(f"   ❌ Ошибка: {error_msg}")
                return False
    
    def show_manual_instructions(self):
        """Показать инструкции для ручной настройки"""
        self.print_header("📋 ИНСТРУКЦИЯ ПО АКТИВАЦИИ UNIFIED ACCOUNT")
        
        print("""
1. ОТКРОЙТЕ БРАУЗЕР и перейдите на:
   🔗 https://testnet.bybit.com

2. ВОЙДИТЕ в свой testnet аккаунт
   (Если нет аккаунта - зарегистрируйтесь)

3. ПЕРЕЙДИТЕ в раздел ASSETS (Активы)
   - В верхнем меню выберите "Assets"
   - Или прямая ссылка: https://testnet.bybit.com/en-US/assets/overview

4. ПРОВЕРЬТЕ ТИП АККАУНТА
   - Найдите секцию "Account Type"
   - Если видите "Standard Account" - нужно переключиться

5. АКТИВИРУЙТЕ UNIFIED ACCOUNT:
   - Нажмите кнопку "Upgrade to Unified Account"
   - Подтвердите переход
   - Процесс мгновенный

6. СОЗДАЙТЕ НОВЫЕ API КЛЮЧИ:
   - Перейдите в "Account & Security" → "API Management"
   - Удалите старые ключи (если есть)
   - Создайте новые ключи с permissions:
     ✅ Read-Write
     ✅ Spot Trading - Trade
     ✅ USDT Perpetual - Trade
     ✅ Wallet - Account Transfer (опционально)

7. СОХРАНИТЕ КЛЮЧИ в файл .env:
   BYBIT_API_KEY=новый-ключ
   BYBIT_API_SECRET=новый-секрет

8. ПОЛУЧИТЕ ТЕСТОВЫЕ СРЕДСТВА:
   - Перейдите в "Assets" → "Faucet"
   - Запросите 10,000 USDT
   - Средства появятся мгновенно
""")
        
        print("\n" + "="*60)
        input("Нажмите Enter после выполнения инструкций...")
    
    async def verify_unified_account(self):
        """Проверка UNIFIED аккаунта после настройки"""
        self.print_header("ПРОВЕРКА UNIFIED ACCOUNT")
        
        # Перезагружаем переменные окружения
        load_dotenv(override=True)
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            print("❌ API ключи не найдены в .env")
            return False
        
        # Создаем новое подключение
        self.exchange = ccxt.bybit({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'testnet': True,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'accountType': 'UNIFIED'
            }
        })
        
        self.exchange.set_sandbox_mode(True)
        self.exchange.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com'
        }
        
        try:
            # Проверка аккаунта
            print("\n🔍 Проверка типа аккаунта...")
            account_info = await self.exchange.private_get_v5_account_info()
            result = account_info.get('result', {})
            account_type = result.get('accountType', 'UNKNOWN')
            
            if account_type != 'UNIFIED':
                print(f"❌ Аккаунт всё ещё не UNIFIED: {account_type}")
                return False
            
            print(f"✅ UNIFIED аккаунт активен!")
            
            # Проверка баланса
            print("\n🔍 Проверка баланса...")
            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            
            if usdt_balance > 0:
                print(f"✅ Баланс USDT: {usdt_balance:.2f}")
            else:
                print(f"⚠️ Баланс USDT: 0 (получите тестовые средства)")
            
            # Тест торговой функциональности
            print("\n🔍 Тест торговых функций...")
            
            # Получение позиций
            positions = await self.exchange.fetch_positions()
            print(f"✅ Позиции загружены: {len(positions)} открытых")
            
            # Получение тикера
            ticker = await self.exchange.fetch_ticker('BTC/USDT:USDT')
            print(f"✅ BTC/USDT: ${ticker['last']:,.2f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False
        finally:
            await self.exchange.close()
    
    async def create_config_file(self):
        """Создание правильного конфигурационного файла"""
        self.print_header("СОЗДАНИЕ КОНФИГУРАЦИИ")
        
        config = {
            "exchanges": {
                "bybit": {
                    "enabled": True,
                    "testnet": True,
                    "api_key": "${BYBIT_API_KEY}",
                    "api_secret": "${BYBIT_API_SECRET}",
                    "options": {
                        "defaultType": "future",
                        "accountType": "UNIFIED",
                        "recvWindow": 60000,
                        "enableRateLimit": True
                    },
                    "ws_reconnect_delay": 5,
                    "ws_reconnect_delay_max": 60,
                    "ws_max_reconnect_attempts": -1,
                    "ws_heartbeat_interval": 30,
                    "ws_heartbeat_timeout": 60
                }
            }
        }
        
        # Сохраняем в файл
        config_path = Path("config/bybit_unified.json")
        config_path.parent.mkdir(exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Конфигурация сохранена в {config_path}")
        
        # Также обновляем основной config.yaml
        print("\n📝 Добавьте в config/config.yaml:")
        print("""
exchanges:
  bybit:
    enabled: true
    testnet: true
    api_key: ${BYBIT_API_KEY}
    api_secret: ${BYBIT_API_SECRET}
    options:
      defaultType: 'future'
      accountType: 'UNIFIED'  # ВАЖНО!
""")
    
    async def test_trading(self):
        """Тест торговых операций"""
        self.print_header("ТЕСТ ТОРГОВЫХ ОПЕРАЦИЙ")
        
        if not self.exchange:
            print("❌ Exchange не инициализирован")
            return
        
        try:
            symbol = 'BTC/USDT:USDT'
            
            # Получаем текущую цену
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            print(f"\n📊 Тестовый ордер на {symbol}:")
            print(f"   Текущая цена: ${current_price:,.2f}")
            
            # Параметры тестового ордера
            side = 'buy'
            amount = 0.001  # Минимальный размер
            price = current_price * 0.95  # 5% ниже рынка
            
            print(f"   Размещение: {side.upper()} {amount} BTC")
            print(f"   Лимит цена: ${price:,.2f}")
            
            # Проверка баланса
            balance = await self.exchange.fetch_balance()
            usdt_free = balance.get('USDT', {}).get('free', 0)
            
            if usdt_free < price * amount:
                print(f"   ⚠️ Недостаточно средств: ${usdt_free:.2f} USDT")
                print(f"   Необходимо: ${price * amount:.2f} USDT")
                return
            
            # Размещаем ордер
            order = await self.exchange.create_order(
                symbol=symbol,
                type='limit',
                side=side,
                amount=amount,
                price=price
            )
            
            order_id = order['id']
            print(f"   ✅ Ордер размещен! ID: {order_id}")
            
            # Ждем немного
            await asyncio.sleep(2)
            
            # Отменяем ордер
            await self.exchange.cancel_order(order_id, symbol)
            print(f"   ✅ Ордер отменен")
            
            print("\n🎉 Все тесты пройдены успешно!")
            
        except Exception as e:
            print(f"❌ Ошибка при тестировании: {e}")
    
    async def run(self):
        """Главный процесс настройки"""
        self.print_header("🚀 НАСТРОЙКА BYBIT UNIFIED ACCOUNT")
        
        print("""
Этот скрипт поможет вам:
1. Проверить текущие настройки
2. Активировать UNIFIED account
3. Настроить API ключи
4. Проверить работоспособность
""")
        
        # Шаг 1: Проверка текущей конфигурации
        self.print_step(1, "Проверка текущей конфигурации")
        is_unified = await self.check_current_setup()
        
        if not is_unified:
            # Шаг 2: Инструкции по активации
            self.print_step(2, "Активация UNIFIED Account")
            self.show_manual_instructions()
            
            # Шаг 3: Проверка после настройки
            self.print_step(3, "Проверка новой конфигурации")
            is_unified = await self.verify_unified_account()
            
            if not is_unified:
                print("\n❌ UNIFIED account не активирован")
                print("Пожалуйста, следуйте инструкциям выше")
                return False
        
        # Шаг 4: Создание конфигурации
        self.print_step(4, "Создание конфигурационных файлов")
        await self.create_config_file()
        
        # Шаг 5: Тестирование
        self.print_step(5, "Тестирование торговых функций")
        await self.test_trading()
        
        # Завершение
        self.print_header("✅ НАСТРОЙКА ЗАВЕРШЕНА")
        print("""
Bybit UNIFIED account настроен и готов к работе!

Следующие шаги:
1. Запустите бота: python main.py --mode shadow
2. Проверьте логи: tail -f logs/trading_bot.log
3. Мониторинг: http://localhost:8000/metrics

Документация: docs/BYBIT_UNIFIED_SETUP.md
""")
        
        return True


async def main():
    """Точка входа"""
    setup = BybitUnifiedSetup()
    
    try:
        success = await setup.run()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
        return 1
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)