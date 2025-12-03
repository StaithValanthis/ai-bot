# Bybit AI Trading Bot v2.1

**A self-managing, risk-aware trading bot for Bybit perpetual futures with automated operations, health monitoring, and evidence-based strategy improvements.**

A production-ready AI trading bot for Bybit perpetual futures using meta-labeling strategy. This bot implements a two-stage approach: a primary trend-following signal generator combined with a meta-model that predicts the profitability probability of each signal.

## ⚠️ DISCLAIMER

**THIS SOFTWARE IS FOR EDUCATIONAL AND RESEARCH PURPOSES ONLY.**

- **NO GUARANTEE OF PROFITABILITY**: Trading cryptocurrency derivatives involves substantial risk of loss. Past performance does not guarantee future results.
- **HIGH RISK**: Leveraged trading can result in losses exceeding your initial deposit.
- **NOT FINANCIAL ADVICE**: This is research/engineering software, not financial advice.
- **USE AT YOUR OWN RISK**: You are solely responsible for any trading decisions and losses.

**Always test on testnet first before using real funds.**

## Overview

This trading bot implements a **meta-labeling strategy** (inspired by Lopez de Prado's "Advances in Financial Machine Learning"):

1. **Primary Model**: Generates trend-following signals using technical indicators (EMA crossovers, RSI, MACD)
2. **Meta-Model**: XGBoost classifier that predicts the probability that each primary signal will be profitable
3. **Risk Management**: Strict position sizing, stop-losses, and daily loss limits
4. **Execution**: Automated order placement and position monitoring via Bybit API

## Features

### Core Strategy
- ✅ Meta-labeling strategy for signal filtering
- ✅ Trend-following primary signals (EMA, RSI, MACD)
- ✅ XGBoost meta-model for profitability prediction

### V2 Enhancements (New!)
- ✅ **Regime Filter**: Automatically avoids trading in ranging/choppy markets
- ✅ **Performance Guard**: Auto-throttles risk during drawdowns, auto-recovers
- ✅ **Triple-Barrier Labeling**: More realistic training labels
- ✅ **Volatility-Targeted Sizing**: Adjusts position size by market volatility
- ✅ **Walk-Forward Validation**: Proper time-series validation (no look-ahead bias)
- ✅ **Slippage & Funding Modeling**: Realistic cost modeling in backtests
- ✅ **Universe Discovery**: Dynamically discovers and filters tradable symbols from Bybit (auto or fixed mode)

### Infrastructure
- ✅ Real-time data streaming via Bybit WebSocket
- ✅ Automated risk management (leverage limits, position sizing, stop-losses)
- ✅ Comprehensive logging and PnL tracking
- ✅ Kill switch for emergency shutdown
- ✅ Testnet support for safe testing
- ✅ Modular, well-documented codebase

## Project Structure

```
ai-bot/
├── config/
│   └── config.yaml          # Configuration file
├── docs/
│   ├── PHASE1_RESEARCH_REPORT.md
│   ├── PHASE2_STRATEGY_DESIGN.md
│   ├── PHASE3_SYSTEM_ARCHITECTURE.md
│   └── PHASE5_VALIDATION.md
├── src/
│   ├── config/              # Configuration management
│   ├── data/                # Data ingestion (historical & live)
│   ├── models/              # Model training
│   ├── signals/             # Signal generation (features, primary, meta)
│   ├── execution/           # Order execution (Bybit API)
│   ├── risk/                # Risk management
│   └── monitoring/          # Logging and PnL tracking
├── models/                  # Trained model artifacts (gitignored)
├── data/                    # Historical data (gitignored)
├── logs/                    # Log files (gitignored)
├── train_model.py           # Model training script
├── live_bot.py              # Live trading bot
├── requirements.txt         # Python dependencies
└── README.md
```

## Quick Start (One-Line Installer)

**For Ubuntu/Debian servers:**

```bash
git clone <repo-url>
cd ai-bot
bash install.sh
```

The installer will:
- Install system dependencies (Python, build tools, etc.)
- Create and configure Python virtual environment
- Install all Python packages
- Prompt for Bybit API keys and configuration
- Set up `.env` file with your settings
- Optionally configure systemd services
- Guide you through next steps

**Note:** The installer does **NOT** automatically start live trading. You must:
1. Complete testnet validation (2+ weeks minimum)
2. Review configuration and safety settings
3. Manually start the bot when ready

**See `docs/FIRST_DEPLOYMENT_BUNDLE.md` for the complete deployment path.**

---

## Manual Setup (Alternative)

If you prefer manual setup or are not on Ubuntu/Debian:

### Prerequisites

- Python 3.10 or higher
- Bybit account (for API keys)
- Testnet API keys (recommended for initial testing)

### Installation

1. **Clone the repository** (or navigate to project directory):
   ```bash
   cd ai-bot
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   
   Create a `.env` file in the project root:
   ```bash
   BYBIT_API_KEY=your_testnet_api_key_here
   BYBIT_API_SECRET=your_testnet_api_secret_here
   BYBIT_TESTNET=true
   ```
   
   **Important**: Get testnet API keys from https://testnet.bybit.com/

5. **Configure the bot**:
   
   Edit `config/config.yaml` to adjust:
   - Trading symbols
   - Risk parameters (leverage, position sizes, stop-losses)
   - Model confidence threshold
   - Feature settings

## Usage

### Step 1: Train the Model

Before running the live bot, you need to train the meta-model on historical data:

```bash
python train_model.py --symbol BTCUSDT --days 730 --version 1.0
```

This will:
- Download historical data from Bybit
- Calculate technical indicators
- Generate training labels by simulating trades
- Train an XGBoost meta-model
- Save model artifacts to `models/`

**Options:**
- `--symbol`: Trading symbol (default: BTCUSDT)
- `--days`: Number of days of history (default: 730)
- `--version`: Model version (default: 1.0)
- `--config`: Config file path (default: config/config.yaml)

### Step 2: Run the Live Bot

**⚠️ IMPORTANT: Start with testnet!**

```bash
python live_bot.py
```

The bot will:
- Load the trained model
- Connect to Bybit WebSocket for live data
- Generate signals and execute trades
- Monitor positions and manage risk
- Log all activity

**Stop the bot**: Press `Ctrl+C`

### Step 3: Monitor Performance

Check log files in `logs/`:
- `logs/trades_YYYYMMDD.jsonl`: Trade logs
- `logs/bot_YYYYMMDD.log`: Bot activity logs
- `logs/training_YYYYMMDD.log`: Training logs

## Configuration

### Key Configuration Parameters

**Risk Management** (`config/config.yaml`):
```yaml
risk:
  max_leverage: 3.0              # Maximum leverage
  max_position_size: 0.10        # 10% of equity per position
  max_daily_loss: 0.05           # 5% daily loss limit
  base_position_size: 0.02       # 2% base position size
  stop_loss_pct: 0.02           # 2% stop loss
  take_profit_pct: 0.03         # 3% take profit
```

**Model Settings**:
```yaml
model:
  confidence_threshold: 0.6      # Minimum confidence to trade
```

**Trading Settings**:
```yaml
trading:
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
  timeframe: "1h"               # 1-hour candles
```

## Quick Start

**For new users, start here:**

1. **Setup**: Follow `docs/QUICK_START.md`
2. **Testnet**: Test on testnet first (2-4 weeks recommended)
3. **Production**: Use `docs/PRODUCTION_READINESS_CHECKLIST.md` before going live
4. **Operations**: See `docs/OPERATIONS_RUNBOOK.md` for daily operations

**Key Features:**
- ✅ Self-managing (performance guard, regime filter)
- ✅ Automated operations (health checks, alerts, retraining)
- ✅ Research harness for validation
- ✅ Model ensembling for robustness

## Strategy Details

### Primary Signal Generation

The bot generates trend-following signals using:
- **EMA Crossovers**: EMA(9) vs EMA(21)
- **RSI Extremes**: Oversold (< 30) or Overbought (> 70)
- **MACD Crossovers**: MACD line vs signal line

### Meta-Model

The XGBoost meta-model predicts profitability probability using:
- Technical indicators (RSI, MACD, EMAs, ATR, Bollinger Bands, ADX)
- Primary signal strength
- Volume indicators
- Volatility measures
- Time features

Only signals with confidence > threshold (default 0.6, adjusted by performance guard) are executed.

### V2 Enhancements

**Regime Filter:**
- Classifies market into: Trending Up, Trending Down, Ranging, High Volatility
- Blocks trend-following trades in ranging markets (by default)
- Reduces position size in high volatility

**Performance Guard:**
- Monitors recent performance (win rate, drawdown, losing streaks)
- Auto-throttles: REDUCED (50% size, +0.1 confidence) or PAUSED (stop trading)
- Auto-recovers when performance improves

**Volatility Targeting:**
- Adjusts position size inversely with volatility
- Target: 1% daily volatility
- More consistent risk exposure

### Risk Management

- **Position Sizing**: Scaled by meta-model confidence × volatility × performance guard × regime
- **Stop-Loss**: 2% of entry price
- **Take-Profit**: 3% of entry price
- **Daily Loss Limit**: 5% of account equity
- **Kill Switch**: Automatic shutdown if drawdown > 15%
- **Performance Guard**: Auto-throttles during poor performance

## Backtesting

The training script includes a basic backtest during model evaluation. For more comprehensive backtesting, you can:

1. Modify `train_model.py` to add walk-forward validation
2. Use the historical data to simulate trades
3. Calculate performance metrics (Sharpe ratio, profit factor, max drawdown)

## Limitations & Risks

### Known Limitations

1. **Data Quality**: Depends on Bybit API availability and data quality
2. **Model Overfitting**: Risk of overfitting to historical data
3. **Regime Changes**: Model may not adapt to sudden market changes
4. **Transaction Costs**: Fees and slippage can erode profits
5. **Single Exchange**: Only supports Bybit (no multi-exchange arbitrage)

### Main Risks

1. **Market Risk**: Cryptocurrency markets are highly volatile
2. **Leverage Risk**: Leveraged trading amplifies losses
3. **Technical Risk**: API failures, network issues, bugs
4. **Model Risk**: AI models can make poor predictions
5. **Liquidity Risk**: Large orders may experience slippage

## V2.1 Improvements

The bot has been enhanced with evidence-backed improvements and critical fixes:

✅ **Model Ensembling**: XGBoost + Logistic Regression baseline (70/30)  
✅ **Walk-Forward Validation**: Proper time-series validation (no look-ahead bias)  
✅ **Triple-Barrier Labeling**: More realistic training labels  
✅ **Regime Filter**: Avoids trading in unfavorable market conditions  
✅ **Performance Guard**: Auto-throttles risk during drawdowns  
✅ **Volatility Targeting**: Adjusts position size by volatility  
✅ **Slippage & Funding Modeling**: Realistic cost modeling  
✅ **Portfolio Selection**: Cross-sectional symbol selection (optional)  
✅ **Operations Automation**: Auto-retraining, health checks, alerts  
✅ **Critical Bug Fixes**: Ensemble serialization, health check frequency, model paths  

## Further Work

Future enhancements (Tier 3):

1. **Automated Retraining**: Schedule periodic model retraining
2. **Portfolio Risk Aggregation**: Account for correlation between symbols
3. **Monte Carlo Resampling**: Advanced performance evaluation
4. **Health Checks**: Automated system monitoring
5. **Alerting**: Email/Discord notifications
6. **More Data**: Collect funding rate history, order book data

## Troubleshooting

### Model Not Found Error

**Problem**: `FileNotFoundError: Model file not found`

**Solution**: Train the model first using `train_model.py`

### API Authentication Error

**Problem**: `API error: Invalid API key`

**Solution**: 
- Check your `.env` file has correct API keys
- Verify you're using testnet keys for testnet mode
- Ensure API keys have trading permissions

### No Data Downloaded

**Problem**: `No candles fetched`

**Solution**:
- Check internet connection
- Verify Bybit API is accessible
- Try reducing `--days` parameter

### WebSocket Connection Issues

**Problem**: WebSocket disconnects frequently

**Solution**:
- Check network stability
- The bot should auto-reconnect, but monitor logs
- Consider running on a stable server/VPS

## Contributing

This is a research project. Contributions welcome for:
- Bug fixes
- Performance improvements
- Additional strategies
- Better documentation

## License

This project is provided as-is for educational purposes. Use at your own risk.

## References

- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
- Bybit API Documentation: https://bybit-exchange.github.io/docs/
- Research findings: See `docs/PHASE1_RESEARCH_REPORT.md`

## Support

For issues or questions:
1. Check the documentation in `docs/`
2. Review log files in `logs/`
3. Ensure you're using testnet for testing

---

**Remember**: Start with testnet, use small position sizes, and never risk more than you can afford to lose.

