#!/usr/bin/env python3
"""
ТЕСТ: Binance Free Balance Investigation - Проверка правильности расчета

ЦЕЛЬ:
- Проверить что возвращает CCXT fetch_balance() для Binance Futures
- Проверить что возвращает нативный Binance API
- Сравнить 'free' balance с реальным доступным балансом
- Выявить учитывается ли margin занятый в позициях

ВОПРОСЫ:
1. Что возвращает balance['USDT']['free']?
2. Включает ли это margin в открытых позициях?
3. Есть ли более точное поле для доступного баланса?
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


async def test_binance_balance_methods():
    """
    Test Binance balance calculation methods
    """
    print("=" * 100)
    print("TEST: Binance Free Balance Investigation")
    print("=" * 100)
    print()

    config = Config()
    binance_config_obj = config.get_exchange_config('binance')

    if not binance_config_obj:
        print("❌ Binance config not found")
        return

    # Convert ExchangeConfig to dict for ExchangeManager
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
        print("📊 Fetching Binance Futures account data...")
        print()

        # ========================================
        # METHOD 1: CCXT fetch_balance()
        # ========================================
        print("─" * 100)
        print("METHOD 1: CCXT fetch_balance() - ТЕКУЩИЙ КОД")
        print("─" * 100)

        ccxt_balance = await exchange.exchange.fetch_balance()

        usdt_balance = ccxt_balance.get('USDT', {})
        ccxt_free = float(usdt_balance.get('free', 0) or 0)
        ccxt_used = float(usdt_balance.get('used', 0) or 0)
        ccxt_total = float(usdt_balance.get('total', 0) or 0)

        print(f"CCXT Balance['USDT']:")
        print(f"  free  : ${ccxt_free:.4f} ← ТЕКУЩИЙ КОД ИСПОЛЬЗУЕТ ЭТО")
        print(f"  used  : ${ccxt_used:.4f}")
        print(f"  total : ${ccxt_total:.4f}")
        print()

        # ========================================
        # METHOD 2: Native Binance API - Account Info V2
        # ========================================
        print("─" * 100)
        print("METHOD 2: Native Binance API - GET /fapi/v2/account")
        print("─" * 100)

        # Call native Binance Futures API
        account_info = await exchange.exchange.fapiPrivateV2GetAccount()

        # Extract balance fields
        total_wallet_balance = float(account_info.get('totalWalletBalance', 0) or 0)
        total_unrealized_profit = float(account_info.get('totalUnrealizedProfit', 0) or 0)
        total_margin_balance = float(account_info.get('totalMarginBalance', 0) or 0)
        total_initial_margin = float(account_info.get('totalInitialMargin', 0) or 0)
        total_maint_margin = float(account_info.get('totalMaintMargin', 0) or 0)
        total_cross_wallet_balance = float(account_info.get('totalCrossWalletBalance', 0) or 0)
        total_cross_un_pnl = float(account_info.get('totalCrossUnPnl', 0) or 0)
        available_balance = float(account_info.get('availableBalance', 0) or 0)
        max_withdraw_amount = float(account_info.get('maxWithdrawAmount', 0) or 0)

        print("Native API Account-Level Fields:")
        print(f"  totalWalletBalance      : ${total_wallet_balance:.4f}")
        print(f"  totalUnrealizedProfit   : ${total_unrealized_profit:.4f}")
        print(f"  totalMarginBalance      : ${total_margin_balance:.4f}")
        print(f"  totalInitialMargin      : ${total_initial_margin:.4f} (margin used in positions)")
        print(f"  totalMaintMargin        : ${total_maint_margin:.4f}")
        print(f"  totalCrossWalletBalance : ${total_cross_wallet_balance:.4f}")
        print(f"  totalCrossUnPnl         : ${total_cross_un_pnl:.4f}")
        print()
        print(f"  ✅ availableBalance     : ${available_balance:.4f} ← ДОСТУПНО ДЛЯ НОВЫХ ПОЗИЦИЙ")
        print(f"  ✅ maxWithdrawAmount    : ${max_withdraw_amount:.4f} ← МОЖНО ВЫВЕСТИ")
        print()

        # Calculate manually
        calculated_available = total_margin_balance - total_initial_margin
        print(f"  Manual calculation:")
        print(f"    totalMarginBalance - totalInitialMargin")
        print(f"    = ${total_margin_balance:.4f} - ${total_initial_margin:.4f}")
        print(f"    = ${calculated_available:.4f}")
        print()

        # ========================================
        # METHOD 3: Check Assets array
        # ========================================
        print("─" * 100)
        print("METHOD 3: Assets Array (USDT specific)")
        print("─" * 100)

        assets = account_info.get('assets', [])
        usdt_asset = None
        for asset in assets:
            if asset.get('asset') == 'USDT':
                usdt_asset = asset
                break

        if usdt_asset:
            asset_wallet_balance = float(usdt_asset.get('walletBalance', 0) or 0)
            asset_unrealized_profit = float(usdt_asset.get('unrealizedProfit', 0) or 0)
            asset_margin_balance = float(usdt_asset.get('marginBalance', 0) or 0)
            asset_maint_margin = float(usdt_asset.get('maintMargin', 0) or 0)
            asset_initial_margin = float(usdt_asset.get('initialMargin', 0) or 0)
            asset_position_initial_margin = float(usdt_asset.get('positionInitialMargin', 0) or 0)
            asset_open_order_initial_margin = float(usdt_asset.get('openOrderInitialMargin', 0) or 0)
            asset_max_withdraw_amount = float(usdt_asset.get('maxWithdrawAmount', 0) or 0)
            asset_cross_wallet_balance = float(usdt_asset.get('crossWalletBalance', 0) or 0)
            asset_cross_un_pnl = float(usdt_asset.get('crossUnPnl', 0) or 0)
            asset_available_balance = float(usdt_asset.get('availableBalance', 0) or 0)

            print("USDT Asset Fields:")
            print(f"  walletBalance            : ${asset_wallet_balance:.4f}")
            print(f"  unrealizedProfit         : ${asset_unrealized_profit:.4f}")
            print(f"  marginBalance            : ${asset_margin_balance:.4f}")
            print(f"  initialMargin            : ${asset_initial_margin:.4f}")
            print(f"  positionInitialMargin    : ${asset_position_initial_margin:.4f}")
            print(f"  openOrderInitialMargin   : ${asset_open_order_initial_margin:.4f}")
            print(f"  maintMargin              : ${asset_maint_margin:.4f}")
            print(f"  crossWalletBalance       : ${asset_cross_wallet_balance:.4f}")
            print(f"  crossUnPnl               : ${asset_cross_un_pnl:.4f}")
            print()
            print(f"  ✅ availableBalance      : ${asset_available_balance:.4f}")
            print(f"  ✅ maxWithdrawAmount     : ${asset_max_withdraw_amount:.4f}")
            print()
        else:
            print("❌ USDT asset not found in assets array")
            print()

        # ========================================
        # CRITICAL COMPARISON
        # ========================================
        print("=" * 100)
        print("CRITICAL COMPARISON")
        print("=" * 100)

        print(f"Current code uses (CCXT)    : ${ccxt_free:.4f}")
        print(f"Native API availableBalance : ${available_balance:.4f}")
        print(f"Difference                  : ${ccxt_free - available_balance:.4f}")
        print()

        if abs(ccxt_free - available_balance) > 0.01:
            print("🚨 POTENTIAL ISSUE DETECTED!")
            print(f"   CCXT 'free' differs from availableBalance by ${abs(ccxt_free - available_balance):.4f}")
            print()

            if ccxt_free > available_balance:
                print(f"   Current code OVERESTIMATES by ${ccxt_free - available_balance:.4f}")
                print(f"   This could cause MINIMUM_ACTIVE_BALANCE_USD check to fail!")
            else:
                print(f"   Current code UNDERESTIMATES by ${available_balance - ccxt_free:.4f}")
                print(f"   This is safe but might reject valid positions")
            print()
        else:
            print("✅ CCXT 'free' matches availableBalance closely")
            print("   Current implementation appears correct for Binance")
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

        if abs(current_method_result - ccxt_free) < 0.01:
            print("✅ Matches CCXT fetch_balance()['USDT']['free']")
        else:
            print(f"⚠️ Unexpected! Expected ${ccxt_free:.4f}")
        print()

        if abs(current_method_result - available_balance) < 0.01:
            print("✅ Matches native API availableBalance")
            print("   Current implementation is CORRECT")
        else:
            print(f"❌ Does NOT match availableBalance (diff: ${abs(current_method_result - available_balance):.4f})")
            print("   Current implementation may be INCORRECT")
        print()

        # ========================================
        # CHECK POSITIONS
        # ========================================
        print("=" * 100)
        print("POSITION INFORMATION")
        print("=" * 100)

        positions = account_info.get('positions', [])
        open_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]

        print(f"Total positions: {len(positions)}")
        print(f"Open positions: {len(open_positions)}")
        print()

        if open_positions:
            print("Open positions summary:")
            total_position_notional = 0
            for pos in open_positions[:5]:  # Show first 5
                symbol = pos.get('symbol')
                position_amt = float(pos.get('positionAmt', 0))
                entry_price = float(pos.get('entryPrice', 0))
                notional = float(pos.get('notional', 0))
                unrealized_pnl = float(pos.get('unrealizedProfit', 0))

                total_position_notional += abs(notional)

                print(f"  {symbol}: amt={position_amt}, notional=${notional:.2f}, PnL=${unrealized_pnl:.2f}")

            if len(open_positions) > 5:
                print(f"  ... and {len(open_positions) - 5} more positions")

            print()
            print(f"Total notional in positions: ${total_position_notional:.2f}")
            print()

        # ========================================
        # RECOMMENDATION
        # ========================================
        print("=" * 100)
        print("🔧 RECOMMENDATION")
        print("=" * 100)
        print()

        if abs(ccxt_free - available_balance) > 0.01:
            print("⚠️ CCXT fetch_balance() may not be accurate for Binance Futures")
            print()
            print("Consider changing _get_free_balance_usdt() for Binance to use:")
            print()
            print("  Current (may be wrong):")
            print("    balance = await self.exchange.fetch_balance()")
            print("    return float(balance.get('USDT', {}).get('free', 0) or 0)")
            print()
            print("  Recommended (native API):")
            print("    account = await self.exchange.fapiPrivateV2GetAccount()")
            print("    return float(account.get('availableBalance', 0) or 0)")
            print()
        else:
            print("✅ Current CCXT implementation appears correct")
            print("   No changes needed for Binance")
            print()

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(test_binance_balance_methods())
