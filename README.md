# Crypto Futures Trading Bot

A professional-grade automated trading bot for cryptocurrency futures trading on **Binance** and **Bybit** exchanges. Built with Python, asyncio, and CCXT for high-performance, low-latency execution.

## Features

### Core Trading
- **Multi-Exchange Support**: Simultaneous trading on Binance Futures and Bybit Linear
- **WebSocket Signal Processing**: Real-time signal ingestion from external signal server
- **Atomic Position Management**: Database-backed position tracking with crash recovery
- **Smart Order Execution**: Automatic leverage setting, position sizing, and lot validation

### Risk Management
- **Automatic Stop Loss**: Every position protected via Binance Algo API or Bybit position-attached SL
- **Smart Trailing Stop**: Dynamic trailing stop with configurable activation threshold and callback rate
- **Aged Position Manager**: Auto-close positions held too long (breakeven or gradual liquidation)
- **Position Guard**: Emergency protection system with margin call handling

### Reliability
- **Zombie Order Cleanup**: Automatic detection and cancellation of orphaned orders
- **Position Synchronization**: Periodic sync between database and exchange
- **WebSocket Health Monitor**: Auto-reconnection and subscription recovery
- **Event Logging**: Full audit trail of all bot actions in PostgreSQL

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                           main.py                               │
│                    (TradingBot Orchestrator)                     │
├─────────────┬─────────────┬─────────────┬───────────────────────┤
│   Exchange  │   Position  │   Signal    │     Protection        │
│   Manager   │   Manager   │  Processor  │     Systems           │
├─────────────┴─────────────┴─────────────┴───────────────────────┤
│                        WebSocket Layer                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ BinanceHybridWS  │  │   BybitHybridWS  │  │  SignalClient  │ │
│  └──────────────────┘  └──────────────────┘  └────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                       Database Layer                             │
│              PostgreSQL (positions, events, signals)             │
└──────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
TradingBot/
├── main.py                    # Application entry point
├── config/                    # Configuration loading
├── core/                      # Core business logic
│   ├── exchange_manager.py    # CCXT wrapper for exchanges
│   ├── position_manager.py    # Position lifecycle management
│   ├── stop_loss_manager.py   # Stop loss creation/validation (Algo API)
│   ├── signal_processor_websocket.py  # Signal processing
│   ├── aged_position_manager.py       # Aged position handling
│   ├── zombie_manager.py      # Orphaned order cleanup
│   └── ...
├── protection/                # Risk management systems
│   ├── trailing_stop.py       # Smart trailing stop manager
│   ├── position_guard.py      # Emergency protection
│   └── stop_loss_manager.py   # Protection-level SL logic
├── websocket/                 # WebSocket connections
│   ├── binance_hybrid_stream.py  # Binance User + Mark streams
│   ├── bybit_hybrid_stream.py    # Bybit Private + Public streams
│   └── signal_client.py          # Signal server connection
├── database/                  # PostgreSQL access layer
│   ├── repository.py          # Main data access
│   └── models.py             # Data models
├── monitoring/                # Health & metrics
│   ├── health_check.py        # System health monitoring
│   └── performance.py         # Trading performance tracking
├── scripts/                   # Utility scripts
│   ├── binance_trades_24h.py  # 24h trading report
│   ├── check_binance_balance.py
│   ├── close_all_binance_positions.py
│   └── complete_cleanup.py    # Full system cleanup
├── tools/                     # Diagnostic tools
└── tests/                     # Test suite
```

---

## Installation

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Binance Futures API keys
- Bybit Linear API keys (optional)

### Setup

```bash
# Clone repository
git clone <repository-url>
cd TradingBot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and database credentials
```

### Database Setup

```bash
# Create database
psql -U postgres -c "CREATE DATABASE trading_bot;"

# Run migrations
psql -U postgres -d trading_bot -f database/init.sql
```

---

## Configuration

All configuration is done via `.env` file:

### Exchange Credentials
```env
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_secret
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_secret
```

### Database
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=postgres
DB_PASSWORD=your_password
```

### Trading Parameters
```env
# Position sizing
POSITION_SIZE_USD=100
USE_SMART_LIMIT=true
POSITIONS_SMART_LIMIT=6

# Risk management
STOP_LOSS_PERCENT=4.0
TRAILING_STOP_ACTIVATION=36.0
TRAILING_STOP_CALLBACK=8.0

# Signal filtering
SIGNAL_MIN_VOLUME_1H_USDT=1000000
SIGNAL_MIN_SCORE=180

# Aged positions
AGED_POSITION_HOURS=24
```

### Signal Server
```env
SIGNAL_WS_URL=wss://your-signal-server.com/ws
SIGNAL_WS_TOKEN=your_auth_token
```

---

## Usage

### Starting the Bot

```bash
# Production mode
python main.py --mode production

# Shadow mode (signals only, no trading)
python main.py --mode shadow

# With systemd service
sudo systemctl start trading-bot
```

### Command Line Options

```bash
python main.py --help

Options:
  --mode {production,shadow,backtest}
  --kill           Kill existing instance before starting
  --no-kill        Don't check for existing instances
```

### Utility Scripts

```bash
# Check Binance balance and positions
python scripts/check_binance_balance.py

# Get 24h trading report
python scripts/binance_trades_24h.py

# Close specific or all positions
python scripts/close_all_binance_positions.py

# Full cleanup (positions, orders, database)
python scripts/complete_cleanup.py
```

---

## Signal Processing

The bot receives trading signals from an external WebSocket server. Signal flow:

1. **WebSocket Connection**: Connect to signal server (configured via `SIGNAL_WS_URL`)
2. **Wave Monitoring**: Wait for 15-minute candle close + signal wave
3. **Signal Validation**: Filter by score, volume, symbol blocklist
4. **Position Opening**: Execute trades on appropriate exchange
5. **Protection Setup**: Automatic stop loss and trailing stop

### Signal Format
```json
{
  "symbol": "BTCUSDT",
  "side": "long",
  "exchange_id": 1,
  "total_score": 250,
  "timestamp": "2025-12-14T11:00:00Z"
}
```

---

## Protection Systems

### Stop Loss (Algo API)
As of December 2025, Binance migrated conditional orders to Algo API. The bot uses:
- `fapiPrivatePostAlgoOrder` for creation
- `fapiPrivateGetOpenAlgoOrders` for validation
- `fapiPrivateDeleteAlgoOrder` for cancellation

### Trailing Stop
```
Activation: When profit reaches TRAILING_STOP_ACTIVATION%
Callback: Trail with TRAILING_STOP_CALLBACK% distance
Example: Activate at +36%, trail with 8% → locks in 28% minimum profit
```

### Aged Position Manager
Positions held beyond `AGED_POSITION_HOURS` are processed:
1. **In Profit**: Close at breakeven or better
2. **In Loss**: Gradual liquidation to minimize impact

---

## Monitoring

### Health Checks
- Exchange connectivity
- Database connection
- WebSocket stream health
- Position protection validation

### Logs
```bash
# View bot logs
tail -f logs/trading_bot.log

# View with service
journalctl -u trading-bot -f
```

### Performance Metrics
- Open positions count
- Total exposure
- PnL (realized/unrealized)
- Win rate

---

## Development

### Running Tests
```bash
pytest tests/ -v
pytest tests/unit/ -v --cov=core
```

### Code Structure
- **Async everywhere**: All I/O is async using `asyncio`
- **CCXT**: Exchange abstraction layer
- **Type hints**: Full typing for IDE support
- **Logging**: Structured logging with rotation

---

## Troubleshooting

### Common Issues

**Position not opening**
- Check symbol filter / blocklist
- Verify API key permissions
- Check minimum position size

**Stop loss not setting**
- Verify Algo API is being used (not legacy)
- Check position quantity precision
- Look for `-4005` or `-4120` errors in logs

**WebSocket disconnections**
- Check network stability
- Verify API key is not expired
- Monitor `logs/trading_bot.log` for reconnection attempts

---

## License

Proprietary - All rights reserved

---

## Support

For issues and feature requests, contact the development team.
