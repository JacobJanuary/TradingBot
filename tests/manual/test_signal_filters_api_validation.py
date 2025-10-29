"""
Test script to validate API methods for new signal filters.

Tests three new filter criteria:
1. Open Interest >= 1,000,000 USDT
2. 1h Trading Volume >= 50,000 USDT
3. 5-minute price change <= 4% (for BUY: price didn't rise >4%, for SELL: price didn't fall >4%)

CRITICAL: This is a TESTING script only - does NOT modify bot code!

Usage:
    python tests/manual/test_signal_filters_api_validation.py
"""

import asyncio
import csv
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import ccxt.async_support as ccxt

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class SignalFilterAPITester:
    """Tests API methods needed for new signal filters."""

    def __init__(self):
        """Initialize exchange connections."""
        self.binance = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.bybit = ccxt.bybit({
            'enableRateLimit': True,
            'options': {'defaultType': 'linear'}
        })

        # Filter thresholds (matching requirements)
        self.MIN_OI_USDT = 1_000_000  # 1 million USDT
        self.MIN_VOLUME_1H_USDT = 50_000  # 50k USDT
        self.MAX_PRICE_CHANGE_5MIN_PERCENT = 4.0  # 4%

        # Test statistics
        self.stats = {
            'total_tested': 0,
            'oi_api_success': 0,
            'oi_api_failed': 0,
            'volume_api_success': 0,
            'volume_api_failed': 0,
            'price_5min_api_success': 0,
            'price_5min_api_failed': 0,
            'would_pass_oi_filter': 0,
            'would_pass_volume_filter': 0,
            'would_pass_price_change_filter': 0,
            'would_pass_all_filters': 0,
            'would_be_filtered_out': 0
        }

    async def close(self):
        """Close exchange connections."""
        await self.binance.close()
        await self.bybit.close()

    def normalize_symbol_for_exchange(self, symbol: str, exchange: str) -> str:
        """Normalize symbol for specific exchange."""
        if exchange == 'binance':
            return symbol  # BTCUSDT
        elif exchange == 'bybit':
            base = symbol.replace('USDT', '')
            return f"{base}/USDT:USDT"  # BTC/USDT:USDT
        return symbol

    async def test_fetch_open_interest(
        self,
        exchange_name: str,
        symbol: str
    ) -> Tuple[Optional[float], bool, str]:
        """
        Test Method 1: fetch_open_interest()

        Returns:
            (oi_value_usdt, success, method_used)
        """
        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Method 1: Try fetch_open_interest
            try:
                oi_data = await exchange.fetch_open_interest(normalized_symbol)

                if oi_data:
                    # Try openInterestValue (already in USDT)
                    if 'openInterestValue' in oi_data and oi_data['openInterestValue'] is not None:
                        return float(oi_data['openInterestValue']), True, 'fetch_open_interest.openInterestValue'

                    # Try quoteVolume
                    if 'quoteVolume' in oi_data and oi_data['quoteVolume'] is not None:
                        return float(oi_data['quoteVolume']), True, 'fetch_open_interest.quoteVolume'

                    # Try openInterestAmount (need to convert)
                    if 'openInterestAmount' in oi_data and oi_data['openInterestAmount'] is not None:
                        amount = float(oi_data['openInterestAmount'])

                        # Try to get price from info
                        if 'info' in oi_data and oi_data['info']:
                            mark_price = oi_data['info'].get('markPrice') or oi_data['info'].get('lastPrice')
                            if mark_price:
                                return amount * float(mark_price), True, 'fetch_open_interest.openInterestAmount*markPrice'

                        # Fallback: fetch ticker for price
                        ticker = await exchange.fetch_ticker(normalized_symbol)
                        if ticker and ticker.get('last'):
                            return amount * float(ticker['last']), True, 'fetch_open_interest.openInterestAmount*ticker'
            except Exception as e:
                pass  # Try method 2

            # Method 2: Try fetch_ticker (some exchanges include OI)
            try:
                ticker = await exchange.fetch_ticker(normalized_symbol)
                if ticker:
                    info = ticker.get('info', {})

                    # Binance: openInterest in contracts
                    if 'openInterest' in info:
                        oi_amount = float(info['openInterest'])
                        if ticker.get('last'):
                            return oi_amount * float(ticker['last']), True, 'fetch_ticker.openInterest*last'

                    # Bybit: openInterestValue in USDT
                    if 'openInterestValue' in info:
                        return float(info['openInterestValue']), True, 'fetch_ticker.openInterestValue'
            except Exception:
                pass

            return None, False, 'all_methods_failed'

        except Exception as e:
            return None, False, f'exception:{str(e)[:50]}'

    async def test_fetch_1h_volume(
        self,
        exchange_name: str,
        symbol: str,
        signal_timestamp: datetime
    ) -> Tuple[Optional[float], bool, str]:
        """
        Test Method 2: fetch_ohlcv() for 1h volume

        Returns:
            (volume_usdt, success, method_used)
        """
        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Round timestamp to hour boundary
            hour_start = signal_timestamp.replace(minute=0, second=0, microsecond=0)
            ts_ms = int(hour_start.timestamp() * 1000)

            # Fetch 1h candle
            ohlcv = await exchange.fetch_ohlcv(
                normalized_symbol,
                timeframe='1h',
                since=ts_ms,
                limit=1
            )

            if not ohlcv or len(ohlcv) == 0:
                return None, False, 'no_ohlcv_data'

            candle = ohlcv[0]
            # [timestamp, open, high, low, close, volume]

            base_volume = candle[5]
            close_price = candle[4]

            if base_volume is None or close_price is None or close_price <= 0:
                return None, False, 'invalid_candle_data'

            volume_usdt = base_volume * close_price

            return volume_usdt, True, 'fetch_ohlcv_1h'

        except Exception as e:
            return None, False, f'exception:{str(e)[:50]}'

    async def test_fetch_price_5min_before(
        self,
        exchange_name: str,
        symbol: str,
        signal_timestamp: datetime
    ) -> Tuple[Optional[float], Optional[float], bool, str]:
        """
        Test Method 3: fetch_ohlcv() for 5-minute-before price

        Returns:
            (price_at_signal, price_5min_before, success, method_used)
        """
        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Get price at signal timestamp
            ts_signal_ms = int(signal_timestamp.timestamp() * 1000)
            ohlcv_signal = await exchange.fetch_ohlcv(
                normalized_symbol,
                timeframe='1m',
                since=ts_signal_ms - (10 * 60 * 1000),
                limit=15
            )

            if not ohlcv_signal or len(ohlcv_signal) == 0:
                return None, None, False, 'no_signal_price'

            # Find closest candle to signal timestamp
            closest_signal = min(ohlcv_signal, key=lambda x: abs(x[0] - ts_signal_ms))
            price_at_signal = closest_signal[4]  # close price

            # Get price 5 minutes before
            ts_5min_before = signal_timestamp - timedelta(minutes=5)
            ts_5min_ms = int(ts_5min_before.timestamp() * 1000)

            ohlcv_before = await exchange.fetch_ohlcv(
                normalized_symbol,
                timeframe='1m',
                since=ts_5min_ms - (5 * 60 * 1000),
                limit=10
            )

            if not ohlcv_before or len(ohlcv_before) == 0:
                return price_at_signal, None, False, 'no_5min_before_price'

            # Find closest candle to 5min before timestamp
            closest_before = min(ohlcv_before, key=lambda x: abs(x[0] - ts_5min_ms))
            price_5min_before = closest_before[4]  # close price

            if price_at_signal and price_5min_before and price_5min_before > 0:
                return price_at_signal, price_5min_before, True, 'fetch_ohlcv_1m'
            else:
                return price_at_signal, price_5min_before, False, 'invalid_prices'

        except Exception as e:
            return None, None, False, f'exception:{str(e)[:50]}'

    def check_filters(
        self,
        signal: Dict,
        oi_usdt: Optional[float],
        volume_1h_usdt: Optional[float],
        price_at_signal: Optional[float],
        price_5min_before: Optional[float]
    ) -> Dict:
        """
        Check if signal would pass all three new filters.

        Returns:
            Dict with filter results
        """
        direction = signal.get('direction', signal.get('recommended_action', 'BUY'))

        result = {
            'pass_oi_filter': False,
            'pass_volume_filter': False,
            'pass_price_change_filter': False,
            'pass_all_filters': False,
            'oi_filter_reason': '',
            'volume_filter_reason': '',
            'price_change_filter_reason': '',
            'price_change_percent': None
        }

        # Filter 1: Open Interest >= 1M USDT
        if oi_usdt is None:
            result['pass_oi_filter'] = False
            result['oi_filter_reason'] = 'OI data not available'
        elif oi_usdt >= self.MIN_OI_USDT:
            result['pass_oi_filter'] = True
            result['oi_filter_reason'] = f'OI ${oi_usdt:,.0f} >= ${self.MIN_OI_USDT:,}'
        else:
            result['pass_oi_filter'] = False
            result['oi_filter_reason'] = f'OI ${oi_usdt:,.0f} < ${self.MIN_OI_USDT:,}'

        # Filter 2: 1h Volume >= 50k USDT
        if volume_1h_usdt is None:
            result['pass_volume_filter'] = False
            result['volume_filter_reason'] = 'Volume data not available'
        elif volume_1h_usdt >= self.MIN_VOLUME_1H_USDT:
            result['pass_volume_filter'] = True
            result['volume_filter_reason'] = f'Volume ${volume_1h_usdt:,.0f} >= ${self.MIN_VOLUME_1H_USDT:,}'
        else:
            result['pass_volume_filter'] = False
            result['volume_filter_reason'] = f'Volume ${volume_1h_usdt:,.0f} < ${self.MIN_VOLUME_1H_USDT:,}'

        # Filter 3: Price change <= 4%
        if price_at_signal is None or price_5min_before is None or price_5min_before <= 0:
            result['pass_price_change_filter'] = False
            result['price_change_filter_reason'] = 'Price data not available'
        else:
            price_change_percent = ((price_at_signal - price_5min_before) / price_5min_before) * 100
            result['price_change_percent'] = price_change_percent

            # For BUY: reject if price rose >4% (buying at top)
            # For SELL: reject if price fell >4% (selling at bottom)
            if direction == 'BUY':
                if price_change_percent > self.MAX_PRICE_CHANGE_5MIN_PERCENT:
                    result['pass_price_change_filter'] = False
                    result['price_change_filter_reason'] = f'BUY: price rose {price_change_percent:+.2f}% > {self.MAX_PRICE_CHANGE_5MIN_PERCENT}%'
                else:
                    result['pass_price_change_filter'] = True
                    result['price_change_filter_reason'] = f'BUY: price change {price_change_percent:+.2f}% <= {self.MAX_PRICE_CHANGE_5MIN_PERCENT}%'
            elif direction == 'SELL':
                if price_change_percent < -self.MAX_PRICE_CHANGE_5MIN_PERCENT:
                    result['pass_price_change_filter'] = False
                    result['price_change_filter_reason'] = f'SELL: price fell {price_change_percent:+.2f}% < -{self.MAX_PRICE_CHANGE_5MIN_PERCENT}%'
                else:
                    result['pass_price_change_filter'] = True
                    result['price_change_filter_reason'] = f'SELL: price change {price_change_percent:+.2f}% >= -{self.MAX_PRICE_CHANGE_5MIN_PERCENT}%'

        # All filters must pass
        result['pass_all_filters'] = (
            result['pass_oi_filter'] and
            result['pass_volume_filter'] and
            result['pass_price_change_filter']
        )

        return result

    async def test_signal(self, signal: Dict) -> Dict:
        """Test all API methods and filters for a single signal."""
        symbol = signal.get('pair_symbol', signal.get('symbol', ''))
        exchange_id = int(signal.get('exchange_id', 1))
        exchange_name = 'binance' if exchange_id == 1 else 'bybit'
        direction = signal.get('recommended_action', 'BUY')

        # Parse timestamp (handle timezone)
        timestamp_str = signal.get('timestamp', signal.get('created_at', ''))
        signal_timestamp = datetime.fromisoformat(timestamp_str.replace('+00', '+00:00'))

        print(f"\n{'='*80}")
        print(f"Testing: {symbol} ({direction}) on {exchange_name}")
        print(f"Signal time: {signal_timestamp}")
        print(f"{'='*80}")

        result = {
            'symbol': symbol,
            'exchange': exchange_name,
            'direction': direction,
            'timestamp': signal_timestamp,
            'oi_usdt': None,
            'oi_success': False,
            'oi_method': '',
            'volume_1h_usdt': None,
            'volume_success': False,
            'volume_method': '',
            'price_at_signal': None,
            'price_5min_before': None,
            'price_success': False,
            'price_method': '',
            'filter_results': {}
        }

        # Test 1: Open Interest
        print("\n🔍 Test 1: Fetching Open Interest...")
        oi_usdt, oi_success, oi_method = await self.test_fetch_open_interest(exchange_name, symbol)
        result['oi_usdt'] = oi_usdt
        result['oi_success'] = oi_success
        result['oi_method'] = oi_method

        if oi_success:
            print(f"  ✅ SUCCESS: OI = ${oi_usdt:,.2f} USDT (method: {oi_method})")
            self.stats['oi_api_success'] += 1
        else:
            print(f"  ❌ FAILED: {oi_method}")
            self.stats['oi_api_failed'] += 1

        # Small delay for rate limiting
        await asyncio.sleep(0.3)

        # Test 2: 1h Volume
        print("\n🔍 Test 2: Fetching 1h Trading Volume...")
        volume_1h_usdt, volume_success, volume_method = await self.test_fetch_1h_volume(
            exchange_name, symbol, signal_timestamp
        )
        result['volume_1h_usdt'] = volume_1h_usdt
        result['volume_success'] = volume_success
        result['volume_method'] = volume_method

        if volume_success:
            print(f"  ✅ SUCCESS: Volume = ${volume_1h_usdt:,.2f} USDT (method: {volume_method})")
            self.stats['volume_api_success'] += 1
        else:
            print(f"  ❌ FAILED: {volume_method}")
            self.stats['volume_api_failed'] += 1

        # Small delay for rate limiting
        await asyncio.sleep(0.3)

        # Test 3: 5-minute price change
        print("\n🔍 Test 3: Fetching 5-minute price change...")
        price_at_signal, price_5min_before, price_success, price_method = await self.test_fetch_price_5min_before(
            exchange_name, symbol, signal_timestamp
        )
        result['price_at_signal'] = price_at_signal
        result['price_5min_before'] = price_5min_before
        result['price_success'] = price_success
        result['price_method'] = price_method

        if price_success:
            price_change_pct = ((price_at_signal - price_5min_before) / price_5min_before) * 100
            print(f"  ✅ SUCCESS: Price changed {price_change_pct:+.2f}% (method: {price_method})")
            print(f"     Price 5min before: ${price_5min_before:.8f}")
            print(f"     Price at signal:   ${price_at_signal:.8f}")
            self.stats['price_5min_api_success'] += 1
        else:
            print(f"  ❌ FAILED: {price_method}")
            self.stats['price_5min_api_failed'] += 1

        # Apply filters
        print("\n📊 Filter Analysis:")
        filter_results = self.check_filters(
            signal, oi_usdt, volume_1h_usdt, price_at_signal, price_5min_before
        )
        result['filter_results'] = filter_results

        # Update statistics
        if filter_results['pass_oi_filter']:
            self.stats['would_pass_oi_filter'] += 1
        if filter_results['pass_volume_filter']:
            self.stats['would_pass_volume_filter'] += 1
        if filter_results['pass_price_change_filter']:
            self.stats['would_pass_price_change_filter'] += 1
        if filter_results['pass_all_filters']:
            self.stats['would_pass_all_filters'] += 1
        else:
            self.stats['would_be_filtered_out'] += 1

        # Print filter results
        oi_status = "✅ PASS" if filter_results['pass_oi_filter'] else "❌ FAIL"
        vol_status = "✅ PASS" if filter_results['pass_volume_filter'] else "❌ FAIL"
        price_status = "✅ PASS" if filter_results['pass_price_change_filter'] else "❌ FAIL"

        print(f"  Filter 1 (OI >= 1M USDT):         {oi_status} - {filter_results['oi_filter_reason']}")
        print(f"  Filter 2 (Volume >= 50k USDT):    {vol_status} - {filter_results['volume_filter_reason']}")
        print(f"  Filter 3 (Price change <= 4%):    {price_status} - {filter_results['price_change_filter_reason']}")

        if filter_results['pass_all_filters']:
            print(f"\n  ✅✅✅ SIGNAL WOULD PASS ALL FILTERS ✅✅✅")
        else:
            print(f"\n  ❌ SIGNAL WOULD BE FILTERED OUT")

        return result

    async def run_tests(self, csv_path: str, limit: Optional[int] = None):
        """Run tests on signals from CSV file."""
        # Read signals from CSV
        signals = []
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                signals.append(row)
                if limit and len(signals) >= limit:
                    break

        print(f"\n{'='*80}")
        print(f"SIGNAL FILTER API VALIDATION TEST")
        print(f"{'='*80}")
        print(f"Total signals to test: {len(signals)}")
        print(f"Filter thresholds:")
        print(f"  - Minimum OI: ${self.MIN_OI_USDT:,} USDT")
        print(f"  - Minimum 1h Volume: ${self.MIN_VOLUME_1H_USDT:,} USDT")
        print(f"  - Maximum 5min price change: {self.MAX_PRICE_CHANGE_5MIN_PERCENT}%")
        print(f"{'='*80}")

        results = []
        for i, signal in enumerate(signals, 1):
            print(f"\n\n[{i}/{len(signals)}] Testing signal...")
            self.stats['total_tested'] += 1

            result = await self.test_signal(signal)
            results.append(result)

            # Delay between signals to respect rate limits
            await asyncio.sleep(0.5)

        # Print final statistics
        self.print_statistics()

        return results

    def print_statistics(self):
        """Print test statistics."""
        print(f"\n\n{'='*80}")
        print(f"TEST STATISTICS")
        print(f"{'='*80}")
        print(f"Total signals tested: {self.stats['total_tested']}")
        print(f"\nAPI Method Success Rates:")
        print(f"  Open Interest API:")
        print(f"    ✅ Success: {self.stats['oi_api_success']} ({self.stats['oi_api_success']/self.stats['total_tested']*100:.1f}%)")
        print(f"    ❌ Failed:  {self.stats['oi_api_failed']} ({self.stats['oi_api_failed']/self.stats['total_tested']*100:.1f}%)")
        print(f"  1h Volume API:")
        print(f"    ✅ Success: {self.stats['volume_api_success']} ({self.stats['volume_api_success']/self.stats['total_tested']*100:.1f}%)")
        print(f"    ❌ Failed:  {self.stats['volume_api_failed']} ({self.stats['volume_api_failed']/self.stats['total_tested']*100:.1f}%)")
        print(f"  5min Price API:")
        print(f"    ✅ Success: {self.stats['price_5min_api_success']} ({self.stats['price_5min_api_success']/self.stats['total_tested']*100:.1f}%)")
        print(f"    ❌ Failed:  {self.stats['price_5min_api_failed']} ({self.stats['price_5min_api_failed']/self.stats['total_tested']*100:.1f}%)")

        print(f"\nFilter Pass Rates (individual):")
        print(f"  OI Filter (>= 1M USDT):            {self.stats['would_pass_oi_filter']} passed ({self.stats['would_pass_oi_filter']/self.stats['total_tested']*100:.1f}%)")
        print(f"  Volume Filter (>= 50k USDT):       {self.stats['would_pass_volume_filter']} passed ({self.stats['would_pass_volume_filter']/self.stats['total_tested']*100:.1f}%)")
        print(f"  Price Change Filter (<= 4%):       {self.stats['would_pass_price_change_filter']} passed ({self.stats['would_pass_price_change_filter']/self.stats['total_tested']*100:.1f}%)")

        print(f"\nOverall Filter Results:")
        print(f"  ✅ Would PASS all filters:         {self.stats['would_pass_all_filters']} ({self.stats['would_pass_all_filters']/self.stats['total_tested']*100:.1f}%)")
        print(f"  ❌ Would be FILTERED OUT:          {self.stats['would_be_filtered_out']} ({self.stats['would_be_filtered_out']/self.stats['total_tested']*100:.1f}%)")
        print(f"{'='*80}")


async def main():
    """Main entry point."""
    csv_path = '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/data-1761678817380.csv'

    if not Path(csv_path).exists():
        print(f"❌ Error: CSV file not found: {csv_path}")
        sys.exit(1)

    tester = SignalFilterAPITester()

    try:
        # Run tests on ALL signals from CSV (no limit)
        await tester.run_tests(csv_path, limit=None)

    finally:
        await tester.close()


if __name__ == '__main__':
    asyncio.run(main())
