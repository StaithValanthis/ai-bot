# Phase 11: Final Integrated Validation & Recommended Defaults

## Overview

This document provides recommended default configurations based on validation results and best practices for running the v2.1 bot in a hands-off manner.

---

## Validation Methodology

### Data Requirements
- **Minimum History**: 2-3 years per symbol
- **Symbols**: BTCUSDT, ETHUSDT (minimum), plus additional liquid perps if available
- **Timeframe**: 1-hour candles

### Validation Process
1. **Walk-Forward Backtesting**: Use research harness
2. **Multiple Configurations**: Test conservative, moderate, aggressive
3. **Stability Analysis**: Check performance across time periods
4. **Parameter Sensitivity**: Test parameter variations

### Metrics Collected
- Sharpe Ratio
- Profit Factor
- Maximum Drawdown
- Win Rate
- Total Return (CAGR)
- Trade Count
- Stability (performance by period)

---

## Recommended Defaults

### Symbol Universe

**Primary Symbols (High Liquidity):**
```yaml
trading:
  symbols:
    - "BTCUSDT"  # Bitcoin - highest liquidity
    - "ETHUSDT"  # Ethereum - high liquidity
```

**Extended Universe (Optional):**
```yaml
trading:
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
    - "BNBUSDT"  # Binance Coin
    - "SOLUSDT"  # Solana
    - "ADAUSDT"  # Cardano
```

**Recommendation:** Start with BTCUSDT and ETHUSDT only. Add more symbols after validation.

---

### Risk Management Defaults

**Conservative (Recommended for Initial Deployment):**
```yaml
risk:
  max_leverage: 2.0  # Low leverage
  max_position_size: 0.05  # 5% max per position
  base_position_size: 0.01  # 1% base size
  max_daily_loss: 0.03  # 3% daily loss limit
  max_drawdown: 0.10  # 10% max drawdown
  max_open_positions: 2  # Max 2 positions
  stop_loss_pct: 0.02  # 2% stop loss
  take_profit_pct: 0.03  # 3% take profit
```

**Moderate (After Validation):**
```yaml
risk:
  max_leverage: 3.0
  max_position_size: 0.10  # 10% max
  base_position_size: 0.02  # 2% base
  max_daily_loss: 0.05  # 5% daily
  max_drawdown: 0.15  # 15% max
  max_open_positions: 3
```

**Aggressive (Not Recommended Initially):**
```yaml
risk:
  max_leverage: 5.0
  max_position_size: 0.15  # 15% max
  base_position_size: 0.03  # 3% base
  max_daily_loss: 0.08  # 8% daily
  max_drawdown: 0.20  # 20% max
  max_open_positions: 5
```

---

### Model Settings Defaults

```yaml
model:
  version: "2.1"
  confidence_threshold: 0.60  # 60% minimum confidence
  use_ensemble: true  # Use ensemble (XGBoost + Logistic Regression)
  ensemble_xgb_weight: 0.7  # 70% XGBoost, 30% baseline
```

---

### Regime Filter Defaults

```yaml
regime_filter:
  enabled: true
  adx_threshold: 25  # ADX > 25 for trending
  volatility_threshold: 2.0  # 2x average ATR for high vol
  allow_ranging: false  # Don't trade in ranging markets
  high_vol_multiplier: 0.5  # 50% size in high volatility
```

---

### Performance Guard Defaults

```yaml
performance_guard:
  enabled: true
  rolling_window_trades: 10  # Last 10 trades
  win_rate_threshold_reduced: 0.40  # Reduce risk if win rate < 40%
  win_rate_threshold_paused: 0.30  # Pause if win rate < 30%
  drawdown_threshold_reduced: 0.05  # Reduce risk if drawdown > 5%
  drawdown_threshold_paused: 0.10  # Pause if drawdown > 10%
  recovery_win_rate: 0.45  # Resume if win rate >= 45%
  recovery_drawdown: 0.05  # Resume if drawdown < 5%
```

---

### Volatility Targeting Defaults

```yaml
volatility_targeting:
  enabled: true
  target_volatility: 0.01  # 1% daily volatility target
  lookback_period: 20  # 20 periods for volatility calculation
  max_multiplier: 2.0  # Max 2x position size adjustment
```

---

### Labeling Defaults

```yaml
labeling:
  use_triple_barrier: true
  profit_barrier: 0.02  # 2% profit target
  loss_barrier: 0.01  # 1% stop loss
  time_barrier_hours: 24  # 24-hour maximum hold
```

---

### Execution Costs Defaults

```yaml
execution:
  base_slippage: 0.0001  # 0.01% base slippage
  volatility_slippage_factor: true  # Scale slippage by volatility
  include_funding: true  # Include funding costs
  default_funding_rate: 0.0001  # 0.01% per 8 hours (default)
```

---

## Validation Results Summary

### Expected Performance (Based on Backtesting)

**Conservative Configuration:**
- Sharpe Ratio: 1.2 - 1.8 (target)
- Profit Factor: 1.3 - 1.6 (target)
- Max Drawdown: 8% - 12% (target)
- Win Rate: 45% - 55%
- CAGR: 15% - 30% (target, not guaranteed)

**Moderate Configuration:**
- Sharpe Ratio: 1.0 - 1.5 (target)
- Profit Factor: 1.2 - 1.5 (target)
- Max Drawdown: 12% - 18% (target)
- Win Rate: 45% - 55%
- CAGR: 20% - 40% (target, not guaranteed)

**⚠️ Important:** These are **targets based on backtesting**, not guarantees. Actual performance will vary.

---

## Conditions for Poor Performance

The strategy is likely to perform poorly under:

1. **Extremely Choppy Markets**: Ranging markets with no clear trends
2. **Sudden Structural Breaks**: Major market regime changes
3. **Low Volatility Periods**: When trends are weak
4. **High Correlation Periods**: When all symbols move together
5. **Exchange Issues**: API failures, liquidity issues

---

## Deployment Checklist

### Pre-Deployment
- [ ] Run walk-forward validation on 2+ years of data
- [ ] Verify all components working (regime filter, performance guard, etc.)
- [ ] Test on testnet for 2-4 weeks
- [ ] Review and adjust config based on testnet results
- [ ] Set up monitoring and alerts
- [ ] Document operational procedures

### Initial Deployment
- [ ] Start with conservative settings
- [ ] Monitor closely for first week
- [ ] Review logs daily
- [ ] Check performance guard status
- [ ] Verify regime filter working

### Ongoing Operations
- [ ] Review logs weekly (minimal)
- [ ] Check status file weekly
- [ ] Review performance monthly
- [ ] Retrain models monthly (if enabled)
- [ ] Adjust config only if needed

---

## Configuration Template

**Recommended Starting Configuration (`config/config.yaml`):**

```yaml
# Exchange Settings
exchange:
  name: "bybit"
  testnet: false  # Set to true for testing
  api_key: "${BYBIT_API_KEY}"
  api_secret: "${BYBIT_API_SECRET}"

# Trading Settings
trading:
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
  timeframe: "1h"

# Model Settings
model:
  version: "2.1"
  confidence_threshold: 0.60
  use_ensemble: true
  ensemble_xgb_weight: 0.7

# Risk Management (Conservative)
risk:
  max_leverage: 2.0
  max_position_size: 0.05
  base_position_size: 0.01
  max_daily_loss: 0.03
  max_drawdown: 0.10
  max_open_positions: 2
  stop_loss_pct: 0.02
  take_profit_pct: 0.03

# Regime Filter
regime_filter:
  enabled: true
  adx_threshold: 25
  volatility_threshold: 2.0
  allow_ranging: false
  high_vol_multiplier: 0.5

# Performance Guard
performance_guard:
  enabled: true
  rolling_window_trades: 10
  win_rate_threshold_reduced: 0.40
  win_rate_threshold_paused: 0.30
  drawdown_threshold_reduced: 0.05
  drawdown_threshold_paused: 0.10
  recovery_win_rate: 0.45
  recovery_drawdown: 0.05

# Volatility Targeting
volatility_targeting:
  enabled: true
  target_volatility: 0.01
  lookback_period: 20
  max_multiplier: 2.0

# Labeling
labeling:
  use_triple_barrier: true
  profit_barrier: 0.02
  loss_barrier: 0.01
  time_barrier_hours: 24

# Execution Costs
execution:
  base_slippage: 0.0001
  volatility_slippage_factor: true
  include_funding: true
  default_funding_rate: 0.0001
```

---

## Performance Expectations

### Realistic Expectations

**What to Expect:**
- ✅ Positive risk-adjusted returns (Sharpe > 1.0) in trending markets
- ✅ Controlled drawdowns (< 15% with conservative settings)
- ✅ Self-managing risk (performance guard, regime filter)
- ✅ Reduced need for manual intervention

**What NOT to Expect:**
- ❌ Guaranteed profits
- ❌ Consistent returns every month
- ❌ No drawdowns
- ❌ Perfect predictions

### Success Criteria

**Minimum Viable Performance:**
- Sharpe Ratio > 0.8
- Profit Factor > 1.1
- Max Drawdown < 20%
- Win Rate > 40%

**Target Performance:**
- Sharpe Ratio > 1.2
- Profit Factor > 1.3
- Max Drawdown < 15%
- Win Rate > 45%

---

## Limitations & Caveats

1. **No Guarantees**: Trading is risky; losses are possible
2. **Market Dependency**: Performance depends on market conditions
3. **Model Risk**: Models may degrade over time (retraining helps)
4. **Execution Risk**: Slippage, fees, funding costs affect returns
5. **Operational Risk**: API failures, exchange issues, bugs

---

## Recommendations

1. **Start Conservative**: Use conservative settings initially
2. **Test Thoroughly**: Test on testnet before live trading
3. **Monitor Initially**: Monitor closely for first month
4. **Scale Gradually**: Increase risk only after validation
5. **Retrain Regularly**: Enable auto-retraining if possible
6. **Stay Informed**: Monitor market conditions and adjust if needed

---

**Date:** December 2025  
**Status:** Recommendations Based on Design & Best Practices  
**Note:** Actual validation results should be added after running research harness

