# Phase 6: V2 System Design

## Overview

This document describes the v2 architecture and strategy stack for the Bybit AI trading bot. The design preserves the core meta-labeling on trend-following approach while adding evidence-backed enhancements to improve robustness, profitability potential, and self-management capabilities.

---

## Design Principles

1. **Preserve Core**: Keep meta-labeling + trend-following foundation
2. **Evidence-Backed**: Only add improvements with solid research support
3. **Backward Compatible**: Existing configs and models should still work
4. **Self-Managing**: Minimize human intervention
5. **Risk-First**: Prioritize risk control over returns

---

## New Components & Changes

### 1. Regime Filter Module

**New Module:** `src/signals/regime_filter.py`

**Purpose:** Classify market regimes and gate trend-following entries

**Regime Classification:**
- **Trending Up**: ADX > 25, price > EMA(50), positive momentum
- **Trending Down**: ADX > 25, price < EMA(50), negative momentum
- **Ranging**: ADX < 25, low volatility, sideways price action
- **High Volatility**: ATR > 2x rolling average, extreme moves

**Decision Logic:**
```python
if regime == "Trending Up" or regime == "Trending Down":
    if trend_following_signal:
        allow_trade = True
        position_size_multiplier = 1.0
elif regime == "Ranging":
    allow_trade = False  # Don't trade trend-following in ranging
elif regime == "High Volatility":
    allow_trade = True  # But with reduced size
    position_size_multiplier = 0.5
```

**Integration:**
- Called in `live_bot.py` before meta-model prediction
- If regime doesn't allow trading, skip signal entirely

---

### 2. Performance Guard Module

**New Module:** `src/risk/performance_guard.py`

**Purpose:** Monitor recent performance and automatically throttle risk

**Metrics Tracked:**
- Rolling PnL (last 10 trades)
- Rolling win rate (last 20 trades)
- Current drawdown from peak
- Days since last profitable trade

**Throttling Tiers:**

**Tier 1 - Normal:**
- Position size: 100% of calculated size
- Confidence threshold: Base threshold (0.6)
- Status: Full trading

**Tier 2 - Reduced Risk:**
- Triggers: Win rate < 40% OR last 5 trades losing OR drawdown > 5%
- Position size: 50% of calculated size
- Confidence threshold: Base + 0.1 (0.7)
- Status: Continue trading but reduced

**Tier 3 - Paused:**
- Triggers: Win rate < 30% OR last 10 trades losing OR drawdown > 10%
- Position size: 0%
- Confidence threshold: N/A
- Status: Stop trading until recovery

**Recovery Conditions:**
- Win rate > 45% for last 10 trades
- Drawdown recovers to < 5%
- 3 consecutive profitable trades

**Integration:**
- Called in `live_bot.py` after risk checks, before order placement
- Overrides position size and confidence threshold

---

### 3. Enhanced Label Generation (Triple-Barrier)

**Modified Module:** `src/models/train.py`

**Changes:**
- Replace simple hold-period logic with triple-barrier method
- Track which barrier was hit (profit, loss, time)

**Barrier Logic:**
```python
# For each primary signal:
entry_price = next_bar_close
profit_barrier = entry_price * (1 + profit_pct)  # e.g., +2%
loss_barrier = entry_price * (1 - loss_pct)      # e.g., -1%
time_barrier = entry_time + max_hold_hours       # e.g., 24h

# Check each bar until barrier hit:
for bar in bars_after_entry:
    if bar.high >= profit_barrier:  # LONG
        label = 1  # Profitable
        barrier_hit = "profit"
        break
    elif bar.low <= loss_barrier:  # LONG
        label = 0  # Loss
        barrier_hit = "loss"
        break
    elif bar.timestamp >= time_barrier:
        label = 0  # Timeout (neutral/unprofitable)
        barrier_hit = "time"
        break
```

**Benefits:**
- Models actual stop-loss/take-profit behavior
- More realistic labels
- Better alignment with live trading

---

### 4. Walk-Forward Evaluation Module

**New Module:** `src/models/evaluation.py`

**Purpose:** Proper time-series validation and backtesting

**Walk-Forward Logic:**
```python
# Rolling window approach:
train_window = 180 days  # 6 months
test_window = 30 days    # 1 month
step = 30 days          # Roll forward 1 month

for start_date in date_range:
    train_end = start_date + train_window
    test_start = train_end
    test_end = test_start + test_window
    
    # Train on train period
    model = train_model(data[train_start:train_end])
    
    # Test on test period
    metrics = backtest(model, data[test_start:test_end])
    
    # Roll forward
    start_date += step
```

**Metrics Calculated:**
- Sharpe ratio
- Profit factor
- Maximum drawdown
- Win rate
- Average win/loss ratio
- Total return

**Output:**
- Performance metrics per fold
- Aggregate statistics (mean, std, min, max)
- Confidence intervals

---

### 5. Enhanced Feature Engineering

**Modified Module:** `src/signals/features.py`

**New Features:**
- **ADX**: Average Directional Index (trend strength)
- **Funding rate**: Current funding rate and 8h change
- **Volatility regime**: High/medium/low based on ATR percentiles
- **Regime features**: Regime probabilities from regime filter

**Funding Rate Integration:**
- Fetch from Bybit API (8-hourly)
- Include in label calculation (subtract from returns)
- Add as feature (current rate, rate change, rate trend)

---

### 6. Volatility-Targeted Position Sizing

**Modified Module:** `src/risk/risk_manager.py`

**Changes:**
- Add volatility calculation (20-day ATR or rolling std)
- Scale position size by volatility: `size = base_size * (target_vol / current_vol)`
- Target volatility: 1% daily (configurable)

**Formula:**
```python
current_vol = calculate_volatility(df, period=20)  # e.g., 2% daily
target_vol = 0.01  # 1% daily
volatility_multiplier = min(target_vol / current_vol, 2.0)  # Cap at 2x
adjusted_size = base_size * confidence * volatility_multiplier
```

---

### 7. Slippage & Funding Modeling

**Modified Module:** `src/models/train.py`

**Changes:**
- Add slippage to entry/exit prices
- Add funding costs to returns
- Volatility-adjusted slippage

**Slippage Model:**
```python
base_slippage = 0.0001  # 0.01%
volatility_factor = current_vol / average_vol  # e.g., 1.5x in high vol
slippage = base_slippage * volatility_factor

entry_price = close_price * (1 + slippage)  # LONG
exit_price = close_price * (1 - slippage)   # LONG
```

**Funding Model:**
```python
funding_rate = get_funding_rate(symbol, timestamp)  # e.g., 0.0001 (0.01%)
hold_hours = 24
funding_cost = funding_rate * (hold_hours / 8)  # 8-hourly payments

net_return = gross_return - (2 * fee_rate) - funding_cost - slippage
```

---

## Data & Feature Updates

### New Data Sources
- **Funding rate**: Fetch from Bybit API (historical and live)
- **ADX calculation**: Add to technical indicators

### Feature Additions
- ADX (trend strength)
- Funding rate (current, change, trend)
- Volatility regime (high/medium/low)
- Regime probabilities
- Volatility-adjusted features

### Feature Engineering Pipeline
1. Calculate standard indicators (RSI, MACD, EMAs, etc.)
2. Calculate ADX (new)
3. Fetch funding rate (new)
4. Classify regime (new)
5. Calculate volatility (enhanced)
6. Build meta-features (includes new features)

---

## Decision Logic Flow

### Signal Generation (Enhanced)

```
1. Receive new candle
2. Calculate features (including ADX, funding, volatility)
3. Classify regime
   → If regime == "Ranging": SKIP (don't trade trend-following)
   → If regime == "High Volatility": Continue with reduced size flag
4. Generate primary signal (trend-following)
5. If primary signal exists:
   a. Check regime allows trading
   b. Get performance guard status
   c. Predict meta-model probability
   d. Apply performance guard adjustments (confidence threshold, size multiplier)
   e. If confidence > adjusted_threshold: Proceed
6. Calculate position size:
   a. Base size * confidence
   b. Apply volatility multiplier
   c. Apply performance guard multiplier
   d. Apply regime multiplier (if high vol)
7. Risk checks (existing)
8. Execute trade
```

### Position Sizing (Enhanced)

```
base_size = equity * 0.02  # 2%
confidence_multiplier = meta_confidence  # 0.6-1.0
volatility_multiplier = target_vol / current_vol  # e.g., 0.5-2.0
performance_multiplier = guard.get_size_multiplier()  # 0.0-1.0
regime_multiplier = 1.0 if normal, 0.5 if high_vol

final_size = base_size * confidence_multiplier * volatility_multiplier * 
             performance_multiplier * regime_multiplier
final_size = min(final_size, max_position_size)
```

### Risk Throttling (New)

```
if performance_guard.status == "PAUSED":
    return  # Don't trade
elif performance_guard.status == "REDUCED":
    confidence_threshold += 0.1
    position_size_multiplier = 0.5
elif performance_guard.status == "NORMAL":
    # No adjustments
```

---

## Model Lifecycle

### Training → Validation → Promotion

**Step 1: Training**
- Download latest historical data
- Generate labels using triple-barrier method
- Train model with walk-forward validation
- Evaluate on out-of-sample period

**Step 2: Validation**
- Test on hold-out period (last 30-60 days)
- Calculate metrics: Sharpe, PF, max DD, win rate
- Compare to baseline model

**Step 3: Promotion Criteria**
- Sharpe ratio >= baseline * 0.9 (allow 10% degradation)
- Profit factor >= baseline * 0.9
- Max drawdown <= baseline * 1.1 (allow 10% worse)
- Minimum 50 trades in validation period
- All metrics must pass (no single failure)

**Step 4: Promotion**
- Save new model with version number
- Keep previous model for rollback
- Update config to point to new model
- Log promotion event

**Step 5: Monitoring**
- Track live performance vs backtest
- If live performance degrades significantly, trigger rollback
- Schedule next retraining

**Step 6: Rollback (if needed)**
- If live Sharpe < backtest Sharpe * 0.7: Rollback
- If max DD > backtest DD * 1.5: Rollback
- Revert to previous model version

---

## Configuration Updates

### New Config Sections

```yaml
# Regime Filter
regime_filter:
  enabled: true
  adx_threshold: 25
  volatility_threshold: 2.0  # 2x average ATR
  allow_ranging: false  # Don't trade in ranging markets
  high_vol_multiplier: 0.5  # Reduce size in high vol

# Performance Guard
performance_guard:
  enabled: true
  rolling_window_trades: 10
  win_rate_threshold_reduced: 0.40
  win_rate_threshold_paused: 0.30
  drawdown_threshold_reduced: 0.05  # 5%
  drawdown_threshold_paused: 0.10   # 10%
  recovery_win_rate: 0.45
  recovery_drawdown: 0.05

# Triple-Barrier Labeling
labeling:
  profit_barrier: 0.02  # 2%
  loss_barrier: 0.01    # 1%
  time_barrier_hours: 24
  use_triple_barrier: true

# Volatility Targeting
volatility_targeting:
  enabled: true
  target_volatility: 0.01  # 1% daily
  lookback_period: 20  # days
  max_multiplier: 2.0

# Slippage & Funding
execution:
  base_slippage: 0.0001  # 0.01%
  volatility_slippage_factor: true
  include_funding: true
```

---

## Backward Compatibility

### Existing Configs
- Old configs without new sections will use defaults
- Existing models (v1.0) will still work
- New features are opt-in via config flags

### Migration Path
1. Keep existing model files
2. Add new config sections with defaults
3. Gradually enable new features
4. Retrain models with new labeling when ready

---

## Testing & Validation

### Unit Tests
- Regime filter classification accuracy
- Performance guard throttling logic
- Triple-barrier label generation
- Volatility calculation
- Walk-forward evaluation

### Integration Tests
- End-to-end signal generation with regime filter
- Position sizing with all multipliers
- Performance guard integration
- Model training with triple-barrier

### Backtesting
- Walk-forward validation on 2-3 years of data
- Compare v1 vs v2 performance
- Monte Carlo resampling for confidence intervals
- Stress tests under extreme conditions

---

## Operational Automation

### Automated Retraining
- **Script**: `scripts/scheduled_retrain.py`
- **Schedule**: Weekly (configurable)
- **Process**:
  1. Download latest data
  2. Train new model
  3. Validate against criteria
  4. Promote if passes
  5. Log results

### Health Checks
- **Heartbeat**: Log "alive" every hour
- **Data freshness**: Check last candle timestamp
- **Signal generation**: Verify signals being generated
- **API connectivity**: Test Bybit API connection

### Alerting (Future)
- Email/Discord on kill switch
- Performance guard interventions
- Model promotion/rollback
- API errors exceeding threshold

---

## Expected Improvements

### Robustness
- ✅ Regime filtering reduces bad trades
- ✅ Performance guard prevents death spirals
- ✅ Walk-forward validation reduces overfitting
- ✅ Triple-barrier labels more realistic

### Profitability Potential
- ✅ Better labels → better model → better predictions
- ✅ Volatility targeting → better risk-adjusted returns
- ✅ Funding/slippage modeling → more realistic expectations

### Self-Management
- ✅ Performance guard auto-throttles
- ✅ Automated retraining keeps models current
- ✅ Health checks detect issues
- ✅ Model promotion/rollback automated

---

## Limitations & Risks

### New Risks
- **Regime misclassification**: May miss opportunities or trade in wrong regime
- **Performance guard over-conservative**: May pause during temporary drawdowns
- **Model promotion failures**: Bad models may pass validation

### Mitigations
- Conservative regime thresholds (err on side of caution)
- Performance guard recovery conditions (auto-resume)
- Strict promotion criteria (multiple checks)

---

**Document Date:** December 2025  
**Version:** 2.0  
**Status:** Ready for Implementation

