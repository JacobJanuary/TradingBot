#!/usr/bin/env python3
"""
Тест: проверка maxNotionalValue для NEWTUSDT на Binance testnet
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
import ccxt.async_support as ccxt

load_dotenv()

async def test_max_notional():
    """Test maxNotionalValue for NEWTUSDT"""

    # Initialize Binance testnet
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
        print("TEST: NEWTUSDT maxNotionalValue на Binance Testnet")
        print("="*80)

        # Call position risk API
        symbol_clean = 'NEWTUSDT'  # Binance format

        print(f"\n1. Вызов fapiPrivateV2GetPositionRisk для {symbol_clean}...")
        position_risk = await exchange.fapiPrivateV2GetPositionRisk({
            'symbol': symbol_clean
        })

        print(f"\n2. Полученный response:")
        print(f"   Type: {type(position_risk)}")
        print(f"   Length: {len(position_risk) if isinstance(position_risk, list) else 'N/A'}")

        if isinstance(position_risk, list) and len(position_risk) > 0:
            risk = position_risk[0]
            print(f"\n3. Данные для {symbol_clean}:")
            print(f"   symbol: {risk.get('symbol')}")
            print(f"   maxNotionalValue: {risk.get('maxNotionalValue')}")
            print(f"   notional: {risk.get('notional')}")
            print(f"   positionAmt: {risk.get('positionAmt')}")
            print(f"   leverage: {risk.get('leverage')}")

            max_notional_str = risk.get('maxNotionalValue', 'INF')
            print(f"\n4. Анализ maxNotionalValue:")
            print(f"   Raw value: '{max_notional_str}'")
            print(f"   Type: {type(max_notional_str)}")

            if max_notional_str != 'INF':
                max_notional = float(max_notional_str)
                print(f"   Float value: ${max_notional:.2f}")

                if max_notional == 0:
                    print(f"\n🔴 ПРОБЛЕМА: maxNotionalValue = $0.00!")
                    print(f"   Это означает что для данного символа НЕТ лимита,")
                    print(f"   или символ НЕ доступен для торговли.")
                else:
                    print(f"\n✅ OK: maxNotionalValue = ${max_notional:.2f}")
            else:
                print(f"\n✅ OK: maxNotionalValue = INF (без ограничений)")

        else:
            print(f"\n🔴 ОШИБКА: Position risk пустой или не список!")
            print(f"   Response: {position_risk}")

        # Also check if symbol exists in markets
        print(f"\n5. Проверка символа в markets...")
        await exchange.load_markets()

        # Try different formats
        test_symbols = ['NEWT/USDT:USDT', 'NEWT/USDT', 'NEWTUSDT']

        for test_sym in test_symbols:
            if test_sym in exchange.markets:
                print(f"   ✅ {test_sym} найден в markets")
                market = exchange.markets[test_sym]
                print(f"      active: {market.get('active')}")
                print(f"      limits: {market.get('limits')}")
            else:
                print(f"   ❌ {test_sym} НЕ найден в markets")

    except Exception as e:
        print(f"\n🔴 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(test_max_notional())
