#!/usr/bin/env python3
"""
Тест: проверка maxNotionalValue для нескольких символов
Цель: понять когда Binance возвращает 0 vs реальный лимит
"""
import asyncio
import os
from dotenv import load_dotenv
import ccxt.async_support as ccxt

load_dotenv()

async def test_multiple_symbols():
    """Test maxNotionalValue for multiple symbols"""

    exchange = ccxt.binanceusdm({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    })

    try:
        print("="*80)
        print("TEST: maxNotionalValue для разных символов")
        print("="*80)

        # Test symbols: some with open positions, some without
        test_symbols = [
            'NEWTUSDT',       # Filtered (maxNotional=0)
            '1000RATSUSDT',   # Successfully opened
            'FLRUSDT',        # Failed (no liquidity on Bybit, но проверим Binance)
            'BTCUSDT',        # Popular symbol
            'ETHUSDT',        # Popular symbol
        ]

        results = []

        for symbol_clean in test_symbols:
            try:
                print(f"\n{'='*60}")
                print(f"Symbol: {symbol_clean}")
                print(f"{'='*60}")

                position_risk = await exchange.fapiPrivateV2GetPositionRisk({
                    'symbol': symbol_clean
                })

                if isinstance(position_risk, list) and len(position_risk) > 0:
                    risk = position_risk[0]

                    max_notional_str = risk.get('maxNotionalValue', 'INF')
                    notional = risk.get('notional', '0')
                    position_amt = risk.get('positionAmt', '0')
                    leverage = risk.get('leverage', '0')

                    print(f"  maxNotionalValue: {max_notional_str}")
                    print(f"  notional:         {notional}")
                    print(f"  positionAmt:      {position_amt}")
                    print(f"  leverage:         {leverage}")

                    max_val = float(max_notional_str) if max_notional_str != 'INF' else float('inf')

                    results.append({
                        'symbol': symbol_clean,
                        'maxNotional': max_val,
                        'notional': float(notional),
                        'positionAmt': float(position_amt),
                        'has_position': float(position_amt) != 0
                    })

                    if max_val == 0:
                        print(f"  ⚠️ maxNotionalValue = 0 (has_position={float(position_amt) != 0})")
                    elif max_val == float('inf'):
                        print(f"  ✅ maxNotionalValue = INF")
                    else:
                        print(f"  ✅ maxNotionalValue = ${max_val:.2f}")

            except Exception as e:
                print(f"  🔴 ERROR: {e}")

        # Summary
        print(f"\n{'='*80}")
        print("SUMMARY:")
        print(f"{'='*80}")

        zero_notionals = [r for r in results if r['maxNotional'] == 0]
        non_zero_notionals = [r for r in results if r['maxNotional'] > 0 and r['maxNotional'] != float('inf')]

        print(f"\nСимволы с maxNotional = 0:")
        for r in zero_notionals:
            print(f"  - {r['symbol']}: position_amt={r['positionAmt']}, has_position={r['has_position']}")

        print(f"\nСимволы с maxNotional > 0:")
        for r in non_zero_notionals:
            print(f"  - {r['symbol']}: ${r['maxNotional']:.2f} (position_amt={r['positionAmt']})")

        print(f"\n{'='*80}")
        print("ВЫВОД:")
        print(f"{'='*80}")

        if all(r['maxNotional'] == 0 and not r['has_position'] for r in zero_notionals):
            print("✅ ГИПОТЕЗА ПОДТВЕРЖДЕНА:")
            print("   maxNotional = 0 для символов БЕЗ открытых позиций!")
            print("   Это означает что код ДОЛЖЕН игнорировать maxNotional=0")
            print("   и считать его как 'без ограничений'.")
        elif any(r['maxNotional'] == 0 and r['has_position'] for r in zero_notionals):
            print("❌ ГИПОТЕЗА ОПРОВЕРГНУТА:")
            print("   maxNotional = 0 даже при открытой позиции!")
        else:
            print("⚠️ НЕОДНОЗНАЧНО: нужно больше данных")

    except Exception as e:
        print(f"\n🔴 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(test_multiple_symbols())
