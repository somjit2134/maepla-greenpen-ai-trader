# Mae Pla Green Pen AI Trader

> Professional XAUUSD Gold Trading Analysis System

## Overview

The Mae Pla Green Pen AI Trader is a production-ready quantitative trading assistant for XAUUSD (Gold vs US Dollar). It implements the complete Mae Pla Green Pen trading framework with multi-timeframe analysis, market structure detection, support/resistance zones, grid level analysis, and automated trade plan generation.

## Architecture

```
pencilgreen/
├── config/           # Configuration files
│   └── config.yaml   # Main configuration
├── src/
│   ├── main.py       # CLI entry point
│   ├── config_loader.py
│   ├── log_setup.py
│   ├── data/         # Data layer
│   │   ├── mt5_connector.py    # MT5 API connector
│   │   └── database.py         # SQLite database
│   ├── analysis/     # Analysis engine
│   │   ├── multi_timeframe.py
│   │   ├── market_structure.py
│   │   ├── support_resistance.py
│   │   ├── grid_analysis.py
│   │   ├── frame_analysis.py
│   │   ├── price_action.py
│   │   └── setup_scorer.py
│   ├── engine/       # Core engines
│   │   ├── analysis_engine.py
│   │   ├── trading_engine.py
│   │   └── risk_engine.py
│   ├── notification/ # Alert system
│   │   └── line_notify.py
│   └── ai/           # Future ML integration
├── tests/            # Test suite
├── data/             # SQLite database
├── logs/             # Application logs
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Features

- **Multi-Timeframe Analysis**: Monthly, Weekly, Daily, H4, H1, M15
- **Market Structure Detection**: HH/HL, LH/LL pattern recognition
- **Support & Resistance Zones**: Automated S/R detection with clustering
- **Grid 0/5 Analysis**: Psychological price level detection
- **1000-Point Frame**: Gold cycle position analysis
- **ATH Frame**: All-time high distance calculation
- **Price Action Detection**: Engulfing, pin bars, wick analysis
- **Setup Scoring**: 0-10 scoring system with grade interpretation
- **Risk Management**: Position sizing, R:R calculation, daily loss limits
- **LINE Notifications**: Real-time alerts via LINE Notify
- **SQLite Database**: Signal history, trade journal, performance tracking
- **MT5 Integration**: Live data and trade execution
- **Simulated Mode**: Demo mode for testing without MT5
- **Docker Support**: Containerized deployment

## Installation

### Prerequisites

- Python 3.12+
- MetaTrader 5 (optional, for live trading)
- LINE Notify token (optional, for alerts)

### Standard Installation

```bash
# Clone or copy the project
cd pencilgreen

# Install dependencies
pip install -r requirements.txt

# Configure settings
edit config/config.yaml

# Run analysis (simulated mode)
python -m src.main /analyze --simulate
```

### Docker Installation

```bash
# Build and run
docker compose up -d

# Or build manually
docker build -t maepla-trader .
docker run --rm maepla-trader /analyze --simulate
```

## Configuration

Edit `config/config.yaml`:

```yaml
mt5:
  path: "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
  login: 12345678
  password: "your_password"
  server: "YourBroker-Server"

symbol:
  name: "XAUUSD"
  at: 5603.0  # All-time high

line_notify:
  token: "your_line_token"
  enabled: true

risk:
  default_risk_percent: 1.0
  max_risk_percent: 2.0
  min_rr: 2.0
  max_daily_loss_percent: 5.0
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `/analyze` | Full XAUUSD analysis |
| `/scan` | Scan all setups |
| `/buysetup` | Find BUY setups only |
| `/sellsetup` | Find SELL setups only |
| `/risk` | Calculate position size |
| `/backtest` | Run backtest |
| `/journal` | Record/View trading journal |
| `/monitor` | Continuous monitoring mode |

### Examples

```bash
# Full analysis
python -m src.main /analyze --simulate

# Scan with risk check
python -m src.main /analyze --simulate --risk-check

# Position size calculator
python -m src.main /risk --entry 4075 --stop 4060 --target 4100 --balance 10000

# Continuous monitoring
python -m src.main /monitor --simulate --interval 60

# View journal
python -m src.main /journal view

# Add journal entry
python -m src.main /journal add --direction BUY --entry-price 4000 --exit-price 4050 --profit 50 --lesson "Waited for confirmation"
```

## Scoring System

| Score | Grade | Action |
|-------|-------|--------|
| 9-10 | A+ Setup | High probability |
| 7-8 | Good Setup | Consider trade |
| 5-6 | Watchlist | Monitor only |
| <5 | NO TRADE | Stay out |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term

# Run specific test
pytest tests/test_analysis.py -v -k "test_bullish_structure"
```

## Trading Rules

1. **Never predict** - Wait for price to arrive at important locations
2. **Multi-timeframe alignment** - All timeframes must agree
3. **Minimum R:R 1:2** - Never trade with poor risk/reward
4. **Maximum 2% risk per trade** - Preserve capital
5. **News awareness** - Avoid trading during high-impact events
6. **No revenge trading** - Never trade emotionally
7. **Journal every trade** - Learn from every outcome

## Database Schema

The SQLite database (`data/trading.db`) contains:

- **signals**: All analysis signals with full breakdown
- **trades**: Executed trade records
- **performance**: Aggregate performance metrics
- **journal**: Trading psychology journal

## LINE Notifications

Enable LINE alerts in config.yaml:

```yaml
line_notify:
  token: "YOUR_LINE_TOKEN"
  enabled: true
```

Get a token at: https://notify-bot.line.me/

## License

Private trading system. For educational and personal use only.

## Disclaimer

Trading financial markets involves substantial risk. This system is a tool for analysis and does not guarantee profits. Never risk more than you can afford to lose.
