# Phase 9: Additional Profitability-Focused Improvements

## Overview

This document identifies and evaluates additional evidence-backed improvements that can enhance the v2 bot's profitability and robustness. Based on research and industry best practices, we evaluate candidate enhancements and select the most promising ones for implementation.

---

## Candidate Improvements

### 1. Cross-Sectional Symbol Selection & Portfolio Control

**Source:**
- **Lopez de Prado (2018)**: "Advances in Financial Machine Learning" - Chapter 20 on Portfolio Construction
- **Industry Practice**: Most systematic funds use cross-sectional ranking and selection
- **Evidence**: Cross-sectional momentum is a well-documented anomaly

**Concept:**
Instead of trading all symbols independently, use cross-sectional strength to:
1. **Rank symbols** by composite score (trend strength, recent risk-adjusted return, ADX, etc.)
2. **Select top K symbols** (e.g., top 3-5) to trade at each rebalancing
3. **Allocate capital** across selected symbols (equal weight, risk parity, or capped risk per symbol)
4. **Rebalance periodically** (e.g., daily or weekly)

**Why Relevant:**
- **Current Issue**: Bot trades each symbol independently, no portfolio view
- **Opportunity**: Cross-sectional selection can improve risk-adjusted returns
- **Risk Management**: Diversification across symbols reduces single-symbol risk

**Expected Benefits:**
- Better risk-adjusted returns (Sharpe ratio)
- Reduced correlation risk
- More efficient capital use
- Natural diversification

**Possible Downsides:**
- Adds complexity
- May miss opportunities in non-selected symbols
- Rebalancing costs (minimal for crypto)

**Implementation Complexity:** Medium
- Need to add symbol ranking logic
- Need portfolio allocation module
- Need rebalancing scheduler
- Need to track positions across symbols

**Evidence Strength:** ⭐⭐⭐⭐ (Strong)

---

### 2. Model Ensembling / Baseline Model Checks

**Source:**
- **Breiman (2001)**: "Random Forests" - Ensemble methods improve generalization
- **Industry Practice**: Most ML trading systems use ensembles or model selection
- **Evidence**: Ensembles reduce overfitting and improve robustness

**Concept:**
1. **Add baseline model**: Simple logistic regression or linear model alongside XGBoost
2. **Train both models** on same data
3. **Compare performance** (validation metrics)
4. **Use ensemble or selection rule**:
   - **Option A**: Ensemble (weighted average of predictions)
   - **Option B**: Select best model based on validation performance
   - **Option C**: Use baseline as sanity check (only trade if both agree)

**Why Relevant:**
- **Current Issue**: Single model (XGBoost) may overfit
- **Opportunity**: Ensembles are more robust
- **Risk Management**: Baseline can catch when XGBoost is overconfident

**Expected Benefits:**
- Reduced overfitting
- More robust predictions
- Better generalization
- Sanity check mechanism

**Possible Downsides:**
- Adds training time
- More complex inference
- May reduce signal strength if models disagree

**Implementation Complexity:** Low-Medium
- Add baseline model training
- Modify prediction logic
- Add ensemble/selection logic
- Update config

**Evidence Strength:** ⭐⭐⭐⭐⭐ (Very Strong)

---

### 3. Improved Meta-Labeling Parameters (Systematic Tuning)

**Source:**
- **Lopez de Prado (2018)**: Triple-barrier method parameters should be tuned
- **Industry Practice**: Parameters are typically tuned via grid search or Bayesian optimization
- **Evidence**: Parameter sensitivity analysis is standard practice

**Concept:**
1. **Grid search or Bayesian optimization** over triple-barrier parameters:
   - Profit barrier: [0.01, 0.015, 0.02, 0.025, 0.03]
   - Loss barrier: [0.005, 0.01, 0.015, 0.02]
   - Time barrier: [12, 24, 48, 72] hours
2. **Evaluate robustness**: Test across multiple symbols and time periods
3. **Select robust parameters**: Choose parameters that work across symbols, not overfitted to one
4. **Document sensitivity**: Report how sensitive performance is to parameters

**Why Relevant:**
- **Current Issue**: Parameters are set to defaults (2%, 1%, 24h)
- **Opportunity**: Optimal parameters may differ by symbol or market regime
- **Risk Management**: Robust parameters reduce overfitting risk

**Expected Benefits:**
- Better label quality
- More robust training
- Potentially better model performance

**Possible Downsides:**
- Time-consuming (many combinations)
- Risk of overfitting to training data
- Need careful validation

**Implementation Complexity:** Medium
- Add parameter search framework
- Integrate with research harness
- Add robustness checks
- Update config with optimal parameters

**Evidence Strength:** ⭐⭐⭐ (Moderate - depends on validation rigor)

---

### 4. Regime-Specific Model Variants

**Source:**
- **Lopez de Prado (2018)**: Regime-dependent models can improve performance
- **Industry Practice**: Many funds use regime-specific strategies
- **Evidence**: Regime classification is well-established

**Concept:**
1. **Train separate models** for different regimes:
   - Model for TRENDING_UP
   - Model for TRENDING_DOWN
   - Model for RANGING (optional)
   - Model for HIGH_VOLATILITY
2. **Select model** based on current regime (from regime_filter)
3. **Use regime-specific features** if beneficial

**Why Relevant:**
- **Current Issue**: Single model for all regimes
- **Opportunity**: Regime-specific models may capture regime-specific patterns
- **Risk Management**: Better adaptation to market conditions

**Expected Benefits:**
- Better regime-specific performance
- More adaptive strategy
- Potentially higher Sharpe ratio

**Possible Downsides:**
- More complex (multiple models to train/maintain)
- Risk of overfitting to regimes
- Need more data per regime
- Model selection complexity

**Implementation Complexity:** High
- Need to split training data by regime
- Train multiple models
- Add model selection logic
- Update config and storage

**Evidence Strength:** ⭐⭐⭐ (Moderate - depends on regime stability)

---

### 5. Dynamic Position Sizing Based on Recent Performance

**Source:**
- **Kelly Criterion**: Optimal position sizing based on win rate and payoff
- **Industry Practice**: Many systematic funds use dynamic sizing
- **Evidence**: Kelly criterion is theoretically optimal (with caveats)

**Concept:**
1. **Calculate recent win rate and average win/loss** (rolling window)
2. **Apply Kelly fraction** (or fractional Kelly for safety):
   - Kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
   - Fractional Kelly = Kelly * 0.25 (for safety)
3. **Adjust position size** based on Kelly fraction
4. **Cap at max position size** for safety

**Why Relevant:**
- **Current Issue**: Position size is static (based on confidence only)
- **Opportunity**: Dynamic sizing can improve risk-adjusted returns
- **Risk Management**: Reduces size when performance is poor

**Expected Benefits:**
- Better risk-adjusted returns
- Automatic size adjustment
- More capital-efficient

**Possible Downsides:**
- Adds complexity
- Kelly can be volatile
- Need sufficient history for stable estimates

**Implementation Complexity:** Low-Medium
- Add Kelly calculation
- Integrate into position sizing
- Add safety caps

**Evidence Strength:** ⭐⭐⭐⭐ (Strong, but needs careful implementation)

---

## Selected Improvements for Implementation

Based on evidence strength, implementation complexity, and expected impact, we select:

### 1. Model Ensembling / Baseline Model Checks ⭐⭐⭐⭐⭐
**Priority:** HIGH  
**Rationale:**
- Very strong evidence (ensembles are standard)
- Low-medium complexity
- High impact on robustness
- Can be implemented without major architectural changes

**Implementation Plan:**
- Add logistic regression baseline model
- Train both models in parallel
- Use weighted ensemble (70% XGBoost, 30% baseline) or selection rule
- Add validation comparison

### 2. Cross-Sectional Symbol Selection ⭐⭐⭐⭐
**Priority:** HIGH  
**Rationale:**
- Strong evidence (cross-sectional momentum)
- Medium complexity
- High impact on portfolio risk
- Natural extension of current architecture

**Implementation Plan:**
- Add symbol ranking module
- Add portfolio allocation logic
- Add rebalancing scheduler
- Integrate with live_bot.py

### 3. Dynamic Position Sizing (Fractional Kelly) ⭐⭐⭐⭐
**Priority:** MEDIUM  
**Rationale:**
- Strong evidence (Kelly criterion)
- Low-medium complexity
- Medium-high impact
- Complements performance guard

**Implementation Plan:**
- Add Kelly calculation to risk_manager
- Integrate with existing position sizing
- Add safety caps and smoothing

---

## Implementation Order

1. **Model Ensembling** (Week 1)
   - Quick win, high impact
   - Low risk
   - Improves robustness immediately

2. **Cross-Sectional Selection** (Week 2)
   - Medium complexity
   - High impact on portfolio
   - Requires more testing

3. **Dynamic Position Sizing** (Week 3)
   - Lower priority
   - Can be added incrementally
   - Complements existing features

---

## Rejected Improvements

### Regime-Specific Models
- **Reason**: High complexity, moderate evidence, risk of overfitting
- **Status**: Deferred to future work

### Systematic Parameter Tuning
- **Reason**: Can be done manually via research harness, not core feature
- **Status**: Documented as best practice, not implemented as automation

---

## Expected Impact Summary

| Improvement | Evidence | Complexity | Impact | Priority |
|------------|----------|------------|--------|----------|
| Model Ensembling | ⭐⭐⭐⭐⭐ | Low-Medium | High | HIGH |
| Cross-Sectional Selection | ⭐⭐⭐⭐ | Medium | High | HIGH |
| Dynamic Position Sizing | ⭐⭐⭐⭐ | Low-Medium | Medium-High | MEDIUM |
| Regime-Specific Models | ⭐⭐⭐ | High | Medium | DEFERRED |
| Parameter Tuning | ⭐⭐⭐ | Medium | Low-Medium | MANUAL |

---

## References

1. Lopez de Prado, M. (2018). "Advances in Financial Machine Learning"
2. Breiman, L. (2001). "Random Forests"
3. Kelly, J. L. (1956). "A New Interpretation of Information Rate"
4. Industry best practices from systematic trading funds

---

**Status:** Ready for Implementation  
**Date:** December 2025

