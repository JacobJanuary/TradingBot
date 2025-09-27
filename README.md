# 🤖 Trading Bot - Professional Cryptocurrency Trading System

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-blue.svg)
![Tests](https://img.shields.io/badge/Tests-100%25_Passing-success.svg)
![Coverage](https://img.shields.io/badge/Coverage-44%25-yellow.svg)
![License](https://img.shields.io/badge/License-Proprietary-red.svg)

## 📋 Overview

Professional-grade algorithmic trading bot for cryptocurrency markets with advanced risk management, real-time position protection, and comprehensive monitoring capabilities.

### ✨ Key Features

- 🔄 **Multi-Exchange Support**: Binance and Bybit integration via CCXT
- 📊 **Signal Processing**: Integration with FAS scoring system
- 🛡️ **Advanced Risk Management**: Position limits, daily loss limits, leverage control
- 🎯 **Smart Stop-Loss System**: Fixed, ATR-based, time-based, and trailing stops
- 📈 **Real-time Monitoring**: Prometheus metrics, Grafana dashboards, health checks
- ⚡ **WebSocket Streams**: Real-time market data and position updates
- 🔐 **Position Protection**: Automatic risk assessment and emergency liquidation
- 📊 **Performance Analytics**: Sharpe ratio, Sortino ratio, drawdown analysis
- 🐳 **Docker Ready**: Complete containerization with docker-compose

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 14+
- Docker & Docker Compose (optional)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/your-org/TradingBot.git
cd TradingBot
```

2. **Set up Python environment:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys and database credentials
```

4. **Set up database:**
```bash
# Create database and apply migrations
createdb trading_bot
alembic upgrade head
```

5. **Run the bot:**
```bash
python main.py --config config/config.yaml
```

### 🐳 Docker Deployment

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f trading-bot

# Stop services
docker-compose down
```

## 📊 Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Signal Source  │────▶│ Signal Processor │────▶│ Exchange Manager │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                  │                         │
                                  ▼                         ▼
                         ┌──────────────────┐     ┌──────────────────┐
                         │  Risk Manager    │     │ Position Manager │
                         └──────────────────┘     └──────────────────┘
                                  │                         │
                                  └────────┬────────────────┘
                                           ▼
                                  ┌──────────────────┐
                                  │Protection System │
                                  └──────────────────┘
                                           │
                         ┌─────────────────┼─────────────────┐
                         ▼                 ▼                 ▼
                ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                │StopLoss Mgr  │  │Position Guard│  │Trailing Stop │
                └──────────────┘  └──────────────┘  └──────────────┘
```

## 🛠️ Configuration

Edit `config/config.yaml`:

```yaml
trading:
  exchanges:
    - name: binance
      enabled: true
      markets: [BTC/USDT, ETH/USDT]
      leverage: 5

risk:
  max_position_size: 10000
  max_daily_loss: 1000
  risk_per_trade: 1.0  # % of capital

protection:
  stop_loss:
    type: combined
    fixed_percentage: 2.0
    trailing_percentage: 1.5
```

## 📈 Monitoring

### Prometheus Metrics
- **Endpoint**: `http://localhost:8000/metrics`
- **Metrics**: Trades, P&L, positions, signals, errors

### Grafana Dashboards
- **URL**: `http://localhost:3000`
- **Default credentials**: admin/admin
- **Dashboards**: Overview, Positions, Performance, Risk

### Health Check
- **Endpoint**: `http://localhost:8080/health`
- **Status**: Database, exchanges, WebSockets, risk limits

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
```

## 📚 Documentation

- [Deployment Guide](DEPLOYMENT.md) - Complete deployment and operation manual
- [API Reference](docs/api.md) - Module API documentation
- [Configuration](docs/config.md) - Configuration options
- [Development](docs/development.md) - Development guidelines

## 🔧 Maintenance

### Daily Tasks
```bash
# Clean old data
python scripts/cleanup.py --days 30

# Backup database
python scripts/backup.py
```

### System Check
```bash
# Pre-start verification
python scripts/pre_start_check.py

# Graceful shutdown
python scripts/graceful_shutdown.py --reason "Maintenance"
```

## 📊 Performance Metrics

The system tracks and reports:
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Ratio of gross profit to gross loss
- **Sharpe Ratio**: Risk-adjusted returns
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Recovery Factor**: Net profit divided by maximum drawdown

## 🔐 Security

- API keys stored in environment variables
- Database connections use SSL
- Non-root Docker container execution
- Rate limiting on all API calls
- Automatic position protection systems

## 🤝 Contributing

This is a proprietary system. Contributions are restricted to authorized developers.

## 📄 License

Proprietary Software - All Rights Reserved

## 📞 Support

- **Email**: support@tradingbot.com
- **Issues**: GitHub Issues (private repository)
- **Documentation**: [docs.tradingbot.com](https://docs.tradingbot.com)

---

**Version**: 1.0.0  
**Last Updated**: September 26, 2024  
**Status**: Production Ready