# Bot Review Phase 2: Context Summary

## Current Strategy Overview

The bot implements a **meta-labeling on trend-following** strategy, inspired by Lopez de Prado's "Advances in Financial Machine Learning" (2018). This is a two-stage approach:

1. **Primary Signal Layer**: Generates trend-following signals using technical indicators:
   - EMA crossovers (EMA9 vs EMA21)
   - RSI extremes (oversold < 30, overbought > 70)
   - MACD crossovers
   - Signals are combined using weighted averaging or voting

2. **Meta-Model Layer**: An XGBoost classifier that predicts the probability (0-1) that each primary signal will be profitable. Only signals with confidence > 0.6 (configurable) are executed.

## Training Pipeline

**Data Flow:**
1. Historical OHLCV data is downloaded from Bybit (1-hour candles, minimum 730 days)
2. Technical indicators are calculated (RSI, MACD, EMAs, ATR, Bollinger Bands)
3. Primary signals are generated on historical data
4. For each primary signal:
   - Entry is simulated at the next bar's close price
   - Position is held for a fixed period (4 hours by default)
   - Exit price is the close price after the hold period
   - Net return is calculated: `(exit - entry) / entry - 2 * fee_rate` (0.05% per trade)
   - Label is `1` if net return > 0.5%, else `0`

**Model Training:**
- XGBoost classifier with default hyperparameters (100 trees, max_depth=5, learning_rate=0.1)
- Train/Val/Test split: 60/20/20 (random split, not time-based)
- Features include: technical indicators, primary signal strength, volume ratios, volatility, time features
- Model outputs probability of profitability

**Current Limitations in Training:**
- No walk-forward validation (uses random split, not time-based)
- Fixed hold period (4 hours) - no early exit logic
- Simple binary labeling (profitable/not) - no triple-barrier method
- No funding rate modeling in labels
- No slippage modeling beyond fixed fee rate

## Live Trading Workflow

**Signal Generation:**
1. WebSocket receives new 1-hour candle
2. Features are calculated from latest candle + historical context
3. Primary signal is generated (LONG/SHORT/NEUTRAL)
4. If primary signal exists, meta-model predicts profitability probability
5. If confidence > threshold (0.6), proceed to execution

**Risk Management:**
- Position sizing: `base_size (2%) * confidence` capped at 10% of equity
- Pre-trade checks:
  - Daily loss limit (5% of equity)
  - Max drawdown (15% from peak)
  - Max open positions (3)
  - No duplicate positions in same symbol
- Stop-loss: 2% of entry price
- Take-profit: 3% of entry price
- Trailing stop: Activates after 1% profit, trails 1% below peak

**Execution:**
- Market orders placed via Bybit API
- Stop-loss and take-profit orders set automatically
- Positions monitored every minute
- Exit on stop-loss, take-profit, or signal reversal

**Logging:**
- All signals, orders, and trades logged to JSONL files
- PnL tracked (realized and unrealized)
- Error logging for debugging

## Current Risk Management Features

**Implemented:**
- ✅ Position sizing scaled by confidence
- ✅ Daily loss limit (5%)
- ✅ Maximum drawdown limit (15%)
- ✅ Stop-loss and take-profit orders
- ✅ Kill switch (triggers on drawdown/daily loss/errors)
- ✅ Maximum leverage limit (3x)
- ✅ Maximum open positions (3)

**Missing/Weak:**
- ❌ No dynamic risk adjustment based on recent performance
- ❌ No volatility-based position sizing
- ❌ No regime-based gating (trades in all market conditions)
- ❌ No portfolio-level risk aggregation (trades symbols independently)
- ❌ No correlation awareness between positions
- ❌ No performance-based throttling (reduces size when losing)

## Current Monitoring & Automation

**Implemented:**
- ✅ Trade logging (signals, orders, fills, PnL)
- ✅ Error logging
- ✅ Basic PnL tracking (total, daily, win rate)
- ✅ Kill switch for emergencies

**Missing:**
- ❌ No automated model retraining
- ❌ No model performance monitoring (live vs backtest)
- ❌ No automatic model rollback
- ❌ No health checks or heartbeats
- ❌ No alerting system (email/Discord)
- ❌ No performance guard (auto-throttling based on results)

## Limitations Noted in Phase 5

1. **Data Limitations:**
   - Limited to Bybit's available history
   - No multi-exchange data
   - Single timeframe (1h)

2. **Model Limitations:**
   - Overfitting risk (random split, not walk-forward)
   - No regime adaptation
   - Single model (XGBoost only)
   - Fixed hyperparameters

3. **Market Limitations:**
   - Transaction costs may be underestimated
   - No funding rate in labels
   - No slippage modeling
   - Single exchange

4. **Implementation Limitations:**
   - No portfolio optimization
   - Trades symbols independently
   - No correlation awareness

5. **Operational Limitations:**
   - Requires manual retraining
   - No automated monitoring
   - No self-healing capabilities

## Key Files & Modules

**Core Modules:**
- `src/models/train.py`: Model training pipeline
- `src/signals/primary_signal.py`: Trend-following signal generation
- `src/signals/meta_predictor.py`: Meta-model inference
- `src/signals/features.py`: Feature engineering
- `src/risk/risk_manager.py`: Risk limits and position sizing
- `src/execution/bybit_client.py`: Bybit API integration
- `src/monitoring/trade_logger.py`: Trade logging and PnL tracking
- `live_bot.py`: Main trading bot orchestration
- `train_model.py`: Training script entry point

**Configuration:**
- `config/config.yaml`: All settings (risk, model, features, etc.)

**Documentation:**
- `docs/PHASE1_RESEARCH_REPORT.md`: Research findings
- `docs/PHASE2_STRATEGY_DESIGN.md`: Strategy design
- `docs/PHASE3_SYSTEM_ARCHITECTURE.md`: System architecture
- `docs/PHASE5_VALIDATION.md`: Limitations and risks

## Current State Assessment

**Strengths:**
- Solid theoretical foundation (meta-labeling from Lopez de Prado)
- Modular, well-documented codebase
- Conservative risk management (3x leverage, 2% base size)
- Comprehensive logging
- Testnet support

**Weaknesses:**
- No walk-forward validation (overfitting risk)
- Simple labeling (no triple-barrier)
- No regime filtering (trades in all conditions)
- Static risk management (no dynamic adjustment)
- No automation (manual retraining, no self-management)
- Limited evaluation (no Monte Carlo, no stress tests)

**Risk Points:**
- Model may overfit to historical data
- May trade in unfavorable regimes (ranging/choppy markets)
- No adaptation to changing market conditions
- Transaction costs may be underestimated
- No performance-based risk throttling

---

**Document Date:** December 2025  
**Purpose:** Context for Phase 2 review and improvements

