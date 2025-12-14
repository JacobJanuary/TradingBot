#!/usr/bin/env python3
"""
Простой скрипт для проверки баланса на Binance Futures
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Correct path for scripts/ directory
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_balance():
    """Проверить баланс на Binance"""
    print("=" * 80)
    print("BINANCE FUTURES - ПРОВЕРКА БАЛАНСА")
    print("=" * 80)
    print()

    config = Config()
    binance_config_obj = config.get_exchange_config('binance')

    if not binance_config_obj:
        print("❌ Binance config не найден в настройках")
        return

    # Конвертируем ExchangeConfig в dict для ExchangeManager
    binance_config = {
        'api_key': binance_config_obj.api_key,
        'api_secret': binance_config_obj.api_secret,
        'testnet': binance_config_obj.testnet,
        'rate_limit': True
    }

    exchange = ExchangeManager(
        exchange_name='binance',
        config=binance_config,
        repository=None
    )

    try:
        # 1. Получить баланс через CCXT
        print("📊 Получение баланса через CCXT...")
        balance = await exchange.exchange.fetch_balance()

        usdt_balance = balance.get('USDT', {})
        free = float(usdt_balance.get('free', 0) or 0)
        used = float(usdt_balance.get('used', 0) or 0)
        total = float(usdt_balance.get('total', 0) or 0)

        print()
        print("💰 USDT БАЛАНС:")
        print(f"  Доступно (free) : ${free:,.2f}")
        print(f"  Используется    : ${used:,.2f}")
        print(f"  Всего (total)   : ${total:,.2f}")
        print()

        # 2. Получить детальную информацию через нативный API
        print("📊 Получение детальной информации через Binance API...")
        account_info = await exchange.exchange.fapiPrivateV2GetAccount()

        wallet_balance = float(account_info.get('totalWalletBalance', 0) or 0)
        unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0) or 0)
        margin_balance = float(account_info.get('totalMarginBalance', 0) or 0)
        initial_margin = float(account_info.get('totalInitialMargin', 0) or 0)
        available_balance = float(account_info.get('availableBalance', 0) or 0)
        max_withdraw = float(account_info.get('maxWithdrawAmount', 0) or 0)

        print()
        print("📈 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ:")
        print(f"  Баланс кошелька        : ${wallet_balance:,.2f}")
        print(f"  Нереализ. прибыль/убыток: ${unrealized_pnl:+,.2f}")
        print(f"  Маржа баланс           : ${margin_balance:,.2f}")
        print(f"  Маржа в позициях       : ${initial_margin:,.2f}")
        print(f"  ✅ Доступно для торговли: ${available_balance:,.2f}")
        print(f"  Доступно для вывода    : ${max_withdraw:,.2f}")
        print()

        # 3. Получить открытые позиции
        print("📊 Проверка открытых позиций...")
        positions = account_info.get('positions', [])
        open_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]

        print()
        print(f"📍 ПОЗИЦИИ:")
        print(f"  Всего позиций  : {len(positions)}")
        print(f"  Открытых позиций: {len(open_positions)}")
        print()

        if open_positions:
            print("  Открытые позиции (топ 10):")
            print(f"  {'Символ':<15} {'Количество':>12} {'Вход':>12} {'Текущая':>12} {'PnL':>12}")
            print("  " + "-" * 75)

            total_notional = 0
            total_pnl = 0

            for pos in open_positions[:10]:
                symbol = pos.get('symbol', 'UNKNOWN')
                position_amt = float(pos.get('positionAmt', 0))
                entry_price = float(pos.get('entryPrice', 0))
                mark_price = float(pos.get('markPrice', 0))
                unrealized_pnl = float(pos.get('unrealizedProfit', 0))
                notional = abs(float(pos.get('notional', 0)))

                total_notional += notional
                total_pnl += unrealized_pnl

                pnl_sign = "+" if unrealized_pnl >= 0 else ""
                print(f"  {symbol:<15} {position_amt:>12.4f} ${entry_price:>11.4f} ${mark_price:>11.4f} {pnl_sign}${unrealized_pnl:>10.2f}")

            if len(open_positions) > 10:
                print(f"  ... и еще {len(open_positions) - 10} позиций")

            print("  " + "-" * 75)
            print(f"  {'ИТОГО':<15} {'':>12} {'':>12} {'':>12} {'+' if total_pnl >= 0 else ''}${total_pnl:>10.2f}")
            print()
            print(f"  Общая стоимость позиций: ${total_notional:,.2f}")
            print()

        # 4. Сводная информация
        print("=" * 80)
        print("📊 СВОДКА")
        print("=" * 80)
        print(f"✅ Доступно для открытия новых позиций: ${available_balance:,.2f}")
        print(f"📊 Маржа в {len(open_positions)} открытых позициях: ${initial_margin:,.2f}")
        print(f"{'📈' if unrealized_pnl >= 0 else '📉'} Нереализованная прибыль/убыток: ${unrealized_pnl:+,.2f}")
        print(f"💼 Общий баланс кошелька: ${wallet_balance:,.2f}")
        print("=" * 80)
        print()

    except Exception as e:
        logger.error(f"❌ Ошибка при проверке баланса: {e}", exc_info=True)
        raise

    finally:
        await exchange.close()
        print("✅ Соединение закрыто")


if __name__ == '__main__':
    asyncio.run(check_balance())
