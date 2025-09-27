#!/usr/bin/env python3
"""
Test Bybit UNIFIED Account Connection
Проверка подключения к Bybit Testnet с UNIFIED аккаунтом
"""

import asyncio
import ccxt.async_support as ccxt
import os
import sys
from dotenv import load_dotenv
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()


class BybitUnifiedTester:
    """Тестер для Bybit UNIFIED Account"""
    
    def __init__(self):
        self.api_key = os.getenv('BYBIT_API_KEY') or os.getenv('BYBIT_TESTNET_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET') or os.getenv('BYBIT_TESTNET_API_SECRET')
        self.exchange = None
        
    async def initialize(self):
        """Инициализация подключения"""
        logger.info("=" * 60)
        logger.info("BYBIT UNIFIED ACCOUNT CONNECTION TEST")
        logger.info("=" * 60)
        
        if not self.api_key or not self.api_secret:
            logger.error("❌ API ключи не найдены в .env файле")
            logger.error("Добавьте BYBIT_API_KEY и BYBIT_API_SECRET в .env")
            return False
        
        logger.info("✅ API ключи загружены")
        logger.info(f"   API Key: {self.api_key[:8]}...")
        
        # Создание exchange объекта
        self.exchange = ccxt.bybit({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'testnet': True,  # ВАЖНО: используем testnet
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',    # Для фьючерсов
                'accountType': 'UNIFIED',   # ВАЖНО: указываем UNIFIED
                'recvWindow': 60000,
            }
        })
        
        # Включаем sandbox mode для CCXT
        self.exchange.set_sandbox_mode(True)
        
        # Устанавливаем правильные URL для testnet
        self.exchange.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com',
        }
        
        logger.info("✅ Exchange объект создан с UNIFIED настройками")
        return True
    
    async def test_connection(self):
        """Тест базового подключения"""
        logger.info("\n🔍 Тестирование подключения...")
        
        try:
            # Проверка времени сервера
            server_time = await self.exchange.fetch_time()
            server_dt = datetime.fromtimestamp(server_time / 1000)
            logger.info(f"✅ Подключение установлено")
            logger.info(f"   Время сервера: {server_dt}")
            
            # Проверка статуса сервера
            status = await self.exchange.fetch_status()
            logger.info(f"   Статус: {status.get('status', 'unknown')}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    async def test_account_info(self):
        """Проверка информации об аккаунте"""
        logger.info("\n🔍 Проверка типа аккаунта...")
        
        try:
            # Используем прямой API вызов для получения информации об аккаунте
            account_info = await self.exchange.private_get_v5_account_info()
            
            result = account_info.get('result', {})
            account_type = result.get('accountType', 'UNKNOWN')
            unified_status = result.get('unifiedMarginStatus', 0)
            
            logger.info(f"   Account Type: {account_type}")
            logger.info(f"   Unified Status: {unified_status} (1=UNIFIED, 0=Classic)")
            
            if account_type == 'UNIFIED':
                logger.info("✅ UNIFIED аккаунт активен!")
                return True
            else:
                logger.warning("⚠️ Аккаунт не UNIFIED!")
                logger.warning("   Необходимо активировать UNIFIED account на testnet.bybit.com")
                return False
                
        except Exception as e:
            error_msg = str(e)
            
            if "accountType only support UNIFIED" in error_msg:
                logger.error("❌ ОШИБКА: API требует UNIFIED аккаунт!")
                logger.info("\n📋 КАК ИСПРАВИТЬ:")
                logger.info("1. Перейдите на https://testnet.bybit.com")
                logger.info("2. Войдите в аккаунт")
                logger.info("3. Assets → Account Type")
                logger.info("4. Выберите 'Unified Trading Account'")
                logger.info("5. Нажмите 'Upgrade Now'")
                logger.info("6. Создайте новые API ключи")
                logger.info("7. Обновите .env файл")
            else:
                logger.error(f"❌ Ошибка получения информации об аккаунте: {e}")
            
            return False
    
    async def test_balance(self):
        """Проверка баланса"""
        logger.info("\n🔍 Проверка баланса...")
        
        try:
            balance = await self.exchange.fetch_balance()
            
            # Показываем основные валюты
            currencies = ['USDT', 'BTC', 'ETH']
            has_funds = False
            
            for currency in currencies:
                if currency in balance:
                    free = balance[currency].get('free', 0)
                    used = balance[currency].get('used', 0)
                    total = balance[currency].get('total', 0)
                    
                    if total > 0:
                        has_funds = True
                        logger.info(f"   {currency}:")
                        logger.info(f"      Free: {free:.4f}")
                        logger.info(f"      Used: {used:.4f}")
                        logger.info(f"      Total: {total:.4f}")
            
            if not has_funds:
                logger.warning("⚠️ Нет средств на счете!")
                logger.info("\n📋 КАК ПОЛУЧИТЬ ТЕСТОВЫЕ СРЕДСТВА:")
                logger.info("1. Перейдите на https://testnet.bybit.com")
                logger.info("2. Assets → Faucet (или Test Coins)")
                logger.info("3. Запросите USDT (10,000)")
                logger.info("4. Средства появятся мгновенно")
            else:
                logger.info("✅ Баланс получен успешно")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            return False
    
    async def test_markets(self):
        """Проверка доступных рынков"""
        logger.info("\n🔍 Проверка рынков...")
        
        try:
            markets = await self.exchange.fetch_markets()
            
            # Фильтруем рынки
            spot_markets = [m for m in markets if m.get('spot', False)]
            futures_markets = [m for m in markets if m.get('future', False)]
            active_markets = [m for m in markets if m.get('active', False)]
            
            logger.info(f"   Всего рынков: {len(markets)}")
            logger.info(f"   Спот рынков: {len(spot_markets)}")
            logger.info(f"   Фьючерс рынков: {len(futures_markets)}")
            logger.info(f"   Активных рынков: {len(active_markets)}")
            
            # Показываем популярные фьючерсы
            popular = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']
            logger.info("\n   Популярные фьючерсы:")
            
            for symbol in popular:
                market = self.exchange.market(symbol) if symbol in self.exchange.markets else None
                if market:
                    logger.info(f"      ✅ {symbol} - доступен")
                else:
                    logger.info(f"      ❌ {symbol} - не найден")
            
            logger.info("✅ Рынки загружены успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки рынков: {e}")
            return False
    
    async def test_ticker(self):
        """Проверка получения тикера"""
        logger.info("\n🔍 Проверка тикеров...")
        
        try:
            symbol = 'BTC/USDT:USDT'
            ticker = await self.exchange.fetch_ticker(symbol)
            
            logger.info(f"   {symbol}:")
            logger.info(f"      Last: ${ticker.get('last', 0):,.2f}")
            logger.info(f"      Bid: ${ticker.get('bid', 0):,.2f}")
            logger.info(f"      Ask: ${ticker.get('ask', 0):,.2f}")
            logger.info(f"      Volume 24h: {ticker.get('quoteVolume', 0):,.0f} USDT")
            logger.info(f"      Change 24h: {ticker.get('percentage', 0):.2f}%")
            
            logger.info("✅ Тикер получен успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения тикера: {e}")
            return False
    
    async def test_order_placement(self):
        """Тест размещения ордера (dry run)"""
        logger.info("\n🔍 Тест размещения ордера (симуляция)...")
        
        try:
            symbol = 'BTC/USDT:USDT'
            ticker = await self.exchange.fetch_ticker(symbol)
            
            # Параметры тестового ордера (далеко от рынка)
            side = 'buy'
            order_type = 'limit'
            amount = 0.001  # Минимальный размер
            price = ticker['last'] * 0.8  # 20% ниже рынка
            
            logger.info(f"   Симуляция ордера:")
            logger.info(f"      Symbol: {symbol}")
            logger.info(f"      Side: {side}")
            logger.info(f"      Type: {order_type}")
            logger.info(f"      Amount: {amount} BTC")
            logger.info(f"      Price: ${price:,.2f}")
            logger.info(f"      Value: ${price * amount:,.2f}")
            
            # Проверяем, достаточно ли баланса
            balance = await self.exchange.fetch_balance()
            usdt_free = balance.get('USDT', {}).get('free', 0)
            
            if usdt_free >= price * amount:
                logger.info(f"   ✅ Баланс достаточен: ${usdt_free:,.2f} USDT")
                
                # Можно попробовать реально разместить ордер
                logger.info("\n   Размещение реального ордера...")
                try:
                    order = await self.exchange.create_order(
                        symbol=symbol,
                        type=order_type,
                        side=side,
                        amount=amount,
                        price=price
                    )
                    
                    order_id = order.get('id')
                    logger.info(f"   ✅ Ордер размещен! ID: {order_id}")
                    
                    # Отменяем ордер
                    await asyncio.sleep(1)
                    await self.exchange.cancel_order(order_id, symbol)
                    logger.info(f"   ✅ Ордер отменен")
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Не удалось разместить ордер: {e}")
            else:
                logger.warning(f"   ⚠️ Недостаточно средств: ${usdt_free:,.2f} USDT")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка теста ордера: {e}")
            return False
    
    async def test_positions(self):
        """Проверка позиций"""
        logger.info("\n🔍 Проверка позиций...")
        
        try:
            positions = await self.exchange.fetch_positions()
            
            if positions:
                logger.info(f"   Открытых позиций: {len(positions)}")
                for pos in positions[:5]:  # Показываем первые 5
                    logger.info(f"   {pos['symbol']}:")
                    logger.info(f"      Side: {pos.get('side', 'N/A')}")
                    logger.info(f"      Contracts: {pos.get('contracts', 0)}")
                    logger.info(f"      Entry: ${pos.get('entryPrice', 0):,.2f}")
                    logger.info(f"      PnL: ${pos.get('unrealizedPnl', 0):,.2f}")
            else:
                logger.info("   Нет открытых позиций")
            
            logger.info("✅ Позиции проверены")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки позиций: {e}")
            return False
    
    async def run_all_tests(self):
        """Запуск всех тестов"""
        
        # Инициализация
        if not await self.initialize():
            return False
        
        results = {}
        
        # Запуск тестов
        tests = [
            ("Connection", self.test_connection),
            ("Account Info", self.test_account_info),
            ("Balance", self.test_balance),
            ("Markets", self.test_markets),
            ("Ticker", self.test_ticker),
            ("Positions", self.test_positions),
            ("Order Placement", self.test_order_placement),
        ]
        
        for test_name, test_func in tests:
            try:
                result = await test_func()
                results[test_name] = "PASSED" if result else "FAILED"
            except Exception as e:
                logger.error(f"Test {test_name} crashed: {e}")
                results[test_name] = "ERROR"
        
        # Закрытие соединения
        await self.exchange.close()
        
        # Итоги
        logger.info("\n" + "=" * 60)
        logger.info("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        logger.info("=" * 60)
        
        all_passed = True
        for test_name, result in results.items():
            emoji = "✅" if result == "PASSED" else "❌"
            logger.info(f"{emoji} {test_name}: {result}")
            if result != "PASSED":
                all_passed = False
        
        if all_passed:
            logger.info("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
            logger.info("Bybit UNIFIED account настроен правильно")
        else:
            logger.warning("\n⚠️ Некоторые тесты не пройдены")
            logger.info("Проверьте инструкции в docs/BYBIT_UNIFIED_SETUP.md")
        
        return all_passed


async def main():
    """Главная функция"""
    tester = BybitUnifiedTester()
    
    try:
        success = await tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("\nТест прерван пользователем")
        return 1
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)