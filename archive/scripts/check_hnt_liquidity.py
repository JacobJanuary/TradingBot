#!/usr/bin/env python3
"""
Check HNT/USDT liquidity and orderbook on Bybit testnet
Verify hypothesis about illiquid pair
"""
import ccxt

def check_hnt_liquidity():
    print("=" * 80)
    print("🔍 CHECKING HNT/USDT LIQUIDITY ON BYBIT TESTNET")
    print("=" * 80)
    print()

    # Initialize Bybit testnet
    # Read from env directly
    import os
    from dotenv import load_dotenv
    load_dotenv()

    testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
    api_key = os.getenv('BYBIT_API_KEY', '')
    api_secret = os.getenv('BYBIT_API_SECRET', '')

    if not api_key or not api_secret:
        print("❌ Bybit API credentials not found in .env")
        return

    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'recvWindow': 10000
        }
    })

    if testnet:
        exchange.set_sandbox_mode(True)
        print("📍 Mode: TESTNET")
    else:
        print("📍 Mode: PRODUCTION")

    print()

    try:
        symbol = 'HNT/USDT:USDT'

        # 1. Check if market exists
        print("1️⃣ Checking market info...")
        try:
            markets = exchange.load_markets()
            if symbol in markets:
                market = markets[symbol]
                print(f"   ✅ Market exists")
                print(f"   Active: {market.get('active', 'unknown')}")
                print(f"   Limits: {market.get('limits', {})}")
            else:
                print(f"   ❌ Market {symbol} NOT FOUND")
                print(f"   Available markets: {len(markets)}")
                # Show similar symbols
                hnt_markets = [m for m in markets.keys() if 'HNT' in m]
                if hnt_markets:
                    print(f"   HNT markets found: {hnt_markets}")
                return
        except Exception as e:
            print(f"   ❌ Error loading markets: {e}")
            return

        # 2. Check ticker
        print()
        print("2️⃣ Checking ticker...")
        try:
            ticker = exchange.fetch_ticker(symbol)
            print(f"   Last price: {ticker.get('last')}")
            print(f"   Mark price: {ticker.get('info', {}).get('markPrice')}")
            print(f"   Bid: {ticker.get('bid')}")
            print(f"   Ask: {ticker.get('ask')}")
            print(f"   Volume 24h: {ticker.get('quoteVolume')}")
            print(f"   Timestamp: {ticker.get('timestamp')}")
        except Exception as e:
            print(f"   ❌ Error fetching ticker: {e}")

        # 3. Check orderbook
        print()
        print("3️⃣ Checking orderbook depth...")
        try:
            orderbook = exchange.fetch_order_book(symbol, limit=20)

            bids_count = len(orderbook.get('bids', []))
            asks_count = len(orderbook.get('asks', []))

            print(f"   Bids: {bids_count} levels")
            if bids_count > 0:
                top_bid = orderbook['bids'][0]
                print(f"   Top bid: {top_bid[0]} (qty: {top_bid[1]})")

            print(f"   Asks: {asks_count} levels")
            if asks_count > 0:
                top_ask = orderbook['asks'][0]
                print(f"   Top ask: {top_ask[0]} (qty: {top_ask[1]})")

            if bids_count == 0 and asks_count == 0:
                print(f"   ⚠️ EMPTY ORDERBOOK - NO LIQUIDITY!")
            elif bids_count < 5 or asks_count < 5:
                print(f"   ⚠️ VERY LOW LIQUIDITY")

            # Calculate spread
            if bids_count > 0 and asks_count > 0:
                spread = top_ask[0] - top_bid[0]
                spread_pct = (spread / top_bid[0]) * 100
                print(f"   Spread: {spread:.6f} ({spread_pct:.2f}%)")

                if spread_pct > 5:
                    print(f"   ⚠️ HUGE SPREAD - ILLIQUID MARKET!")
        except Exception as e:
            print(f"   ❌ Error fetching orderbook: {e}")

        # 4. Check open positions
        print()
        print("4️⃣ Checking open positions...")
        try:
            positions = exchange.fetch_positions([symbol])

            for pos in positions:
                if float(pos.get('contracts', 0)) > 0:
                    print(f"   Position found:")
                    print(f"     Symbol: {pos.get('symbol')}")
                    print(f"     Side: {pos.get('side')}")
                    print(f"     Size: {pos.get('contracts')}")
                    print(f"     Entry price: {pos.get('entryPrice')}")
                    print(f"     Mark price: {pos.get('markPrice')}")
                    print(f"     UnrealizedPnl: {pos.get('unrealizedPnl')}")

                    # Check position-attached SL
                    info = pos.get('info', {})
                    sl = info.get('stopLoss', '0')
                    tp = info.get('takeProfit', '0')
                    print(f"     Stop Loss (attached): {sl}")
                    print(f"     Take Profit (attached): {tp}")

                    # CRITICAL: Check what Bybit thinks is base price
                    entry = float(pos.get('entryPrice', 0))
                    mark = float(pos.get('markPrice', 0))

                    if mark > 0 and entry > 0:
                        drift = abs((mark - entry) / entry) * 100
                        print(f"     Drift from entry: {drift:.2f}%")

                        if drift > 50:
                            print(f"     ⚠️ HUGE PRICE DRIFT - SUSPICIOUS!")

            if not any(float(p.get('contracts', 0)) > 0 for p in positions):
                print(f"   No open positions")

        except Exception as e:
            print(f"   ❌ Error fetching positions: {e}")

        # 5. Try to fetch recent trades
        print()
        print("5️⃣ Checking recent trades...")
        try:
            trades = exchange.fetch_trades(symbol, limit=10)
            print(f"   Recent trades: {len(trades)}")

            if len(trades) == 0:
                print(f"   ⚠️ NO RECENT TRADES - DEAD MARKET!")
            else:
                for trade in trades[:3]:
                    print(f"     {trade.get('datetime')}: {trade.get('price')} (amount: {trade.get('amount')})")
        except Exception as e:
            print(f"   ❌ Error fetching trades: {e}")

        # 6. Check funding rate (for perpetual)
        print()
        print("6️⃣ Checking funding rate...")
        try:
            funding = exchange.fetch_funding_rate(symbol)
            print(f"   Funding rate: {funding.get('fundingRate')}")
            print(f"   Next funding: {funding.get('fundingDatetime')}")
        except Exception as e:
            print(f"   ⚠️ Could not fetch funding: {e}")

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        exchange.close()

    print()
    print("=" * 80)
    print("✅ LIQUIDITY CHECK COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    check_hnt_liquidity()
