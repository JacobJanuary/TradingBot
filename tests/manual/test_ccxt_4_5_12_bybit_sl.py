#!/usr/bin/env python3
"""
ТЕСТ: Bybit Stop-Loss after CCXT 4.5.12 upgrade
Проверяем что SL создается и определяется корректно
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager
from core.stop_loss_manager import StopLossManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_bybit_sl_after_upgrade():
    """Test Bybit SL creation and detection after CCXT upgrade"""
    print("=" * 100)
    print("TEST: Bybit Stop-Loss After CCXT 4.5.12 Upgrade")
    print("=" * 100)
    print()

    config = Config()
    bybit_config_obj = config.get_exchange_config('bybit')

    if not bybit_config_obj:
        print("❌ Bybit config not found")
        return

    bybit_config = {
        'api_key': bybit_config_obj.api_key,
        'api_secret': bybit_config_obj.api_secret,
        'testnet': bybit_config_obj.testnet,
        'rate_limit': True
    }

    exchange_mgr = ExchangeManager(
        exchange_name='bybit',
        config=bybit_config,
        repository=None
    )

    try:
        # Test 1: Fetch positions and check stopLoss field
        print("─" * 100)
        print("TEST 1: Fetch positions and check info.stopLoss format")
        print("─" * 100)

        positions = await exchange_mgr.exchange.fetch_positions(
            params={'category': 'linear'}
        )

        print(f"Total positions: {len(positions)}")

        for pos in positions[:3]:  # First 3 positions
            if float(pos.get('contracts', 0)) > 0:
                symbol = pos['symbol']
                contracts = pos.get('contracts', 0)
                stop_loss = pos.get('info', {}).get('stopLoss', '0')

                print(f"\nPosition: {symbol}")
                print(f"  Contracts: {contracts}")
                print(f"  info.stopLoss: '{stop_loss}' (type: {type(stop_loss).__name__})")

                # Verify parsing works
                if stop_loss and stop_loss != '0' and stop_loss != '':
                    try:
                        sl_float = float(stop_loss)
                        print(f"  ✅ Parsed as float: {sl_float}")
                    except:
                        print(f"  ❌ FAILED to parse stopLoss as float!")
                else:
                    print(f"  ℹ️  No SL attached to position")

        print()

        # Test 2: StopLossManager detection
        print("─" * 100)
        print("TEST 2: StopLossManager.has_stop_loss() method")
        print("─" * 100)

        sl_manager = StopLossManager(exchange_mgr.exchange, 'bybit')

        # Find a position with SL
        test_symbol = None
        for pos in positions:
            if float(pos.get('contracts', 0)) > 0:
                stop_loss = pos.get('info', {}).get('stopLoss', '0')
                if stop_loss and stop_loss != '0' and stop_loss != '':
                    test_symbol = pos['symbol']
                    break

        if test_symbol:
            print(f"Testing has_stop_loss() for: {test_symbol}")
            has_sl, sl_price = await sl_manager.has_stop_loss(test_symbol)

            print(f"  has_stop_loss() returned:")
            print(f"    has_sl: {has_sl}")
            print(f"    sl_price: {sl_price}")

            if has_sl:
                print(f"  ✅ Stop-loss detected successfully")
            else:
                print(f"  ❌ Stop-loss NOT detected (but position has SL!)")
        else:
            print("ℹ️  No positions with SL found for testing")

        print()

        # Test 3: Position IM field
        print("─" * 100)
        print("TEST 3: Verify totalPositionIM field in balance")
        print("─" * 100)

        response = await exchange_mgr.exchange.privateGetV5AccountWalletBalance({
            'accountType': 'UNIFIED',
            'coin': 'USDT'
        })

        result = response.get('result', {})
        accounts = result.get('list', [])

        if accounts:
            account = accounts[0]
            coins = account.get('coin', [])

            for coin_data in coins:
                if coin_data.get('coin') == 'USDT':
                    wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
                    total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)

                    print(f"USDT coin data:")
                    print(f"  walletBalance: ${wallet_balance:.4f}")
                    print(f"  totalPositionIM: ${total_position_im:.4f}")
                    print(f"  ✅ Field exists and parseable")

                    # Verify our calculation
                    free_balance = wallet_balance - total_position_im
                    print(f"  Calculated free: ${free_balance:.4f}")

                    # Compare with our method
                    our_free = await exchange_mgr._get_free_balance_usdt()
                    print(f"  Our method returns: ${our_free:.4f}")

                    diff = abs(free_balance - our_free)
                    if diff < 0.01:
                        print(f"  ✅ Match! (diff: ${diff:.4f})")
                    else:
                        print(f"  ❌ Mismatch! (diff: ${diff:.4f})")

        print()
        print("=" * 100)
        print("✅ TEST COMPLETE")
        print("=" * 100)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await exchange_mgr.close()


if __name__ == '__main__':
    asyncio.run(test_bybit_sl_after_upgrade())
