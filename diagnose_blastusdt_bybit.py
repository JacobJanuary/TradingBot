#!/usr/bin/env python3
"""
Deep diagnosis script for BLASTUSDT on Bybit Testnet
Checks all possible parameters to find the real issue
"""

import asyncio
import ccxt.async_support as ccxt
import os
import logging
from dotenv import load_dotenv
from decimal import Decimal

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


async def diagnose_blastusdt():
    """Comprehensive diagnosis of BLASTUSDT on Bybit"""

    # Initialize Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # USDT perpetual futures
            'adjustForTimeDifference': True
        }
    })

    # Set testnet mode
    testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
    if testnet:
        bybit.set_sandbox_mode(True)
        logger.info("🧪 Using Bybit TESTNET")
    else:
        logger.info("💰 Using Bybit MAINNET")

    symbol = 'BLASTUSDT'

    try:
        logger.info("=" * 80)
        logger.info("PHASE 1: MARKET AVAILABILITY CHECK")
        logger.info("=" * 80)

        # Load all markets
        logger.info("Loading markets...")
        markets = await bybit.load_markets()
        logger.info(f"✅ Total markets loaded: {len(markets)}")

        # Check if BLASTUSDT exists
        if symbol in markets:
            logger.info(f"✅ {symbol} FOUND in markets")
        else:
            logger.error(f"❌ {symbol} NOT FOUND in markets")
            logger.info(f"\nSearching for similar symbols...")
            similar = [s for s in markets.keys() if 'BLAST' in s.upper()]
            if similar:
                logger.info(f"Found similar: {similar}")
            else:
                logger.info("No similar symbols found")

            # List sample of available symbols
            usdt_symbols = [s for s in markets.keys() if 'USDT' in s][:10]
            logger.info(f"\nSample USDT symbols: {usdt_symbols}")
            return

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 2: MARKET INFO DETAILS")
        logger.info("=" * 80)

        market = markets[symbol]

        logger.info(f"\n📊 Market structure for {symbol}:")
        logger.info(f"  ID: {market.get('id')}")
        logger.info(f"  Symbol: {market.get('symbol')}")
        logger.info(f"  Base: {market.get('base')}")
        logger.info(f"  Quote: {market.get('quote')}")
        logger.info(f"  Active: {market.get('active')}")
        logger.info(f"  Type: {market.get('type')}")
        logger.info(f"  Spot: {market.get('spot')}")
        logger.info(f"  Margin: {market.get('margin')}")
        logger.info(f"  Future: {market.get('future')}")
        logger.info(f"  Swap: {market.get('swap')}")
        logger.info(f"  Option: {market.get('option')}")
        logger.info(f"  Contract: {market.get('contract')}")
        logger.info(f"  Linear: {market.get('linear')}")
        logger.info(f"  Inverse: {market.get('inverse')}")

        logger.info(f"\n💰 Precision:")
        precision = market.get('precision', {})
        logger.info(f"  Amount: {precision.get('amount')}")
        logger.info(f"  Price: {precision.get('price')}")
        logger.info(f"  Base: {precision.get('base')}")
        logger.info(f"  Quote: {precision.get('quote')}")

        logger.info(f"\n📏 Limits:")
        limits = market.get('limits', {})

        amount_limits = limits.get('amount', {})
        logger.info(f"  Amount:")
        logger.info(f"    Min: {amount_limits.get('min')}")
        logger.info(f"    Max: {amount_limits.get('max')}")

        price_limits = limits.get('price', {})
        logger.info(f"  Price:")
        logger.info(f"    Min: {price_limits.get('min')}")
        logger.info(f"    Max: {price_limits.get('max')}")

        cost_limits = limits.get('cost', {})
        logger.info(f"  Cost:")
        logger.info(f"    Min: {cost_limits.get('min')}")
        logger.info(f"    Max: {cost_limits.get('max')}")

        logger.info(f"\n🔧 Info field:")
        info = market.get('info', {})
        logger.info(f"  Lot size: {info.get('lotSizeFilter', {})}")
        logger.info(f"  Price filter: {info.get('priceFilter', {})}")
        logger.info(f"  Min notional: {info.get('minNotionalValue', 'N/A')}")
        logger.info(f"  Contract type: {info.get('contractType', 'N/A')}")
        logger.info(f"  Status: {info.get('status', 'N/A')}")

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 3: CURRENT MARKET DATA")
        logger.info("=" * 80)

        # Get ticker
        try:
            ticker = await bybit.fetch_ticker(symbol)
            logger.info(f"\n📈 Ticker for {symbol}:")
            logger.info(f"  Last price: {ticker.get('last')}")
            logger.info(f"  Bid: {ticker.get('bid')}")
            logger.info(f"  Ask: {ticker.get('ask')}")
            logger.info(f"  High 24h: {ticker.get('high')}")
            logger.info(f"  Low 24h: {ticker.get('low')}")
            logger.info(f"  Volume 24h: {ticker.get('volume')}")
            logger.info(f"  Quote volume: {ticker.get('quoteVolume')}")
        except Exception as e:
            logger.error(f"❌ Failed to fetch ticker: {e}")

        # Get orderbook
        try:
            orderbook = await bybit.fetch_order_book(symbol, limit=5)
            logger.info(f"\n📖 Order book (top 5):")
            logger.info(f"  Bids: {orderbook['bids'][:5]}")
            logger.info(f"  Asks: {orderbook['asks'][:5]}")
        except Exception as e:
            logger.error(f"❌ Failed to fetch orderbook: {e}")

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 4: ACCOUNT BALANCE CHECK")
        logger.info("=" * 80)

        try:
            balance = await bybit.fetch_balance()
            logger.info(f"\n💵 Account balance:")
            logger.info(f"  Total USDT: {balance.get('USDT', {}).get('total', 0)}")
            logger.info(f"  Free USDT: {balance.get('USDT', {}).get('free', 0)}")
            logger.info(f"  Used USDT: {balance.get('USDT', {}).get('used', 0)}")
        except Exception as e:
            logger.error(f"❌ Failed to fetch balance: {e}")

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 5: QUANTITY VALIDATION TESTS")
        logger.info("=" * 80)

        # Get minimum and test various quantities
        min_amount = amount_limits.get('min', 1)
        max_amount = amount_limits.get('max', float('inf'))
        current_price = ticker.get('last', 0.0025) if ticker else 0.0025

        logger.info(f"\n🧪 Testing different quantities:")
        logger.info(f"  Minimum allowed: {min_amount}")
        logger.info(f"  Maximum allowed: {max_amount}")
        logger.info(f"  Current price: {current_price}")

        # Test quantities
        test_quantities = [
            ('Original amount', 77820),
            ('Minimum amount', min_amount),
            ('Minimum * 2', min_amount * 2 if min_amount else 100),
            ('Minimum * 10', min_amount * 10 if min_amount else 1000),
            ('1000', 1000),
            ('10000', 10000),
            ('100000', 100000),
        ]

        for test_name, qty in test_quantities:
            # Apply precision if available
            amount_precision = precision.get('amount', 0)
            if amount_precision:
                qty = round(qty, int(amount_precision))

            # Calculate cost
            cost = qty * current_price
            min_cost = cost_limits.get('min', 0)

            logger.info(f"\n  {test_name}: {qty}")
            logger.info(f"    Quantity: {qty}")
            logger.info(f"    Cost (USDT): {cost:.2f}")

            # Validate
            issues = []

            if qty < min_amount:
                issues.append(f"Below min amount ({min_amount})")

            if qty > max_amount:
                issues.append(f"Above max amount ({max_amount})")

            if min_cost and cost < min_cost:
                issues.append(f"Below min cost ({min_cost} USDT)")

            if issues:
                logger.warning(f"    ⚠️ Issues: {', '.join(issues)}")
            else:
                logger.info(f"    ✅ Valid quantity")

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 6: POSITIONS CHECK")
        logger.info("=" * 80)

        try:
            positions = await bybit.fetch_positions([symbol])
            logger.info(f"\n📊 Current positions for {symbol}:")

            if positions:
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        logger.info(f"  Position found:")
                        logger.info(f"    Contracts: {pos.get('contracts')}")
                        logger.info(f"    Side: {pos.get('side')}")
                        logger.info(f"    Entry price: {pos.get('entryPrice')}")
                        logger.info(f"    Unrealized PnL: {pos.get('unrealizedPnl')}")
                    else:
                        logger.info(f"  No open position")
            else:
                logger.info(f"  No position data")
        except Exception as e:
            logger.error(f"❌ Failed to fetch positions: {e}")

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 7: DRY RUN ORDER TEST")
        logger.info("=" * 80)

        # Test with minimum valid amount
        test_amount = min_amount * 2 if min_amount else 100
        if amount_precision:
            test_amount = round(test_amount, int(amount_precision))

        logger.info(f"\n🧪 Testing order creation (DRY RUN):")
        logger.info(f"  Symbol: {symbol}")
        logger.info(f"  Side: SELL")
        logger.info(f"  Amount: {test_amount}")
        logger.info(f"  Type: MARKET")

        # Check what parameters would be sent
        logger.info(f"\n📤 Order parameters that would be sent:")
        logger.info(f"  symbol: {symbol}")
        logger.info(f"  type: market")
        logger.info(f"  side: sell")
        logger.info(f"  amount: {test_amount}")
        logger.info(f"  reduceOnly: False (opening position)")

        # Calculate required margin
        required_margin = test_amount * current_price
        logger.info(f"\n💰 Margin requirements:")
        logger.info(f"  Position value: {required_margin:.2f} USDT")
        logger.info(f"  Leverage: {info.get('leverage', 'N/A')}")

        logger.info("\n" + "=" * 80)
        logger.info("PHASE 8: ACTUAL ORDER TEST (VERY SMALL AMOUNT)")
        logger.info("=" * 80)

        # Try to place a very small order to see actual error
        logger.info(f"\n⚠️ Attempting to place REAL test order with minimum amount...")

        try:
            # Use absolute minimum
            tiny_amount = min_amount if min_amount else 1
            if amount_precision:
                tiny_amount = round(tiny_amount, int(amount_precision))

            logger.info(f"  Testing with amount: {tiny_amount}")

            # Try to create order
            test_order = await bybit.create_market_order(
                symbol=symbol,
                side='sell',
                amount=tiny_amount
            )

            logger.info(f"✅ Order created successfully!")
            logger.info(f"  Order ID: {test_order.get('id')}")
            logger.info(f"  Status: {test_order.get('status')}")
            logger.info(f"  Filled: {test_order.get('filled')}")

            # Immediately close the position
            logger.info(f"\n🔄 Closing test position...")
            close_order = await bybit.create_market_order(
                symbol=symbol,
                side='buy',
                amount=test_order.get('filled', tiny_amount),
                params={'reduceOnly': True}
            )
            logger.info(f"✅ Position closed: {close_order.get('id')}")

        except Exception as e:
            logger.error(f"❌ Order creation failed: {e}")
            logger.error(f"   Error type: {type(e).__name__}")

            # Parse error details
            error_str = str(e)
            logger.error(f"   Full error: {error_str}")

            # Try to extract Bybit error code
            if 'retCode' in error_str:
                logger.error(f"\n🔍 Bybit API Error Details:")
                logger.error(f"   This is the ACTUAL error from Bybit")

                # Common Bybit error codes
                error_codes = {
                    10001: "Parameter error - check symbol/amount/price format",
                    10003: "Invalid API key",
                    10004: "Invalid sign",
                    10005: "Permission denied",
                    10006: "Too many requests",
                    30031: "Insufficient balance",
                    30032: "Order quantity exceeds upper limit",
                    30033: "Order quantity is lower than the minimum",
                    30034: "Order price exceeds upper limit",
                    30035: "Order price is lower than the minimum",
                    110001: "Order does not exist",
                    110003: "Order price is out of permissible range",
                    110004: "Insufficient wallet balance",
                }

                for code, msg in error_codes.items():
                    if str(code) in error_str:
                        logger.error(f"   Likely code {code}: {msg}")

        logger.info("\n" + "=" * 80)
        logger.info("DIAGNOSIS SUMMARY")
        logger.info("=" * 80)

        logger.info(f"\n📋 Key findings:")
        logger.info(f"  1. Symbol availability: {'✅ AVAILABLE' if symbol in markets else '❌ NOT AVAILABLE'}")
        logger.info(f"  2. Market active: {market.get('active', False)}")
        logger.info(f"  3. Min amount: {min_amount}")
        logger.info(f"  4. Original amount (77820): {'✅ Valid' if 77820 >= min_amount else '❌ Below minimum'}")
        logger.info(f"  5. Min cost requirement: {cost_limits.get('min', 'N/A')}")

        cost_77820 = 77820 * current_price
        min_cost = cost_limits.get('min', 0)
        if min_cost and cost_77820 < min_cost:
            logger.warning(f"  ⚠️ ISSUE: Cost {cost_77820:.2f} USDT < minimum {min_cost} USDT")

        logger.info(f"\n💡 Recommendations:")
        logger.info(f"  - Use amount >= {min_amount}")
        if min_cost:
            min_qty_for_cost = min_cost / current_price if current_price else 0
            logger.info(f"  - For min cost, use amount >= {min_qty_for_cost:.0f}")

    except Exception as e:
        logger.error(f"Fatal error during diagnosis: {e}")
        import traceback
        logger.error(traceback.format_exc())

    finally:
        await bybit.close()
        logger.info("\n✅ Diagnosis complete")


if __name__ == "__main__":
    asyncio.run(diagnose_blastusdt())
