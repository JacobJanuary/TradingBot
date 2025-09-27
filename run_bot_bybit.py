#!/usr/bin/env python3
"""
Запуск торгового бота с Bybit UNIFIED Account
"""
import asyncio
import logging
import sys
from datetime import datetime
import argparse
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

from main import TradingBot
from config.config_manager import ConfigManager
import ccxt.async_support as ccxt

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bybit_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def verify_bybit_setup():
    """Проверка настройки Bybit перед запуском бота"""
    logger.info("="*60)
    logger.info("🔍 Проверка Bybit UNIFIED Account")
    logger.info("="*60)
    
    config_manager = ConfigManager()
    config = config_manager.config
    
    # Проверяем конфигурацию Bybit (сначала проверяем в trading.exchanges)
    bybit_config = None
    
    # Ищем в списке exchanges
    trading_config = config.get('trading', {})
    exchanges_list = trading_config.get('exchanges', [])
    
    for exchange in exchanges_list:
        if exchange.get('name') == 'bybit':
            bybit_config = exchange
            break
    
    # Если не нашли в списке, проверяем на верхнем уровне
    if not bybit_config:
        bybit_config = config.get('bybit', {})
    
    if not bybit_config.get('enabled'):
        logger.error("❌ Bybit не включен в конфигурации")
        logger.info("Установите 'enabled: true' в config/config.yaml")
        return False
    
    # Получаем API ключи с верхнего уровня конфигурации
    api_key = config.get('bybit', {}).get('api_key')
    api_secret = config.get('bybit', {}).get('api_secret')
    
    if not api_key or not api_secret:
        logger.error("❌ API ключи не найдены")
        logger.info("Добавьте BYBIT_API_KEY и BYBIT_API_SECRET в .env")
        return False
    
    # Проверяем подключение
    try:
        exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'testnet': bybit_config.get('testnet', True),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'accountType': 'UNIFIED'
            }
        })
        
        if bybit_config.get('testnet', True):
            exchange.set_sandbox_mode(True)
        
        # Быстрая проверка
        balance = await exchange.fetch_balance()
        usdt = balance.get('USDT', {}).get('total', 0)
        
        logger.info(f"✅ Bybit UNIFIED подключен")
        logger.info(f"   CCXT версия: {ccxt.__version__}")
        logger.info(f"   Режим: {'TESTNET' if bybit_config.get('testnet') else 'MAINNET'}")
        logger.info(f"   Баланс USDT: {usdt:.2f}")
        
        await exchange.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Bybit: {e}")
        
        if "accountType only support UNIFIED" in str(e):
            logger.error("Требуется UNIFIED account!")
            logger.info("1. Зайдите на testnet.bybit.com")
            logger.info("2. Активируйте UNIFIED account")
            logger.info("3. Создайте новые API ключи")
        
        return False


async def run_bot(mode: str = 'shadow'):
    """Запуск торгового бота"""
    
    # Проверяем настройку Bybit
    if not await verify_bybit_setup():
        logger.error("❌ Настройка Bybit не завершена")
        return False
    
    logger.info("\n" + "="*60)
    logger.info(f"🚀 Запуск Trading Bot в режиме {mode.upper()}")
    logger.info("="*60)
    
    # Создаем namespace для аргументов
    args = argparse.Namespace()
    args.mode = mode
    args.config = 'config/config.yaml'
    
    # Создаем и запускаем бота
    bot = TradingBot(args)
    
    try:
        # Инициализация
        logger.info("\n📦 Инициализация компонентов...")
        await bot.initialize()
        
        logger.info("\n✅ Инициализация завершена")
        logger.info("\nКомпоненты:")
        logger.info(f"  • Exchanges: {', '.join(bot.exchanges.keys())}")
        logger.info(f"  • WebSockets: {', '.join(bot.websockets.keys())}")
        logger.info(f"  • Mode: {bot.mode}")
        
        # Показываем начальное состояние
        logger.info("\n📊 Начальное состояние:")
        
        for name, exchange in bot.exchanges.items():
            try:
                balance = await exchange.fetch_balance()
                usdt = balance.get('USDT', {}).get('free', 0)
                logger.info(f"  {name.upper()}: ${usdt:.2f} USDT")
                
                positions = await exchange.fetch_positions()
                open_positions = [p for p in positions if p.get('contracts', 0) > 0]
                if open_positions:
                    logger.info(f"    Открытых позиций: {len(open_positions)}")
                
            except Exception as e:
                logger.warning(f"  {name}: Ошибка получения данных - {e}")
        
        # Запускаем основной цикл
        logger.info("\n" + "="*60)
        logger.info("🟢 БОТ ЗАПУЩЕН И РАБОТАЕТ")
        logger.info("="*60)
        logger.info("\nДля остановки нажмите Ctrl+C")
        logger.info("\nМониторинг:")
        logger.info("  • Логи: tail -f logs/bybit_bot.log")
        logger.info("  • Метрики: http://localhost:8000/metrics")
        
        # Запускаем бота
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Получен сигнал остановки...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        logger.info("\n🛑 Остановка бота...")
        try:
            await bot.cleanup()
        except:
            pass
        logger.info("✅ Бот остановлен")
    
    return True


async def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='Trading Bot для Bybit')
    parser.add_argument(
        '--mode',
        choices=['production', 'shadow', 'backtest'],
        default='shadow',
        help='Режим работы бота (default: shadow)'
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Только проверить настройки, не запускать бота'
    )
    
    args = parser.parse_args()
    
    # Печатаем заголовок
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║                TRADING BOT - BYBIT                  ║
    ║              UNIFIED ACCOUNT EDITION                ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    if args.check_only:
        # Только проверка
        result = await verify_bybit_setup()
        if result:
            print("\n✅ Все проверки пройдены! Бот готов к запуску.")
            print("\nЗапустите без --check-only для старта бота")
        else:
            print("\n❌ Проверки не пройдены. См. ошибки выше.")
        return 0 if result else 1
    
    # Предупреждение для production режима
    if args.mode == 'production':
        print("\n⚠️  ВНИМАНИЕ: Production режим!")
        print("Бот будет совершать РЕАЛЬНЫЕ сделки!")
        response = input("Вы уверены? (yes/no): ")
        if response.lower() != 'yes':
            print("Отменено.")
            return 0
    
    # Запускаем бота
    success = await run_bot(args.mode)
    
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {e}", exc_info=True)
        sys.exit(1)