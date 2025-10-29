# Signal Performance Analyzer - Usage Examples

## Quick Start

### 1. Analyze Your Signals

```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Analyze signals from CSV
python tests/analysis/signal_performance_analyzer.py data-1761678817380.csv
```

### 2. Output

**Console Output:**
```
📊 Analyzing 20 signals from data-1761678817380.csv
================================================================================

[1/20] Processing SKLUSDT...
  Analyzing SKLUSDT (BUY) on binance at 2025-10-28 18:15:00
[2/20] Processing PHBUSDT...
  Analyzing PHBUSDT (BUY) on binance at 2025-10-28 17:45:00
...

================================================================================
SIGNAL ANALYSIS RESULTS
================================================================================

Pair            Direction  DateTime             Price           OI (USDT)          1h Vol (USDT)      1h High         1h Low          Exchange
--------------------------------------------------------------------------------------------------------------------------------------------
SKLUSDT         BUY        2025-10-28 18:15:00  $0.01932000     N/A                $2,383,656.67      $0.01975000     $0.01905000     BINANCE
PHBUSDT         BUY        2025-10-28 17:45:00  $0.80390000     N/A                $29,916,937.96     $0.82490000     $0.79000000     BINANCE
AIAUSDT         BUY        2025-10-28 14:45:00  $1.13580000     N/A                $4,989,717.20      $1.19790000     $1.13000000     BINANCE

Total signals analyzed: 20
================================================================================

✅ Results saved to: data-1761678817380_analysis.csv
```

**CSV Output** (`data-1761678817380_analysis.csv`):
```csv
pair,direction,datetime,price,open_interest_usdt,volume_1h_usdt,high_1h,low_1h,exchange
SKLUSDT,BUY,2025-10-28 18:15:00,$0.01932000,N/A,"$2,383,656.67",$0.01975000,$0.01905000,BINANCE
PHBUSDT,BUY,2025-10-28 17:45:00,$0.80390000,N/A,"$29,916,937.96",$0.82490000,$0.79000000,BINANCE
```

## Data Interpretation

### Column Explanations

| Column | Description | Example | Interpretation |
|--------|-------------|---------|----------------|
| **pair** | Trading symbol | SKLUSDT | SKL/USDT perpetual futures |
| **direction** | Signal direction | BUY | Long position signal |
| **datetime** | Signal timestamp | 2025-10-28 18:15:00 | When signal was generated |
| **price** | Entry price | $0.01932000 | Price at signal time |
| **open_interest_usdt** | Open interest | N/A | Current OI in USDT (if available) |
| **volume_1h_usdt** | 1h trading volume | $2,383,656.67 | Volume in that hour (USDT) |
| **high_1h** | 1h high | $0.01975000 | Highest price in 1h after signal |
| **low_1h** | 1h low | $0.01905000 | Lowest price in 1h after signal |
| **exchange** | Exchange | BINANCE | Where to trade |

### Example Analysis

**Signal: SKLUSDT BUY at $0.01932**

- **1h High**: $0.01975 → +2.22% potential profit
- **1h Low**: $0.01905 → -1.40% potential loss
- **1h Volume**: $2.38M → Good liquidity
- **Direction**: Price went UP (+2.22% high reached)

**Signal: PHBUSDT BUY at $0.8039**

- **1h High**: $0.8249 → +2.61% potential profit
- **1h Low**: $0.7900 → -1.73% potential loss
- **1h Volume**: $29.9M → Excellent liquidity
- **Direction**: Price went UP (+2.61% high reached)

## Advanced Usage

### Filter Specific Exchange

```bash
# Analyze only Binance signals
grep ",1," data-1761678817380.csv > binance_signals.csv
python tests/analysis/signal_performance_analyzer.py binance_signals.csv
```

### Analyze Recent Signals Only

```bash
# Last 10 signals
head -11 data-1761678817380.csv > recent_signals.csv
python tests/analysis/signal_performance_analyzer.py recent_signals.csv
```

### Analyze Specific Pairs

```bash
# Only BTC and ETH signals
grep -E "BTC|ETH" data-1761678817380.csv > btc_eth_signals.csv
python tests/analysis/signal_performance_analyzer.py btc_eth_signals.csv
```

## Performance Metrics Calculation

### Price Change %

Calculate in Excel/Google Sheets:

```excel
=(high_1h - price) / price * 100    # Max profit %
=(low_1h - price) / price * 100     # Max drawdown %
```

### Win Rate

Count signals where `high_1h > price * 1.02` (2% profit target)

### Average Volume

```excel
=AVERAGE(volume_1h_usdt)
```

## Limitations & Notes

### ⚠️ Important Notes

1. **Historical Data**: Script fetches price/volume from exchange API. Very old signals may not have data available.

2. **Open Interest**: Shows CURRENT OI, not historical OI at signal time (limited by API availability).

3. **1h Metrics**: Shows data for the 1h candle that INCLUDES the signal timestamp (not exactly 1h forward).

4. **Rate Limits**: Script has 0.5s delay between signals. For large CSV files (100+ signals), analysis may take time.

5. **Symbol Availability**: Delisted symbols will show "N/A" for all metrics.

### Known Issues

- **OI not available**: Some pairs don't have OI data on Binance/Bybit
- **Very recent signals**: API may not have complete 1h candle data yet
- **Symbol format**: Script automatically converts symbols for each exchange

## Troubleshooting

### Problem: "Rate limit exceeded"

**Solution**: Script already includes delays. If still happening, edit script and increase delay:

```python
# Line ~255
await asyncio.sleep(1.0)  # Increase from 0.5 to 1.0
```

### Problem: All results show "N/A"

**Possible causes:**
1. Wrong symbol format in CSV
2. Symbol delisted from exchange
3. API connection issue

**Solution**: Check that `pair_symbol` column has correct format (e.g., BTCUSDT, not BTC-USDT)

### Problem: "Symbol not found"

**Solution**: Symbol might be:
- Delisted from exchange
- Spot-only (script uses futures)
- Incorrectly formatted

### Problem: Script hangs

**Solution**:
1. Check internet connection
2. Check exchange API status
3. Try with smaller CSV file first

## API Documentation

### Binance Futures API

- **Docs**: https://binance-docs.github.io/apidocs/futures/en/
- **Rate Limits**: 1200 weight/minute
- **Historical Data**: Up to 500 candles per request

### Bybit Futures API

- **Docs**: https://bybit-exchange.github.io/docs/v5/intro
- **Rate Limits**: 120 requests/minute
- **Historical Data**: Up to 200 candles per request

### CCXT Library

- **Docs**: https://docs.ccxt.com/
- **GitHub**: https://github.com/ccxt/ccxt
- **Examples**: https://github.com/ccxt/ccxt/tree/master/examples

## Real-World Example

Let's analyze a complete signal:

```
Signal: AIAUSDT BUY at 2025-10-28 14:45:00
Price: $1.13580
```

**Results:**
```
1h High: $1.19790 (+5.47%)
1h Low:  $1.13000 (-0.51%)
1h Vol:  $4,989,717
```

**Analysis:**
- ✅ Signal was PROFITABLE: Price went +5.47% in 1h
- ✅ Low risk: Only -0.51% drawdown
- ✅ Good volume: $4.9M liquidity
- ✅ High reward/risk ratio: 5.47% / 0.51% = 10.7x

**Trading Decision:**
- Strong BUY signal
- Entry: $1.13580
- Target: $1.19790 (5.47% profit)
- Stop-loss: $1.13000 (0.51% loss)
- Risk/Reward: 1:10 (excellent)

## Tips for Better Analysis

1. **Compare multiple timeframes**: Analyze 1h, 4h, 24h metrics
2. **Check volume trends**: High volume = more reliable signal
3. **Monitor OI changes**: Increasing OI = strong trend
4. **Batch analysis**: Analyze weekly/monthly signals together
5. **Track win rate**: Calculate % of profitable signals
6. **Export to Excel**: Further analysis with pivot tables

## Next Steps

1. **Run full analysis** on your signal CSV
2. **Import CSV to Excel/Google Sheets**
3. **Create charts** for visualization
4. **Calculate win rate** and average profit
5. **Identify best performing pairs**
6. **Optimize signal parameters** based on results
