#!/usr/bin/env python3
"""
ТЕСТ: Bybit Free Balance Bug - MINIMUM_ACTIVE_BALANCE_USD не работает

ПРОБЛЕМА:
- Баланс упал до $3.36 USDT несмотря на MINIMUM_ACTIVE_BALANCE_USD=10.0
- Защита не сработала

ГИПОТЕЗА:
- Текущий код использует: walletBalance - locked = free_balance
- НО это НЕ учитывает margin занятый в открытых позициях!
- Правильно использовать: totalAvailableBalance (на уровне аккаунта)

ТЕСТ ВЕРИФИЦИРУЕТ:
1. Какое значение возвращает текущий метод _get_free_balance_usdt()
2. Какое значение в totalAvailableBalance (правильное)
3. Разница между ними
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_bybit_balance_methods():
    """
    Test current vs correct balance calculation for Bybit UNIFIED
    """
    print("=" * 100)
    print("TEST: Bybit Free Balance Calculation - Current vs Correct")
    print("=" * 100)
    print()

    config = Config()
    bybit_config_obj = config.get_exchange_config('bybit')

    if not bybit_config_obj:
        print("❌ Bybit config not found")
        return

    # Convert ExchangeConfig to dict for ExchangeManager
    bybit_config = {
        'api_key': bybit_config_obj.api_key,
        'api_secret': bybit_config_obj.api_secret,
        'testnet': bybit_config_obj.testnet,
        'rate_limit': True
    }

    exchange = ExchangeManager(
        exchange_name='bybit',
        config=bybit_config,
        repository=None
    )

    try:
        print("📊 Fetching Bybit UNIFIED account balance...")
        print()

        # Get raw API response
        response = await exchange.exchange.privateGetV5AccountWalletBalance({
            'accountType': 'UNIFIED',
            'coin': 'USDT'
        })

        result = response.get('result', {})
        accounts = result.get('list', [])

        if not accounts:
            print("❌ No account data returned")
            return

        account = accounts[0]

        # ========================================
        # ACCOUNT-LEVEL BALANCES
        # ========================================
        print("─" * 100)
        print("ACCOUNT-LEVEL BALANCES (ПРАВИЛЬНЫЕ)")
        print("─" * 100)

        # Bybit API returns empty strings "" for some fields!
        total_equity = float(account.get('totalEquity', 0) or 0)
        total_wallet_balance = float(account.get('totalWalletBalance', 0) or 0)
        total_margin_balance = float(account.get('totalMarginBalance', 0) or 0)
        total_available_balance = float(account.get('totalAvailableBalance', 0) or 0)
        total_initial_margin = float(account.get('totalInitialMargin', 0) or 0)
        total_perp_upl = float(account.get('totalPerpUPL', 0) or 0)

        print(f"totalEquity             : ${total_equity:.4f} (total account value)")
        print(f"totalWalletBalance      : ${total_wallet_balance:.4f} (wallet balance)")
        print(f"totalMarginBalance      : ${total_margin_balance:.4f} (wallet + unrealized PnL)")
        print(f"totalInitialMargin      : ${total_initial_margin:.4f} (margin used by positions)")
        print(f"totalPerpUPL            : ${total_perp_upl:.4f} (unrealized PnL)")
        print()
        print(f"✅ totalAvailableBalance: ${total_available_balance:.4f} ← ЭТО ПРАВИЛЬНОЕ ЗНАЧЕНИЕ!")
        print(f"   Formula: totalMarginBalance - totalInitialMargin")
        print(f"   = ${total_margin_balance:.4f} - ${total_initial_margin:.4f} = ${total_available_balance:.4f}")
        print()

        # ========================================
        # COIN-LEVEL BALANCES (ТЕКУЩИЙ КОД)
        # ========================================
        print("─" * 100)
        print("COIN-LEVEL BALANCES (ТЕКУЩИЙ КОД - НЕПРАВИЛЬНО)")
        print("─" * 100)

        coins = account.get('coin', [])
        usdt_coin = None
        for coin_data in coins:
            if coin_data.get('coin') == 'USDT':
                usdt_coin = coin_data
                break

        if not usdt_coin:
            print("❌ USDT coin data not found")
            return

        wallet_balance = float(usdt_coin.get('walletBalance', 0) or 0)
        locked = float(usdt_coin.get('locked', 0) or 0)
        free_balance_wrong = wallet_balance - locked  # ТЕКУЩИЙ КОД

        print(f"walletBalance           : ${wallet_balance:.4f} (USDT wallet)")
        print(f"locked                  : ${locked:.4f} (locked by spot orders)")
        print()
        print(f"❌ free_balance (WRONG) : ${free_balance_wrong:.4f} ← ТЕКУЩИЙ КОД")
        print(f"   Formula (WRONG): walletBalance - locked")
        print(f"   = ${wallet_balance:.4f} - ${locked:.4f} = ${free_balance_wrong:.4f}")
        print()

        # ========================================
        # СРАВНЕНИЕ
        # ========================================
        print("=" * 100)
        print("CRITICAL COMPARISON")
        print("=" * 100)

        difference = free_balance_wrong - total_available_balance

        print(f"Current code returns    : ${free_balance_wrong:.4f}")
        print(f"Correct value should be : ${total_available_balance:.4f}")
        print(f"Difference              : ${difference:.4f}")
        print()

        if difference > 0.01:
            print(f"🚨 BUG CONFIRMED!")
            print(f"   Current code OVERESTIMATES free balance by ${difference:.4f}")
            print(f"   This causes MINIMUM_ACTIVE_BALANCE_USD check to fail!")
            print()
            print(f"   Example:")
            print(f"   - Position size: $6.00")
            print(f"   - Wrong free balance: ${free_balance_wrong:.4f}")
            print(f"   - Remaining after position: ${free_balance_wrong - 6.00:.4f}")
            print(f"   - MINIMUM_ACTIVE_BALANCE_USD: $10.00")
            print()
            print(f"   Check passes (WRONG): ${free_balance_wrong - 6.00:.4f} < $10.00? NO")
            print(f"   Check should fail (CORRECT): ${total_available_balance - 6.00:.4f} < $10.00? YES")
            print()
        else:
            print("✅ No significant difference detected")
            print()

        # ========================================
        # TEST CURRENT METHOD
        # ========================================
        print("=" * 100)
        print("TESTING CURRENT _get_free_balance_usdt() METHOD")
        print("=" * 100)

        current_method_result = await exchange._get_free_balance_usdt()
        print(f"_get_free_balance_usdt() returns: ${current_method_result:.4f}")
        print()

        if abs(current_method_result - free_balance_wrong) < 0.01:
            print("✅ Matches our calculation (walletBalance - locked)")
        else:
            print(f"⚠️ Unexpected value! Expected ${free_balance_wrong:.4f}")
        print()

        # ========================================
        # ADDITIONAL COIN INFO
        # ========================================
        print("=" * 100)
        print("ADDITIONAL USDT COIN INFORMATION")
        print("=" * 100)

        print(f"equity                  : ${float(usdt_coin.get('equity', 0) or 0):.4f}")
        print(f"usdValue                : ${float(usdt_coin.get('usdValue', 0) or 0):.4f}")
        print(f"unrealisedPnl           : ${float(usdt_coin.get('unrealisedPnl', 0) or 0):.4f}")
        print(f"cumRealisedPnl          : ${float(usdt_coin.get('cumRealisedPnl', 0) or 0):.4f}")
        print(f"totalOrderIM            : ${float(usdt_coin.get('totalOrderIM', 0) or 0):.4f}")
        print(f"totalPositionIM         : ${float(usdt_coin.get('totalPositionIM', 0) or 0):.4f}")
        print(f"totalPositionMM         : ${float(usdt_coin.get('totalPositionMM', 0) or 0):.4f}")
        print()

        # ========================================
        # RECOMMENDATION
        # ========================================
        print("=" * 100)
        print("🔧 RECOMMENDED FIX")
        print("=" * 100)
        print()
        print("Change _get_free_balance_usdt() for Bybit to use:")
        print()
        print("  ❌ OLD (WRONG):")
        print("     wallet_balance = coin['walletBalance']")
        print("     locked = coin['locked']")
        print("     return wallet_balance - locked")
        print()
        print("  ✅ NEW (CORRECT):")
        print("     return float(account.get('totalAvailableBalance', 0))")
        print()
        print("This will properly account for margin used in open positions!")
        print()

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(test_bybit_balance_methods())
