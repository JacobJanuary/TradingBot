"""
Signal Performance Analyzer

Analyzes signals from CSV file using exchange API data.
Creates detailed performance table with market metrics.

Usage:
    python tests/analysis/signal_performance_analyzer.py <csv_file_path>

Example:
    python tests/analysis/signal_performance_analyzer.py data-1761678817380.csv
"""

import asyncio
import csv
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import ccxt.async_support as ccxt


class SignalAnalyzer:
    """Analyzes signal performance using exchange API data."""

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

    async def close(self):
        """Close exchange connections."""
        await self.binance.close()
        await self.bybit.close()

    def normalize_symbol_for_exchange(self, symbol: str, exchange: str) -> str:
        """
        Normalize symbol for specific exchange.

        Args:
            symbol: Symbol like 'BTCUSDT'
            exchange: 'binance' or 'bybit'

        Returns:
            Normalized symbol for exchange API
        """
        if exchange == 'binance':
            # Binance Futures: BTCUSDT
            return symbol
        elif exchange == 'bybit':
            # Bybit Futures: BTC/USDT:USDT
            base = symbol.replace('USDT', '')
            return f"{base}/USDT:USDT"
        return symbol

    async def get_price_at_timestamp(
        self,
        exchange_name: str,
        symbol: str,
        timestamp: datetime
    ) -> Optional[float]:
        """
        Get price at specific timestamp.

        Uses 1m OHLCV data to find closest candle to timestamp.

        Args:
            exchange_name: 'binance' or 'bybit'
            symbol: Trading pair (e.g., 'BTCUSDT')
            timestamp: Target timestamp

        Returns:
            Close price at timestamp, or None if not found
        """
        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Convert to milliseconds
            ts_ms = int(timestamp.timestamp() * 1000)

            # Fetch 1m candles around timestamp (10 candles before and after)
            ohlcv = await exchange.fetch_ohlcv(
                normalized_symbol,
                timeframe='1m',
                since=ts_ms - (10 * 60 * 1000),  # 10 min before
                limit=20
            )

            if not ohlcv:
                return None

            # Find closest candle to timestamp
            closest_candle = min(ohlcv, key=lambda x: abs(x[0] - ts_ms))

            # [timestamp, open, high, low, close, volume]
            close_price = closest_candle[4]

            return close_price

        except Exception as e:
            print(f"    ⚠️ Error getting price for {symbol}: {e}")
            return None

    async def get_open_interest(
        self,
        exchange_name: str,
        symbol: str
    ) -> Optional[float]:
        """
        Get current open interest in USDT.

        Note: This gets CURRENT OI, not historical.
        Historical OI requires different endpoints.

        Args:
            exchange_name: 'binance' or 'bybit'
            symbol: Trading pair

        Returns:
            Open interest in USDT, or None if not available
        """
        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Try Method 1: fetch_open_interest (most direct)
            try:
                oi_data = await exchange.fetch_open_interest(normalized_symbol)

                # Try different fields in order of preference
                if oi_data:
                    # Option 1: openInterestValue (already in USDT)
                    if 'openInterestValue' in oi_data and oi_data['openInterestValue'] is not None:
                        return float(oi_data['openInterestValue'])

                    # Option 2: quoteVolume
                    if 'quoteVolume' in oi_data and oi_data['quoteVolume'] is not None:
                        return float(oi_data['quoteVolume'])

                    # Option 3: openInterestAmount (need to convert to USDT)
                    if 'openInterestAmount' in oi_data and oi_data['openInterestAmount'] is not None:
                        amount = float(oi_data['openInterestAmount'])

                        # Try to get mark price from info field
                        if 'info' in oi_data and oi_data['info']:
                            mark_price = oi_data['info'].get('markPrice') or oi_data['info'].get('lastPrice')
                            if mark_price:
                                return amount * float(mark_price)

                        # Fallback: fetch current ticker to get price
                        ticker = await exchange.fetch_ticker(normalized_symbol)
                        if ticker and ticker.get('last'):
                            return amount * float(ticker['last'])
            except Exception:
                pass  # Try alternative method

            # Method 2: fetch_ticker (has OI in some exchanges)
            try:
                ticker = await exchange.fetch_ticker(normalized_symbol)
                if ticker:
                    # Some exchanges include OI in ticker
                    info = ticker.get('info', {})

                    # Binance: openInterest field
                    if 'openInterest' in info:
                        oi_amount = float(info['openInterest'])
                        if ticker.get('last'):
                            return oi_amount * float(ticker['last'])

                    # Bybit: openInterest in USDT
                    if 'openInterestValue' in info:
                        return float(info['openInterestValue'])
            except Exception:
                pass

            return None

        except Exception as e:
            # Only print error if it's not a "not supported" error
            error_msg = str(e).lower()
            if 'not support' not in error_msg and 'not available' not in error_msg:
                print(f"    ⚠️ Error getting OI for {symbol}: {e}")
            return None

    async def get_1h_metrics_after_signal(
        self,
        exchange_name: str,
        symbol: str,
        signal_timestamp: datetime
    ) -> Dict[str, Optional[float]]:
        """
        Get 1h metrics AFTER signal timestamp.

        Fetches the 1h candle that starts at signal_timestamp.

        Args:
            exchange_name: 'binance' or 'bybit'
            symbol: Trading pair
            signal_timestamp: Signal timestamp

        Returns:
            Dict with volume_usdt, high, low for 1h after signal
        """
        result = {
            'volume_usdt': None,
            'high_1h': None,
            'low_1h': None
        }

        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Round timestamp down to hour boundary
            hour_start = signal_timestamp.replace(minute=0, second=0, microsecond=0)
            ts_ms = int(hour_start.timestamp() * 1000)

            # Fetch 1h candle starting at signal hour
            ohlcv = await exchange.fetch_ohlcv(
                normalized_symbol,
                timeframe='1h',
                since=ts_ms,
                limit=1
            )

            if not ohlcv:
                return result

            candle = ohlcv[0]
            # [timestamp, open, high, low, close, volume]

            # Volume is in base currency, convert to USDT
            base_volume = candle[5]
            close_price = candle[4]
            volume_usdt = base_volume * close_price

            result['volume_usdt'] = volume_usdt
            result['high_1h'] = candle[2]
            result['low_1h'] = candle[3]

            return result

        except Exception as e:
            print(f"    ⚠️ Error getting 1h metrics for {symbol}: {e}")
            return result

    async def get_price_5min_before(
        self,
        exchange_name: str,
        symbol: str,
        signal_timestamp: datetime
    ) -> Optional[float]:
        """
        Get price 5 minutes BEFORE signal timestamp.

        Args:
            exchange_name: 'binance' or 'bybit'
            symbol: Trading pair
            signal_timestamp: Signal timestamp

        Returns:
            Close price 5 minutes before signal, or None if not found
        """
        try:
            exchange = self.binance if exchange_name == 'binance' else self.bybit
            normalized_symbol = self.normalize_symbol_for_exchange(symbol, exchange_name)

            # Get timestamp 5 minutes before signal
            ts_5min_before = signal_timestamp - timedelta(minutes=5)
            ts_ms = int(ts_5min_before.timestamp() * 1000)

            # Fetch 1m candles around that timestamp
            ohlcv = await exchange.fetch_ohlcv(
                normalized_symbol,
                timeframe='1m',
                since=ts_ms - (5 * 60 * 1000),  # 5 min before
                limit=10
            )

            if not ohlcv:
                return None

            # Find closest candle to 5min before timestamp
            closest_candle = min(ohlcv, key=lambda x: abs(x[0] - ts_ms))

            # [timestamp, open, high, low, close, volume]
            close_price = closest_candle[4]

            return close_price

        except Exception as e:
            print(f"    ⚠️ Error getting 5min-before price for {symbol}: {e}")
            return None

    async def analyze_signal(self, signal: Dict) -> Dict:
        """
        Analyze single signal using exchange API.

        Args:
            signal: Signal data from CSV

        Returns:
            Dict with analysis results
        """
        symbol = signal['pair_symbol']
        direction = signal['recommended_action']
        created_at = datetime.fromisoformat(signal['created_at'].replace('+00', '+00:00'))
        signal_timestamp = datetime.fromisoformat(signal['timestamp'].replace('+00', '+00:00'))
        exchange_id = int(signal['exchange_id'])

        # Map exchange_id to exchange name
        # 1 = Binance, 2 = Bybit (based on typical DB schema)
        exchange_name = 'binance' if exchange_id == 1 else 'bybit'

        print(f"  Analyzing {symbol} ({direction}) on {exchange_name} at {signal_timestamp}")

        # Get price at signal timestamp
        price = await self.get_price_at_timestamp(exchange_name, symbol, signal_timestamp)

        # Get price 5 minutes before signal
        price_5min_before = await self.get_price_5min_before(exchange_name, symbol, signal_timestamp)

        # Get open interest (current)
        open_interest = await self.get_open_interest(exchange_name, symbol)

        # Get 1h metrics after signal
        metrics_1h = await self.get_1h_metrics_after_signal(
            exchange_name, symbol, signal_timestamp
        )

        # Calculate price change over 5 minutes before signal
        price_change_5min_percent = None
        if price and price_5min_before and price_5min_before > 0:
            price_change_5min_percent = ((price - price_5min_before) / price_5min_before) * 100

        # Calculate potential 1h profit based on direction
        profit_1h_percent = None
        if price and metrics_1h['high_1h'] and metrics_1h['low_1h']:
            if direction == 'BUY':
                # For BUY (LONG): profit = (high_1h - entry_price) / entry_price * 100
                profit_1h_percent = ((metrics_1h['high_1h'] - price) / price) * 100
            elif direction == 'SELL':
                # For SELL (SHORT): profit = (entry_price - low_1h) / entry_price * 100
                profit_1h_percent = ((price - metrics_1h['low_1h']) / price) * 100

        return {
            'pair': symbol,
            'direction': direction,
            'datetime': signal_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'price': f"${price:.8f}" if price else "N/A",
            'price_5min_before': f"${price_5min_before:.8f}" if price_5min_before else "N/A",
            'price_change_5min_percent': f"{price_change_5min_percent:+.2f}%" if price_change_5min_percent is not None else "N/A",
            'open_interest_usdt': f"${open_interest:,.2f}" if open_interest else "N/A",
            'volume_1h_usdt': f"${metrics_1h['volume_usdt']:,.2f}" if metrics_1h['volume_usdt'] else "N/A",
            'high_1h': f"${metrics_1h['high_1h']:.8f}" if metrics_1h['high_1h'] else "N/A",
            'low_1h': f"${metrics_1h['low_1h']:.8f}" if metrics_1h['low_1h'] else "N/A",
            'profit_1h_percent': f"{profit_1h_percent:+.2f}%" if profit_1h_percent is not None else "N/A",
            'exchange': exchange_name.upper()
        }

    async def analyze_signals_from_csv(self, csv_path: str) -> List[Dict]:
        """
        Analyze all signals from CSV file.

        Args:
            csv_path: Path to CSV file

        Returns:
            List of analysis results
        """
        results = []

        # Read CSV
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            signals = list(reader)

        print(f"\n📊 Analyzing {len(signals)} signals from {csv_path}")
        print(f"{'=' * 80}\n")

        # Analyze each signal
        for i, signal in enumerate(signals, 1):
            print(f"[{i}/{len(signals)}] Processing {signal['pair_symbol']}...")

            result = await self.analyze_signal(signal)
            results.append(result)

            # Add small delay to respect rate limits
            await asyncio.sleep(0.5)

        return results

    def print_results_table(self, results: List[Dict]):
        """
        Print results as formatted table.

        Args:
            results: List of analysis results
        """
        print(f"\n{'=' * 180}")
        print("SIGNAL ANALYSIS RESULTS")
        print(f"{'=' * 180}\n")

        # Print header
        header = (
            f"{'Pair':<15} "
            f"{'Direction':<10} "
            f"{'DateTime':<20} "
            f"{'Price':<15} "
            f"{'Price -5min':<15} "
            f"{'Δ5min %':<10} "
            f"{'OI (USDT)':<18} "
            f"{'1h Vol (USDT)':<18} "
            f"{'1h High':<15} "
            f"{'1h Low':<15} "
            f"{'Profit 1h %':<12} "
            f"{'Exchange':<10}"
        )
        print(header)
        print("-" * 180)

        # Print rows
        for result in results:
            row = (
                f"{result['pair']:<15} "
                f"{result['direction']:<10} "
                f"{result['datetime']:<20} "
                f"{result['price']:<15} "
                f"{result['price_5min_before']:<15} "
                f"{result['price_change_5min_percent']:<10} "
                f"{result['open_interest_usdt']:<18} "
                f"{result['volume_1h_usdt']:<18} "
                f"{result['high_1h']:<15} "
                f"{result['low_1h']:<15} "
                f"{result['profit_1h_percent']:<12} "
                f"{result['exchange']:<10}"
            )
            print(row)

        print(f"\n{'=' * 180}")
        print(f"Total signals analyzed: {len(results)}")
        print(f"{'=' * 180}\n")

    def save_results_to_csv(self, results: List[Dict], output_path: str):
        """
        Save results to CSV file.

        Args:
            results: List of analysis results
            output_path: Path to output CSV file
        """
        if not results:
            print("No results to save")
            return

        # Write CSV
        with open(output_path, 'w', newline='') as f:
            fieldnames = [
                'pair', 'direction', 'datetime', 'price',
                'price_5min_before', 'price_change_5min_percent',
                'open_interest_usdt', 'volume_1h_usdt',
                'high_1h', 'low_1h', 'profit_1h_percent', 'exchange'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()
            writer.writerows(results)

        print(f"✅ Results saved to: {output_path}")


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python signal_performance_analyzer.py <csv_file_path>")
        print("\nExample:")
        print("  python tests/analysis/signal_performance_analyzer.py data-1761678817380.csv")
        sys.exit(1)

    csv_path = sys.argv[1]

    if not Path(csv_path).exists():
        print(f"❌ Error: File not found: {csv_path}")
        sys.exit(1)

    analyzer = SignalAnalyzer()

    try:
        # Analyze signals
        results = await analyzer.analyze_signals_from_csv(csv_path)

        # Print results table
        analyzer.print_results_table(results)

        # Save to CSV
        output_path = csv_path.replace('.csv', '_analysis.csv')
        analyzer.save_results_to_csv(results, output_path)

    finally:
        await analyzer.close()


if __name__ == '__main__':
    asyncio.run(main())
