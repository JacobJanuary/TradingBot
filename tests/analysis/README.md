# Signal Analysis Tools

Tools for analyzing trading signals performance using exchange API data.

## Scripts

### signal_performance_analyzer.py

Analyzes signals from CSV file and creates detailed performance table.

**Features:**
- Fetches historical price at signal timestamp
- Gets current open interest in USDT
- Calculates 1h volume in USDT after signal
- Gets 1h high/low after signal
- Supports both Binance and Bybit
- Exports results to CSV

**Usage:**

```bash
# Basic usage
python tests/analysis/signal_performance_analyzer.py <csv_file_path>

# Example
python tests/analysis/signal_performance_analyzer.py data-1761678817380.csv
```

**Output:**

1. **Console table** - Formatted table with results
2. **CSV file** - `<input>_analysis.csv` with detailed data

**Example output:**

```
Pair            Direction  DateTime             Price           OI (USDT)          1h Vol (USDT)      1h High         1h Low          Exchange
--------------------------------------------------------------------------------------------------------------------
SKLUSDT         BUY        2025-10-28 18:15:00  $0.01946000     $12,345,678.90     $567,890.12        $0.01950000     $0.01940000     BINANCE
PHBUSDT         BUY        2025-10-28 17:45:00  $1.23450000     $8,765,432.10      $234,567.89        $1.24000000     $1.23000000     BINANCE
```

**Data Sources:**

- **Price at timestamp**: `fetch_ohlcv()` with 1m timeframe
- **Open Interest**: `fetch_open_interest()` (current OI)
- **1h Volume**: `fetch_ohlcv()` with 1h timeframe, converted to USDT
- **1h High/Low**: `fetch_ohlcv()` for 1h candle after signal

**CSV Output Format:**

| Column | Description |
|--------|-------------|
| pair | Trading pair (e.g., BTCUSDT) |
| direction | BUY or SELL |
| datetime | Signal timestamp (YYYY-MM-DD HH:MM:SS) |
| price | Price at signal timestamp |
| open_interest_usdt | Current open interest in USDT |
| volume_1h_usdt | 1h volume in USDT after signal |
| high_1h | 1h high after signal |
| low_1h | 1h low after signal |
| exchange | BINANCE or BYBIT |

**Requirements:**

```bash
pip install ccxt
```

**Rate Limits:**

- Script includes 0.5s delay between signals
- Uses ccxt's built-in rate limit handling
- Safe for analyzing large CSV files

**Error Handling:**

- If data unavailable for symbol, shows "N/A"
- Prints warnings for API errors
- Continues processing remaining signals

## Input CSV Format

Expected CSV format (from signal database):

```csv
id,pair_symbol,recommended_action,score_week,score_month,timestamp,created_at,trading_pair_id,exchange_id,score_week_filter,score_month_filter,max_trades_filter,stop_loss_filter,trailing_activation_filter,trailing_distance_filter
6487122,SKLUSDT,BUY,80.00,70.60,2025-10-28 18:15:00+00,2025-10-28 18:33:02.275595+00,2176,1,72,64,3,5,2,0.5
```

**Required columns:**
- `pair_symbol` - Trading pair
- `recommended_action` - BUY or SELL
- `timestamp` - Signal timestamp
- `created_at` - Signal creation timestamp
- `exchange_id` - Exchange ID (1=Binance, 2=Bybit)

## Limitations

1. **Historical OI**: Current implementation fetches CURRENT open interest, not historical OI at signal timestamp (requires different API endpoints)

2. **1h Metrics**: Gets metrics for the 1h candle that includes the signal timestamp (not exactly 1h after)

3. **Symbol Support**: Only works for symbols available on the exchange (delisted symbols will show N/A)

4. **Timeframe**: 1m data may not be available for very old signals (exchanges have data retention limits)

## Future Improvements

- [ ] Add historical open interest fetching
- [ ] Add 24h volume comparison
- [ ] Calculate price change % after signal
- [ ] Add win/loss analysis if stop-loss hit
- [ ] Support for spot markets
- [ ] Parallel processing for faster analysis
- [ ] Progress bar for large CSV files

## Examples

### Analyze recent signals
```bash
python tests/analysis/signal_performance_analyzer.py data-1761678817380.csv
```

### Analyze and save to specific location
```bash
python tests/analysis/signal_performance_analyzer.py signals.csv
# Output: signals_analysis.csv
```

## Troubleshooting

**Problem**: "Symbol not found"
- **Solution**: Symbol might be delisted or not available on exchange

**Problem**: "Rate limit exceeded"
- **Solution**: Script already has delays, but you can increase delay in code

**Problem**: "N/A" in results
- **Solution**: Data might not be available for that timestamp (too old or too recent)

**Problem**: "Connection timeout"
- **Solution**: Check internet connection and exchange API status
