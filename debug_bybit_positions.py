"""
Debug script to inspect Bybit testnet position data
Shows exactly what CCXT returns for positions
"""
import asyncio
import ccxt.async_support as ccxt
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def debug_bybit_positions():
    """Fetch and display Bybit positions with full details"""

    # Initialize Bybit exchange
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',
        }
    })

    if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
        exchange.set_sandbox_mode(True)
        print("🧪 Using Bybit TESTNET")
    else:
        print("🔴 Using Bybit MAINNET")

    try:
        # Fetch positions
        print("\n" + "="*80)
        print("FETCHING POSITIONS FROM BYBIT")
        print("="*80)

        positions = await exchange.fetch_positions(params={'category': 'linear'})

        print(f"\n📊 Total positions returned: {len(positions)}")

        # Filter for our problematic symbols
        problem_symbols = ['ORBSUSDT', 'BLASTUSDT', 'PYRUSDT']

        for pos in positions:
            symbol = pos.get('symbol', '').replace('/USDT:USDT', 'USDT')

            if symbol in problem_symbols:
                print("\n" + "-"*80)
                print(f"🔍 POSITION: {symbol}")
                print("-"*80)

                # CCXT normalized data
                print("\nCCXT Normalized Data:")
                print(f"  symbol: {pos.get('symbol')}")
                print(f"  contracts: {pos.get('contracts')}")
                print(f"  side: {pos.get('side')}")
                print(f"  notional: {pos.get('notional')}")
                print(f"  markPrice: {pos.get('markPrice')}")

                # Raw exchange data
                info = pos.get('info', {})
                print("\nRaw Exchange Data (info):")
                print(f"  symbol: {info.get('symbol')}")
                print(f"  size: {info.get('size')}")
                print(f"  side: {info.get('side')}")
                print(f"  positionValue: {info.get('positionValue')}")
                print(f"  leverage: {info.get('leverage')}")
                print(f"  positionIdx: {info.get('positionIdx')}")
                print(f"  avgPrice: {info.get('avgPrice')}")
                print(f"  markPrice: {info.get('markPrice')}")
                print(f"  liqPrice: {info.get('liqPrice')}")
                print(f"  createdTime: {info.get('createdTime')}")
                print(f"  updatedTime: {info.get('updatedTime')}")

                # Check if position is real
                print("\n✅ Phase 1 Filter Checks:")
                contracts = float(pos.get('contracts') or 0)
                size = float(info.get('size', 0))

                print(f"  contracts > 0: {abs(contracts) > 0} (value: {contracts})")
                print(f"  size > 0: {abs(size) > 0} (value: {size})")

                if abs(contracts) > 0 and abs(size) <= 0:
                    print("  ❌ WOULD BE FILTERED (stale CCXT data)")
                elif abs(contracts) > 0 and abs(size) > 0:
                    print("  ⚠️ WOULD PASS FILTER (but may be phantom!)")
                else:
                    print("  ✅ Would be filtered (contracts=0)")

                # Full info dict
                print("\n📄 Full info dict:")
                print(json.dumps(info, indent=2))

        # Check all positions with contracts > 0
        print("\n" + "="*80)
        print("ALL POSITIONS WITH CONTRACTS > 0")
        print("="*80)

        active_count = 0
        for pos in positions:
            contracts = float(pos.get('contracts') or 0)
            if abs(contracts) > 0:
                active_count += 1
                info = pos.get('info', {})
                size = float(info.get('size', 0))

                symbol = pos.get('symbol', '')

                status = "✅ REAL" if abs(size) > 0 else "❌ STALE"

                print(f"{status} | {symbol:20} | contracts={contracts:>10.4f} | size={size:>10}")

        print(f"\nTotal active positions: {active_count}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(debug_bybit_positions())
