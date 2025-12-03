# Phase 3: System Architecture & Implementation Plan

## Overview

This document outlines the architecture of a production-ready Bybit AI trading bot implementing the Meta-Labeling on Trend-Following strategy (Strategy 1 from Phase 2). The system is designed for reliability, maintainability, and robust risk management.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         TRADING BOT SYSTEM                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Data       │         │   Model      │         │   Signal     │
│  Ingestion   │────────▶│   Training   │────────▶│  Generation  │
└──────────────┘         └──────────────┘         └──────────────┘
       │                         │                         │
       │                         │                         │
       ▼                         ▼                         ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Storage    │         │   Model      │         │   Execution  │
│  (Historical)│         │   Artifacts  │         │   Engine     │
└──────────────┘         └──────────────┘         └──────────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────┐
                                                  │     Risk     │
                                                  │  Management  │
                                                  └──────────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────┐
                                                  │  Monitoring  │
                                                  │   & Logging  │
                                                  └──────────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────┐
                                                  │    Bybit     │
                                                  │     API      │
                                                  └──────────────┘
```

---

## Component Architecture

### 1. Data Ingestion & Storage

#### 1.1 Historical Data Collection

**Purpose:** Download and store historical OHLCV data for model training

**Components:**
- **Module:** `src/data/historical_data.py`
- **Functionality:**
  - Connect to Bybit REST API
  - Download historical candles (1h, 4h timeframes)
  - Store in local database (SQLite) or parquet files
  - Handle rate limits and retries
  - Support incremental updates

**Data Schema:**
```python
Candle(
    symbol: str,
    timestamp: datetime,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    timeframe: str  # '1h', '4h'
)
```

**Storage:**
- **Format:** Parquet files (partitioned by symbol and date) OR SQLite database
- **Location:** `data/historical/`
- **Retention:** Keep at least 2 years of data

#### 1.2 Live Data Streaming

**Purpose:** Receive real-time market data for signal generation

**Components:**
- **Module:** `src/data/live_data.py`
- **Functionality:**
  - Connect to Bybit WebSocket API (kline stream)
  - Subscribe to relevant symbols (BTCUSDT, ETHUSDT)
  - Buffer incoming candles
  - Handle reconnections and errors
  - Provide data to signal generation module

**WebSocket Streams:**
- Kline stream: `wss://stream.bybit.com/v5/public/linear`
- Ticker stream: For 24h statistics
- Funding rate stream: For funding rate updates

**Data Flow:**
```
WebSocket → Buffer → Feature Calculator → Signal Generator
```

---

### 2. Model Training

#### 2.1 Training Pipeline

**Purpose:** Train primary and meta-models offline

**Components:**
- **Module:** `src/models/train.py`
- **Script:** `train_model.py` (entry point)

**Workflow:**
1. **Data Loading:**
   - Load historical candles from storage
   - Filter by symbol and date range
   - Handle missing data

2. **Feature Engineering:**
   - Calculate technical indicators
   - Generate primary signals
   - Create meta-model features
   - Normalize features

3. **Label Generation:**
   - Simulate trades based on primary signals
   - Calculate realized returns (including fees)
   - Generate binary labels (profitable/not profitable)

4. **Model Training:**
   - Split data: train/validation/test
   - Train meta-model (XGBoost)
   - Hyperparameter tuning (grid search or optuna)
   - Cross-validation

5. **Evaluation:**
   - Walk-forward backtest
   - Calculate performance metrics
   - Generate reports

6. **Model Persistence:**
   - Save trained model (joblib format)
   - Save feature scaler
   - Save feature names list
   - Save metadata (training date, performance metrics)

**Output:**
- Model file: `models/meta_model_v1.0.joblib`
- Scaler: `models/feature_scaler_v1.0.joblib`
- Config: `models/model_config_v1.0.json`

#### 2.2 Model Artifacts

**Structure:**
```
models/
├── meta_model_v1.0.joblib          # Trained XGBoost model
├── feature_scaler_v1.0.joblib       # Feature scaler
├── model_config_v1.0.json          # Model metadata
└── training_report_v1.0.html       # Training report
```

**Model Metadata:**
```json
{
    "version": "1.0",
    "training_date": "2025-12-03",
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "timeframe": "1h",
    "features": ["rsi", "macd", "ema_9", ...],
    "performance": {
        "sharpe_ratio": 1.85,
        "profit_factor": 1.72,
        "max_drawdown": 0.15,
        "win_rate": 0.48
    }
}
```

---

### 3. Signal Generation

#### 3.1 Feature Calculation

**Purpose:** Calculate features in real-time from live market data

**Components:**
- **Module:** `src/signals/features.py`
- **Functionality:**
  - Maintain rolling window of candles (for indicators)
  - Calculate technical indicators (RSI, MACD, moving averages, etc.)
  - Calculate primary signal (trend-following rules)
  - Prepare features for meta-model

**Indicators:**
- Moving averages (SMA, EMA)
- Momentum (RSI, MACD, Stochastic)
- Volatility (ATR, Bollinger Bands)
- Volume (OBV, Volume ratios)
- Custom features (funding rate, time features)

#### 3.2 Primary Signal Generation

**Purpose:** Generate trend-following signals

**Components:**
- **Module:** `src/signals/primary_signal.py`
- **Rules:**
  - EMA(9) > EMA(21) → Long signal
  - EMA(9) < EMA(21) → Short signal
  - RSI < 30 → Long signal
  - RSI > 70 → Short signal
  - MACD crossover → Directional signal
  - Combine signals with voting or weighted average

**Output:**
```python
PrimarySignal(
    direction: str,  # 'LONG', 'SHORT', 'NEUTRAL'
    strength: float,  # 0.0 to 1.0
    timestamp: datetime
)
```

#### 3.3 Meta-Model Inference

**Purpose:** Predict profitability probability of primary signals

**Components:**
- **Module:** `src/signals/meta_predictor.py`
- **Functionality:**
  - Load trained meta-model
  - Load feature scaler
  - Build feature vector from current market state
  - Predict profitability probability
  - Return signal with confidence

**Output:**
```python
TradingSignal(
    direction: str,  # 'LONG', 'SHORT', 'NEUTRAL'
    confidence: float,  # 0.0 to 1.0 (meta-model probability)
    primary_signal: PrimarySignal,
    timestamp: datetime,
    features: dict  # For logging/debugging
)
```

**Decision Logic:**
```python
if signal.confidence > CONFIDENCE_THRESHOLD (0.6):
    execute_trade(signal)
else:
    skip_trade()
```

---

### 4. Execution Engine

#### 4.1 Order Management

**Purpose:** Translate signals into orders and manage execution

**Components:**
- **Module:** `src/execution/order_manager.py`
- **Functionality:**
  - Calculate position size based on signal confidence
  - Determine entry price (market or limit)
  - Place orders via Bybit API
  - Handle partial fills
  - Update order status
  - Cancel orders if needed

**Order Types:**
- **Market Orders:** For immediate execution (higher slippage)
- **Limit Orders:** For better prices (may not fill)
- **Stop-Loss Orders:** Automatic risk management
- **Take-Profit Orders:** Lock in profits

**Position Sizing:**
```python
base_size = account_equity * 0.02  # 2% base
confidence_multiplier = signal.confidence  # 0.6 to 1.0
position_size = base_size * confidence_multiplier
position_size = min(position_size, max_position_size)  # Cap at 10%
```

#### 4.2 Bybit API Integration

**Purpose:** Interface with Bybit exchange

**Components:**
- **Module:** `src/execution/bybit_client.py`
- **Library:** `pybit` (official Bybit Python SDK) or `ccxt`
- **Functionality:**
  - Authentication (API key/secret)
  - Place orders (POST /v5/order/create)
  - Cancel orders (POST /v5/order/cancel)
  - Query positions (GET /v5/position/list)
  - Query account info (GET /v5/account/wallet-balance)
  - Handle rate limits (120 requests/minute)
  - Error handling and retries

**API Endpoints Used:**
- `POST /v5/order/create` - Create order
- `POST /v5/order/cancel` - Cancel order
- `GET /v5/position/list` - Get open positions
- `GET /v5/account/wallet-balance` - Get account balance
- `GET /v5/market/kline` - Get historical candles (for training)

#### 4.3 Entry/Exit Logic

**Purpose:** Define when to enter and exit trades

**Components:**
- **Module:** `src/execution/trade_logic.py`

**Entry Rules:**
- Signal confidence > threshold (0.6)
- No existing position in same direction
- Risk limits not exceeded
- Market is open (no maintenance)

**Exit Rules:**
- **Stop-Loss:** Price moves against position by 2%
- **Take-Profit:** Price moves in favor by 3%
- **Trailing Stop:** After 1% profit, trail stop at 1% below peak
- **Signal Reversal:** Primary signal changes direction
- **Time-Based:** Exit after 24 hours (optional)

**Order Flow:**
```
Signal → Risk Check → Position Size Calc → Place Entry Order
  ↓
Monitor Position → Check Stop-Loss/Take-Profit → Place Exit Order
```

---

### 5. Risk & Capital Management

#### 5.1 Risk Limits

**Purpose:** Enforce risk controls to prevent catastrophic losses

**Components:**
- **Module:** `src/risk/risk_manager.py`

**Risk Parameters:**
```python
MAX_LEVERAGE = 3.0
MAX_POSITION_SIZE = 0.10  # 10% of equity per position
MAX_DAILY_LOSS = 0.05  # 5% of equity per day
MAX_DRAWDOWN = 0.15  # 15% from peak equity
MAX_OPEN_POSITIONS = 3  # Maximum concurrent positions
```

**Pre-Trade Checks:**
- Verify daily loss limit not exceeded
- Check position size within limits
- Verify leverage within limits
- Check symbol is allowed
- Verify account has sufficient margin

**Post-Trade Monitoring:**
- Track open positions
- Monitor account equity
- Calculate current drawdown
- Check if kill switch should trigger

#### 5.2 Position Management

**Purpose:** Track and manage open positions

**Components:**
- **Module:** `src/risk/position_manager.py`

**Position Tracking:**
```python
Position(
    symbol: str,
    direction: str,  # 'LONG' or 'SHORT'
    entry_price: float,
    size: float,
    leverage: float,
    stop_loss: float,
    take_profit: float,
    entry_time: datetime,
    unrealized_pnl: float
)
```

**Functions:**
- Add new position
- Update position PnL
- Close position
- Check position limits
- Calculate portfolio risk

#### 5.3 Kill Switch

**Purpose:** Emergency shutdown mechanism

**Components:**
- **Module:** `src/risk/kill_switch.py`

**Trigger Conditions:**
- Account equity drops > 15% from peak
- Daily loss exceeds 5% of equity
- API errors exceed threshold (e.g., 10 errors in 1 minute)
- Manual kill switch activation
- Model confidence consistently low

**Actions:**
- Cancel all open orders
- Close all positions (if configured)
- Stop signal generation
- Send alert notification
- Log emergency event

---

### 6. Monitoring & Logging

#### 6.1 Trade Logging

**Purpose:** Record all trading activity

**Components:**
- **Module:** `src/monitoring/trade_logger.py`

**Logged Events:**
- Signal generation (with features and confidence)
- Order placement (entry/exit)
- Order fills (partial or full)
- Position opens/closes
- Stop-loss/take-profit hits
- Errors and exceptions

**Log Format:**
```json
{
    "timestamp": "2025-12-03T10:30:00Z",
    "event": "ORDER_PLACED",
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "size": 0.05,
    "price": 45000.0,
    "order_id": "abc123",
    "confidence": 0.75
}
```

**Storage:**
- **Format:** JSON lines file or SQLite database
- **Location:** `logs/trades/`
- **Rotation:** Daily log files

#### 6.2 PnL Tracking

**Purpose:** Track performance metrics

**Components:**
- **Module:** `src/monitoring/pnl_tracker.py`

**Metrics Tracked:**
- Realized PnL (closed trades)
- Unrealized PnL (open positions)
- Total PnL
- Daily PnL
- Win rate
- Average win/loss
- Sharpe ratio (rolling)
- Maximum drawdown
- Profit factor

**Reporting:**
- Real-time dashboard (optional)
- Daily summary report
- Performance charts

#### 6.3 Error Logging

**Purpose:** Log errors and system events

**Components:**
- **Module:** `src/monitoring/error_logger.py`

**Logged Events:**
- API errors
- Network errors
- Model prediction errors
- Risk limit violations
- Kill switch activations

**Log Levels:**
- DEBUG: Detailed information
- INFO: General information
- WARNING: Potential issues
- ERROR: Errors that don't stop execution
- CRITICAL: Fatal errors requiring shutdown

**Storage:**
- **Format:** JSON lines or structured logs
- **Location:** `logs/errors/`
- **Rotation:** Daily or by size

---

## Data Flow

### Training Flow

```
Historical Data → Feature Engineering → Label Generation
       ↓
Train/Val/Test Split → Model Training → Evaluation
       ↓
Model Persistence → Model Artifacts
```

### Live Trading Flow

```
WebSocket Stream → Feature Calculation → Primary Signal
       ↓
Meta-Model Inference → Trading Signal
       ↓
Risk Check → Position Sizing → Order Placement
       ↓
Bybit API → Order Execution
       ↓
Position Monitoring → Exit Logic → Order Closure
       ↓
PnL Tracking → Logging
```

---

## Technology Stack

### Core Libraries

- **Python:** 3.10+
- **Data Processing:**
  - `pandas`: Data manipulation
  - `numpy`: Numerical computations
- **Machine Learning:**
  - `xgboost`: Meta-model (or `lightgbm`)
  - `scikit-learn`: Feature scaling, utilities
- **Exchange API:**
  - `pybit`: Bybit official Python SDK (or `ccxt`)
  - `websocket-client`: WebSocket connections
- **Utilities:**
  - `python-dotenv`: Environment variables
  - `pyyaml`: Configuration files
  - `ta-lib` or `pandas-ta`: Technical indicators
- **Logging:**
  - `loguru`: Enhanced logging
- **Testing:**
  - `pytest`: Unit tests

### Infrastructure

- **Storage:**
  - Local filesystem (Parquet/SQLite) for historical data
  - JSON files for configuration
- **Deployment:**
  - Can run on local machine or cloud server
  - Docker containerization (optional)
- **Monitoring:**
  - Log files (can integrate with external monitoring tools)

---

## Configuration Management

### Configuration File Structure

**File:** `config/config.yaml`

```yaml
# Exchange Settings
exchange:
  name: "bybit"
  testnet: true  # Use testnet for initial testing
  api_key: "${BYBIT_API_KEY}"  # From environment
  api_secret: "${BYBIT_API_SECRET}"  # From environment

# Trading Settings
trading:
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
  timeframe: "1h"
  base_timeframe: "1h"
  confirmation_timeframe: "4h"

# Model Settings
model:
  version: "1.0"
  path: "models/meta_model_v1.0.joblib"
  scaler_path: "models/feature_scaler_v1.0.joblib"
  confidence_threshold: 0.6

# Risk Management
risk:
  max_leverage: 3.0
  max_position_size: 0.10  # 10% of equity
  max_daily_loss: 0.05  # 5% of equity
  max_drawdown: 0.15  # 15% from peak
  max_open_positions: 3
  base_position_size: 0.02  # 2% base size
  stop_loss_pct: 0.02  # 2% stop loss
  take_profit_pct: 0.03  # 3% take profit

# Feature Engineering
features:
  indicators:
    - "rsi"
    - "macd"
    - "ema_9"
    - "ema_21"
    - "ema_50"
    - "atr"
    - "bollinger_bands"
  lookback_periods:
    rsi: 14
    macd_fast: 12
    macd_slow: 26
    macd_signal: 9

# Data Settings
data:
  historical_data_path: "data/historical"
  min_history_days: 730  # 2 years
  update_frequency: 3600  # 1 hour in seconds

# Logging
logging:
  level: "INFO"
  trade_log_path: "logs/trades"
  error_log_path: "logs/errors"
  pnl_log_path: "logs/pnl"
```

### Environment Variables

**File:** `.env` (not committed to git)

```bash
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true
```

---

## Error Handling & Resilience

### API Error Handling

- **Rate Limits:** Implement exponential backoff
- **Network Errors:** Retry with jitter
- **Authentication Errors:** Log and alert
- **Invalid Orders:** Validate before submission

### Data Quality

- **Missing Data:** Interpolate or skip
- **Stale Data:** Check timestamps, reconnect if needed
- **Outliers:** Filter extreme values

### Model Errors

- **Prediction Failures:** Fall back to neutral signal
- **Feature Calculation Errors:** Log and skip signal
- **Model Loading Errors:** Shutdown gracefully

---

## Security Considerations

1. **API Keys:**
   - Store in environment variables, never in code
   - Use read-only keys if possible (for data collection)
   - Rotate keys regularly

2. **Code Security:**
   - Don't commit secrets to git
   - Use `.gitignore` for sensitive files
   - Review dependencies for vulnerabilities

3. **Risk Limits:**
   - Enforce strict risk limits
   - Implement kill switches
   - Monitor for unusual activity

---

## Deployment Considerations

### Development Environment

- Run on local machine
- Use Bybit testnet
- Paper trading mode (no real orders)

### Production Environment

- Deploy on reliable server (cloud or dedicated)
- Use mainnet (after thorough testing)
- Enable all monitoring and alerts
- Set up automated backups
- Implement health checks

### Scaling

- Can run multiple symbols in parallel
- Each symbol can have independent risk limits
- Portfolio-level risk aggregation

---

## Next Steps

1. **Phase 4:** Implement code according to this architecture
2. **Testing:** Unit tests for each module
3. **Integration:** End-to-end testing on testnet
4. **Documentation:** Code comments and docstrings
5. **Deployment:** Production deployment guide

---

**Document Date:** December 2025  
**Architecture Version:** 1.0  
**Status:** Ready for Implementation

