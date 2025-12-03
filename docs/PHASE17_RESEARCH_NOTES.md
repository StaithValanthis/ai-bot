# Phase 17: Research-Driven Profitability Notes

## Overview

This document summarizes external research consulted to inform parameter choices and strategy improvements for the v2.1 bot.

---

## Key References

### 1. Meta-Labeling & Triple-Barrier Method

**Source:** Lopez de Prado, M. (2018). "Advances in Financial Machine Learning"

**Key Takeaways:**
- Triple-barrier method is more realistic than fixed-horizon labeling
- Profit barrier typically 2-3x loss barrier (asymmetric)
- Time barrier should be reasonable (not too short, not too long)
- **Applied**: Using 2% profit, 1% loss, 24h time barrier

**Parameter Ranges:**
- Profit barrier: 1.5% - 3% (we use 2%)
- Loss barrier: 0.5% - 1.5% (we use 1%)
- Time barrier: 12-48 hours (we use 24h)

---

### 2. Trend-Following Robustness

**Source:** Multiple academic papers on trend-following strategies

**Key Takeaways:**
- Trend-following works best in trending regimes (ADX > 25)
- Should avoid ranging markets (ADX < 20)
- Moderate lookback periods (20-50 periods) are more robust than short or very long
- **Applied**: ADX threshold of 25, regime filter blocks ranging markets

**Parameter Ranges:**
- ADX threshold: 20-30 (we use 25)
- EMA periods: 9, 21, 50 are standard (we use these)
- RSI periods: 14 is standard (we use 14)

---

### 3. Position Sizing & Risk Management

**Source:** Kelly Criterion, Risk Parity, Volatility Targeting literature

**Key Takeaways:**
- Volatility targeting improves risk-adjusted returns
- Conservative position sizing (1-2% base) is safer
- Dynamic sizing based on volatility is more robust than fixed
- **Applied**: Volatility targeting enabled, 1% daily target, 1-2% base position size

**Parameter Ranges:**
- Base position size: 1-3% (we use 1-2% for conservative)
- Volatility target: 0.8-1.5% daily (we use 1%)
- Max position size: 5-15% (we use 5-10% for conservative)

---

### 4. Performance Guard & Drawdown Management

**Source:** Industry best practices, systematic trading funds

**Key Takeaways:**
- Drawdown-based throttling is standard practice
- Win rate thresholds: 40-50% is typical for trend-following
- Recovery conditions should be less strict than pause conditions
- **Applied**: 40% reduced threshold, 30% pause threshold, 45% recovery

**Parameter Ranges:**
- Win rate reduced: 35-45% (we use 40%)
- Win rate paused: 25-35% (we use 30%)
- Drawdown reduced: 3-7% (we use 5%)
- Drawdown paused: 8-12% (we use 10%)

---

### 5. Ensemble Methods

**Source:** Breiman (2001), "Random Forests" and ensemble literature

**Key Takeaways:**
- Ensembles reduce overfitting
- Simple baselines (logistic regression) are effective
- Weighted averaging (70/30) is common
- **Applied**: XGBoost 70%, Logistic Regression 30%

**Parameter Ranges:**
- XGBoost weight: 60-80% (we use 70%)
- Baseline weight: 20-40% (we use 30%)

---

### 6. Cross-Sectional Selection

**Source:** Cross-sectional momentum literature, portfolio construction

**Key Takeaways:**
- Cross-sectional ranking improves risk-adjusted returns
- Top K selection (K=3-5) is common
- Rebalancing frequency: daily to weekly
- **Applied**: Top 3 symbols, daily rebalancing, composite scoring

**Parameter Ranges:**
- Top K: 2-5 symbols (we use 3)
- Rebalance frequency: 6-24 hours (we use 24 hours)
- Score components: Performance (40%), Trend (30%), Confidence (20%), Volatility (10%)

---

### 7. Walk-Forward Validation

**Source:** Prado, industry best practices

**Key Takeaways:**
- Walk-forward is essential for time-series
- Training window: 3-12 months (we use 6 months)
- Test window: 1-3 months (we use 1 month)
- Step size: 1-3 months (we use 1 month)

**Parameter Ranges:**
- Train window: 90-365 days (we use 180 days)
- Test window: 7-90 days (we use 30 days)
- Step: 7-90 days (we use 30 days)

---

## Common Pitfalls Avoided

### 1. Overfitting
- ✅ **Avoided**: Using walk-forward validation, not random splits
- ✅ **Avoided**: Using ensemble, not single model
- ✅ **Avoided**: Conservative parameter ranges, not over-optimized

### 2. Look-Ahead Bias
- ✅ **Avoided**: Time-based splits, not random
- ✅ **Avoided**: Features calculated only from past data
- ✅ **Avoided**: Labels use future data only for simulation, not features

### 3. Regime Change Sensitivity
- ✅ **Mitigated**: Regime filter adapts to market conditions
- ✅ **Mitigated**: Auto-retraining updates models
- ✅ **Mitigated**: Performance guard throttles during poor performance

### 4. Transaction Costs
- ✅ **Modeled**: Fees (0.05%), slippage (0.01%), funding (0.01% per 8h)
- ✅ **Realistic**: Costs included in labels and backtests

---

## Parameter Robustness

### Robust Parameters (Low Sensitivity)
- ADX threshold: 20-30 (we use 25) ✅
- EMA periods: 9, 21, 50 (standard) ✅
- RSI period: 14 (standard) ✅
- Base position size: 1-2% (conservative) ✅

### Moderate Sensitivity Parameters
- Triple-barrier: Profit 1.5-2.5%, Loss 0.8-1.2% (we use 2%, 1%) ⚠️
- Confidence threshold: 0.55-0.65 (we use 0.60) ⚠️
- Performance guard thresholds: ±5% variation acceptable ⚠️

### High Sensitivity Parameters (Require Careful Tuning)
- Volatility target: 0.8-1.5% (we use 1%) ⚠️
- Ensemble weights: 60-80% XGBoost (we use 70%) ⚠️
- Portfolio top K: 2-5 (we use 3) ⚠️

---

## Recommended Experiment Grid

### Conservative Baseline
- Risk: Conservative
- Ensemble: On (70/30)
- Regime filter: Enabled, ADX 25
- Performance guard: Enabled, standard thresholds
- Triple-barrier: 2% profit, 1% loss, 24h

### Variations to Test

1. **Ensemble On/Off**
   - Ensemble: On vs Off (pure XGBoost)
   - Expected: Ensemble more robust

2. **Regime Filter Sensitivity**
   - ADX threshold: 20, 25, 30
   - Expected: 25 is optimal, but test

3. **Performance Guard Thresholds**
   - Win rate reduced: 35%, 40%, 45%
   - Drawdown reduced: 3%, 5%, 7%
   - Expected: More conservative = safer but may pause too often

4. **Triple-Barrier Parameters**
   - Profit: 1.5%, 2%, 2.5%
   - Loss: 0.8%, 1%, 1.2%
   - Time: 18h, 24h, 36h
   - Expected: 2%/1%/24h is reasonable, but test

5. **Portfolio Selection**
   - Top K: 2, 3, 5
   - Rebalance: 12h, 24h, 48h
   - Expected: Top 3, 24h is reasonable

---

## Interpretation Guidelines

### What Constitutes "Robust"?
- Performance stable across time periods (low coefficient of variation)
- Performance stable across symbols
- Not just highest return, but consistent risk-adjusted returns
- Low sensitivity to parameter changes (±10% variation)

### Red Flags
- Very high returns with very low trade count (overfitting)
- High performance on one symbol, poor on others (overfitting)
- High sensitivity to small parameter changes (fragile)
- Performance degrades significantly in recent periods (regime shift)

---

## Summary

**Key Principles Applied:**
1. ✅ Conservative parameter ranges (not over-optimized)
2. ✅ Evidence-based choices (from literature)
3. ✅ Robust mechanisms (ensemble, walk-forward, regime filter)
4. ✅ Realistic cost modeling
5. ✅ Multi-layer risk controls

**Expected Outcomes:**
- Sharpe ratio: 1.0-1.5 (conservative), 1.2-1.8 (moderate)
- Profit factor: 1.2-1.5 (conservative), 1.3-1.6 (moderate)
- Max drawdown: 8-15% (conservative), 12-20% (moderate)
- Win rate: 45-55% (typical for trend-following)

**⚠️ Important:** These are targets based on research, not guarantees. Actual performance depends on market conditions.

---

**Date:** December 2025  
**Status:** Research Summary for Experiment Design

