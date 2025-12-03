# Phase 2: Strategy Design

## Overview

Based on the research findings from Phase 1, this document proposes concrete AI-based trading strategies for Bybit USDT-perpetual futures. The strategies are designed to be:
- **Evidence-inspired** (based on documented successful approaches)
- **Implementable** (reasonable compute and data requirements)
- **Compatible** with Bybit USDT-perp instruments

---

## Strategy 1: Meta-Labeling on Trend-Following Signal

### High-Level Idea

Enhance a traditional trend-following strategy using **meta-labeling** (Lopez de Prado, 2018). The approach uses two models:

1. **Primary Model:** Generates directional signals based on trend-following indicators (e.g., moving average crossovers, momentum)
2. **Meta-Model:** Predicts the probability that each primary signal will be profitable, filtering out low-quality trades

This two-stage approach reduces false positives and improves risk-adjusted returns by only taking trades with high predicted success probability.

### Features / Inputs

**Primary Signal Features:**
- OHLCV data (Open, High, Low, Close, Volume)
- Moving averages (SMA/EMA: 9, 21, 50, 200 periods)
- Momentum indicators (RSI, MACD, Stochastic)
- Volatility measures (ATR, Bollinger Bands width)
- Volume indicators (Volume MA ratio, OBV)

**Meta-Model Features (in addition to above):**
- Primary signal strength (magnitude of trend indicator)
- Time since last signal
- Market regime features (volatility regime, trend strength)
- Funding rate (for perpetuals)
- Open interest change (if available)
- Time-of-day features (hour, day-of-week)

**Target Variable for Meta-Model:**
- Binary label: `1` if the trade would have been profitable (after fees), `0` otherwise
- Profitability threshold: e.g., > 0.5% return after estimated fees

### Model Type

**Primary Model:**
- **Type:** Rule-based or simple ML classifier (e.g., Logistic Regression)
- **Output:** Binary signal (Long/Short/Neutral)

**Meta-Model:**
- **Type:** Gradient Boosting (XGBoost or LightGBM)
- **Rationale:** 
  - Handles non-linear feature interactions
  - Provides probability estimates
  - Fast inference for real-time trading
  - Good performance on tabular data
- **Output:** Probability (0-1) that the primary signal will be profitable

### Training Objective

**Meta-Model:**
- **Task:** Binary classification
- **Label Construction:**
  1. Generate primary signals on historical data
  2. For each signal, simulate entry at next bar
  3. Hold for fixed period (e.g., 4-24 hours) or until exit signal
  4. Calculate realized return (including estimated fees: 0.05% per trade)
  5. Label as `1` if return > threshold (e.g., 0.5%), else `0`
- **Loss Function:** Binary cross-entropy
- **Class Imbalance:** Use class weights or SMOTE if needed

### Evaluation Plan

**Data Split:**
- **Training:** 60% of historical data (e.g., 2020-2022)
- **Validation:** 20% (e.g., 2023)
- **Test:** 20% (e.g., 2024)

**Walk-Forward Validation:**
- Use rolling windows (e.g., 6-month training, 1-month validation)
- Retrain monthly or quarterly
- Prevents look-ahead bias

**Metrics:**
- **Meta-Model:** Precision, Recall, F1-score, ROC-AUC
- **Trading Performance:**
  - Sharpe Ratio (target: > 1.5)
  - Profit Factor (target: > 1.5)
  - Maximum Drawdown (target: < 20%)
  - Win Rate (target: > 45%)
  - Average Win/Loss Ratio
  - Total Return

**Backtest Considerations:**
- Include realistic transaction costs (0.05% per trade)
- Model slippage (0.01-0.02% for market orders)
- Account for funding fees (8-hourly payments on perpetuals)
- Use actual bid/ask prices, not mid-prices

### Risk Controls

- **Maximum Leverage:** 3x (conservative for initial deployment)
- **Position Sizing:** 
  - Base size: 2% of account equity per trade
  - Scale by meta-model confidence: `position_size = base_size * meta_probability`
  - Maximum position: 10% of account equity
- **Daily Loss Limit:** Stop trading if daily loss > 5% of account equity
- **Stop-Loss:** 2% of entry price (trailing stop after 1% profit)
- **Take-Profit:** 3% of entry price (or use meta-model exit signal)
- **Symbol Filters:** Only trade major pairs (BTCUSDT, ETHUSDT) initially
- **Kill Switch:** Automatic shutdown if:
  - Account equity drops > 15% from peak
  - API errors exceed threshold
  - Model confidence drops below threshold

---

## Strategy 2: Regime Classifier with Adaptive Strategies

### High-Level Idea

Classify market regimes (Trending Up, Trending Down, Ranging/Volatile) and apply regime-specific trading strategies. This approach adapts to changing market conditions, avoiding losses during unfavorable regimes.

### Features / Inputs

**Regime Classification Features:**
- Price action (returns over multiple timeframes: 1h, 4h, 24h)
- Volatility (rolling std of returns, ATR)
- Trend strength (ADX, slope of moving averages)
- Volume patterns (volume trend, volume volatility)
- Market structure (higher highs/lows vs lower highs/lows)

**Trading Features (regime-specific):**
- For **Trending Regimes:** Momentum indicators (RSI, MACD, moving average crossovers)
- For **Ranging Regimes:** Mean reversion indicators (Bollinger Bands, RSI extremes)
- For **Volatile Regimes:** Volatility breakouts (ATR-based channels)

### Model Type

**Regime Classifier:**
- **Type:** Random Forest or Gradient Boosting Classifier
- **Output:** Regime probabilities (3 classes: Trending Up, Trending Down, Ranging)

**Trading Models (one per regime):**
- **Trending:** Simple momentum model (e.g., moving average crossover with ML filter)
- **Ranging:** Mean reversion model (e.g., RSI-based with ML confidence)
- **Volatile:** Breakout model (e.g., ATR-based with ML confirmation)

**Alternative:** Single multi-output model that predicts both regime and direction

### Training Objective

**Regime Classifier:**
- **Task:** Multi-class classification
- **Label Construction:**
  - **Trending Up:** Price increased > 5% over 24h with low volatility
  - **Trending Down:** Price decreased > 5% over 24h with low volatility
  - **Ranging:** Price change < 2% over 24h OR high volatility with no clear trend
- **Loss Function:** Categorical cross-entropy

**Trading Models:**
- **Task:** Binary classification (Long/Short) or regression (expected return)
- **Training:** Only use data from the corresponding regime

### Evaluation Plan

**Data Split:** Same as Strategy 1 (60/20/20)

**Regime Classification Metrics:**
- Accuracy, Precision, Recall per regime
- Confusion matrix
- Regime transition analysis

**Trading Performance Metrics:**
- Same as Strategy 1
- **Additional:** Performance breakdown by regime

**Walk-Forward:** Same approach as Strategy 1

### Risk Controls

- **Regime Confidence Threshold:** Only trade if regime probability > 0.6
- **Regime Transition Handling:** Reduce position size during regime transitions
- **Maximum Leverage:** 3x (same as Strategy 1)
- **Position Sizing:** 
  - Base: 2% of equity
  - Adjust by regime confidence
  - Reduce in volatile/ranging regimes
- **Stop-Loss/Take-Profit:** Regime-specific (tighter in ranging, wider in trending)
- **Daily Loss Limit:** 5% of equity
- **Kill Switch:** Same as Strategy 1

---

## Strategy 3: LSTM Sequence Model for Directional Bias

### High-Level Idea

Use LSTM (or Transformer) to learn temporal patterns in price sequences and predict short-term directional bias. Combine with risk filters and position sizing based on model confidence.

### Features / Inputs

**Sequential Features (input to LSTM):**
- Normalized OHLCV sequences (last 60-100 bars)
- Technical indicators as additional features:
  - RSI, MACD, ATR (normalized)
  - Moving averages (normalized)
  - Volume indicators

**Auxiliary Features (concatenated to LSTM output):**
- Current funding rate
- Open interest change
- Volatility regime
- Time features (hour, day-of-week)

### Model Type

**Architecture:**
- **Type:** LSTM or Transformer (e.g., Time Series Transformer)
- **Structure:**
  - Input: (sequence_length, feature_dim)
  - LSTM layers: 2-3 layers, 64-128 units each
  - Dense layers: 2 layers, 32-64 units
  - Output: 3 classes (Long/Neutral/Short) or regression (expected return)
- **Alternative:** Use 1D CNN for feature extraction, then LSTM

### Training Objective

**Task:** Multi-class classification or regression

**Labels:**
- **Classification:** 
  - Long: Next 4-hour return > 1%
  - Short: Next 4-hour return < -1%
  - Neutral: Otherwise
- **Regression:** Predict next 4-hour return directly

**Loss Function:**
- Classification: Categorical cross-entropy
- Regression: MSE or Huber loss

### Evaluation Plan

**Data Split:** Same as previous strategies

**Metrics:**
- **Model:** Accuracy, Precision, Recall (classification) or MAE, RMSE (regression)
- **Trading:** Same as Strategy 1

**Walk-Forward:** Same approach

### Risk Controls

- **Confidence Threshold:** Only trade if predicted probability > 0.55 (for classification)
- **Maximum Leverage:** 3x
- **Position Sizing:** Scale by model confidence
- **Stop-Loss/Take-Profit:** 2%/3% (same as Strategy 1)
- **Daily Loss Limit:** 5% of equity
- **Sequence Length:** Use fixed lookback (e.g., 60 bars) to avoid variable-length issues

---

## Strategy Selection: Most Promising Strategy

### Selected Strategy: **Strategy 1 - Meta-Labeling on Trend-Following**

### Justification:

1. **Evidence-Backed:**
   - Meta-labeling is well-documented in Lopez de Prado's "Advances in Financial Machine Learning"
   - Has been used successfully in quantitative finance
   - Two-stage approach reduces overfitting risk

2. **Robustness:**
   - Primary model is simple and interpretable (trend-following)
   - Meta-model filters out bad signals, improving risk-adjusted returns
   - Less prone to overfitting than complex deep learning models

3. **Simplicity vs. Complexity:**
   - Moderate complexity: understandable but not overly simple
   - Easier to debug and interpret than LSTM/Transformer models
   - Faster inference (important for real-time trading)

4. **Ease of Deployment:**
   - XGBoost models are lightweight and fast
   - No need for GPU inference
   - Easy to retrain and update
   - Can be deployed on standard servers

5. **Past Documented Results:**
   - Meta-labeling has shown success in equity markets
   - Trend-following is a well-established strategy
   - Combination should be more robust than either alone

6. **Risk Management:**
   - Meta-model provides natural confidence scores for position sizing
   - Can easily implement risk controls based on meta-probability
   - Interpretable features allow for manual oversight

### Implementation Priority:

1. **Primary:** Strategy 1 (Meta-Labeling)
2. **Secondary (future work):** Strategy 2 (Regime Classification) - can be added as enhancement
3. **Tertiary (research):** Strategy 3 (LSTM) - more experimental, requires more data/compute

---

## Strategy Implementation Details

### Data Requirements

**Historical Data:**
- **Symbols:** BTCUSDT, ETHUSDT (start with major pairs)
- **Timeframe:** 1-hour candles (primary), 4-hour for trend confirmation
- **History:** Minimum 2 years (2022-2024) for training
- **Data Source:** Bybit API (historical candles endpoint)

**Live Data:**
- **Streaming:** Bybit WebSocket API (kline stream)
- **Update Frequency:** Every 1 hour (or on new candle close)
- **Additional Data:**
  - Funding rate (8-hourly)
  - Open interest (if available)
  - 24h ticker data (for volume/price change)

### Feature Engineering Pipeline

1. **OHLCV Processing:**
   - Calculate returns (1h, 4h, 24h)
   - Calculate volatility (rolling std)
   - Normalize features (z-score or min-max)

2. **Technical Indicators:**
   - Moving averages (SMA, EMA)
   - Momentum (RSI, MACD, Stochastic)
   - Volatility (ATR, Bollinger Bands)
   - Volume (OBV, Volume MA ratio)

3. **Primary Signal Generation:**
   - Moving average crossover (e.g., EMA(9) > EMA(21) = Long signal)
   - RSI extremes (e.g., RSI < 30 = Long signal)
   - MACD crossover
   - Combine signals with simple voting or weighted average

4. **Meta-Model Features:**
   - All technical indicators
   - Primary signal strength
   - Time features
   - Funding rate
   - Market regime indicators

### Model Training Workflow

1. **Data Collection:** Download historical candles from Bybit
2. **Feature Engineering:** Calculate all features
3. **Label Generation:** Simulate trades and calculate profitability labels
4. **Primary Model Training:** Train simple trend-following rules
5. **Meta-Model Training:** Train XGBoost on meta-features
6. **Validation:** Walk-forward backtest
7. **Model Selection:** Choose best hyperparameters based on validation Sharpe
8. **Final Evaluation:** Test on hold-out set
9. **Model Export:** Save model artifacts (joblib/pickle)

### Signal Generation (Live Trading)

1. **Receive New Candle:** From WebSocket stream
2. **Calculate Features:** Update all technical indicators
3. **Generate Primary Signal:** Apply trend-following rules
4. **Meta-Model Prediction:** If primary signal exists, predict profitability probability
5. **Decision:**
   - If meta-probability > threshold (e.g., 0.6) → Execute trade
   - Else → Skip trade
6. **Position Sizing:** Scale by meta-probability
7. **Risk Check:** Verify within risk limits
8. **Order Placement:** Place order via Bybit API

### Risk Management Integration

- **Pre-Trade Checks:**
  - Verify daily loss limit not exceeded
  - Check position size within limits
  - Verify leverage within limits
  - Check symbol is allowed

- **Post-Trade Monitoring:**
  - Track open positions
  - Monitor stop-loss/take-profit levels
  - Update PnL tracking
  - Log all trades

- **Emergency Controls:**
  - Kill switch if account equity drops > 15%
  - Stop trading if API errors exceed threshold
  - Manual override capability

---

## Next Steps

1. **Phase 3:** Design system architecture to support Strategy 1
2. **Phase 4:** Implement complete trading bot with Strategy 1
3. **Future Enhancements:**
   - Add Strategy 2 (regime classification) as optional filter
   - Experiment with Strategy 3 (LSTM) in research mode
   - Multi-symbol support
   - Portfolio-level risk management

---

**Document Date:** December 2025  
**Strategy Version:** 1.0  
**Status:** Ready for Implementation

