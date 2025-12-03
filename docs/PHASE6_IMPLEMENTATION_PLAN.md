# Phase 6: Implementation Plan

## Overview

This document outlines a prioritized, practical implementation plan for v2 improvements. Improvements are organized into 3 tiers based on impact, risk, and complexity.

---

## Tier 1: High-Impact, Low-Risk (Implement First)

### 1.1 Walk-Forward Validation

**Priority:** CRITICAL  
**Impact:** High (fixes overfitting risk)  
**Risk:** Low (validation improvement, doesn't change trading logic)  
**Complexity:** Medium

**Files to Modify:**
- `src/models/train.py`: Replace random split with time-based split
- `src/models/evaluation.py`: NEW - Walk-forward evaluation module

**Implementation Steps:**
1. Create `src/models/evaluation.py` with walk-forward logic
2. Modify `train_model()` to use time-based split
3. Add walk-forward backtest function
4. Update `train_model.py` script to use walk-forward
5. Generate performance report per fold

**Expected Benefits:**
- More realistic performance estimates
- Reduces overfitting risk
- Better model selection

**Testing:**
- Unit test: Time-based split correctness
- Integration test: Walk-forward on sample data
- Validation: Compare random vs time-based results

---

### 1.2 Slippage & Funding Modeling

**Priority:** HIGH  
**Impact:** High (more realistic backtests)  
**Risk:** Low (adds costs, more conservative)  
**Complexity:** Low

**Files to Modify:**
- `src/models/train.py`: Add slippage and funding to label calculation
- `src/data/historical_data.py`: Add funding rate fetching (if available)

**Implementation Steps:**
1. Add slippage calculation (volatility-adjusted)
2. Add funding rate to label calculation
3. Update `prepare_data()` to include costs
4. Add config parameters for slippage/funding

**Expected Benefits:**
- More realistic backtest results
- Better alignment with live trading
- More conservative expectations

**Testing:**
- Unit test: Slippage calculation
- Validation: Compare with/without slippage results

---

### 1.3 Performance Guard

**Priority:** HIGH  
**Impact:** High (prevents catastrophic losses)  
**Risk:** Low (conservative, reduces risk)  
**Complexity:** Medium

**Files to Create/Modify:**
- `src/risk/performance_guard.py`: NEW - Performance monitoring and throttling
- `live_bot.py`: Integrate performance guard
- `src/risk/risk_manager.py`: Add performance guard integration

**Implementation Steps:**
1. Create `performance_guard.py` module
2. Implement rolling PnL, win rate, drawdown tracking
3. Implement throttling tiers (normal, reduced, paused)
4. Integrate into `live_bot.py` before trade execution
5. Add config parameters

**Expected Benefits:**
- Prevents death spirals
- Auto-throttles during bad periods
- Self-managing risk

**Testing:**
- Unit test: Throttling logic
- Integration test: End-to-end with simulated trades
- Validation: Test recovery conditions

---

### 1.4 Enhanced Risk Limits

**Priority:** MEDIUM  
**Impact:** Medium (safer defaults)  
**Risk:** Low (more conservative)  
**Complexity:** Low

**Files to Modify:**
- `config/config.yaml`: Update default risk parameters
- `src/risk/risk_manager.py`: Add additional safety checks

**Implementation Steps:**
1. Review and tighten default risk limits
2. Add additional pre-trade checks
3. Improve error messages

**Expected Benefits:**
- Safer defaults
- Better risk control

---

## Tier 2: Medium Complexity, Solid Evidence

### 2.1 Triple-Barrier Labeling

**Priority:** HIGH  
**Impact:** High (better labels)  
**Risk:** Medium (changes training, need to retrain)  
**Complexity:** Medium

**Files to Modify:**
- `src/models/train.py`: Replace simple hold-period with triple-barrier
- `config/config.yaml`: Add barrier parameters

**Implementation Steps:**
1. Implement triple-barrier logic in `prepare_data()`
2. Track which barrier was hit
3. Add barrier parameters to config
4. Update label generation documentation
5. Retrain models with new labeling

**Expected Benefits:**
- More realistic labels
- Better alignment with live trading
- Improved model quality

**Testing:**
- Unit test: Barrier hit detection
- Validation: Compare old vs new labels
- Backtest: Compare model performance

---

### 2.2 Regime Filter

**Priority:** HIGH  
**Impact:** High (reduces bad trades)  
**Risk:** Medium (may miss opportunities)  
**Complexity:** Medium

**Files to Create/Modify:**
- `src/signals/regime_filter.py`: NEW - Regime classification
- `src/signals/features.py`: Add ADX calculation
- `live_bot.py`: Integrate regime filter
- `config/config.yaml`: Add regime filter config

**Implementation Steps:**
1. Add ADX calculation to `features.py`
2. Create `regime_filter.py` with classification logic
3. Integrate into signal generation pipeline
4. Add config parameters
5. Test on historical data

**Expected Benefits:**
- Fewer trades in bad conditions
- Higher win rate
- Lower drawdowns

**Testing:**
- Unit test: Regime classification accuracy
- Integration test: Signal gating logic
- Backtest: Compare with/without regime filter

---

### 2.3 Volatility-Targeted Position Sizing

**Priority:** MEDIUM  
**Impact:** Medium (better risk management)  
**Risk:** Low (more conservative)  
**Complexity:** Low

**Files to Modify:**
- `src/risk/risk_manager.py`: Add volatility calculation and scaling
- `config/config.yaml`: Add volatility targeting config

**Implementation Steps:**
1. Add volatility calculation (20-day ATR or rolling std)
2. Modify `calculate_position_size()` to include volatility multiplier
3. Add config parameters
4. Test on historical data

**Expected Benefits:**
- More consistent risk exposure
- Better risk-adjusted returns

**Testing:**
- Unit test: Volatility calculation
- Integration test: Position sizing with volatility

---

## Tier 3: Advanced / Experimental

### 3.1 Portfolio Risk Aggregation

**Priority:** LOW  
**Impact:** Medium (important for multi-symbol)  
**Risk:** Low  
**Complexity:** Medium

**Files to Modify:**
- `src/risk/risk_manager.py`: Add portfolio risk calculation
- `live_bot.py`: Aggregate risk across positions

**Implementation Steps:**
1. Calculate correlation between symbols
2. Implement portfolio risk formula
3. Adjust position limits based on portfolio risk
4. Add to risk checks

---

### 3.2 Monte Carlo Resampling

**Priority:** LOW  
**Impact:** Low (evaluation improvement)  
**Risk:** Low  
**Complexity:** Medium

**Files to Create:**
- `src/models/evaluation.py`: Add Monte Carlo function

**Implementation Steps:**
1. Implement trade sequence shuffling
2. Calculate metrics per shuffle
3. Generate distribution statistics
4. Add to evaluation report

---

### 3.3 Automated Retraining

**Priority:** MEDIUM  
**Impact:** High (operational improvement)  
**Risk:** Medium (may promote bad models)  
**Complexity:** High

**Files to Create:**
- `scripts/scheduled_retrain.py`: NEW - Automated retraining script

**Implementation Steps:**
1. Create retraining script
2. Implement model validation logic
3. Implement promotion/rollback
4. Add scheduling (cron/systemd)
5. Add alerting

---

## Implementation Order

### Phase 1: Critical Fixes (Week 1)
1. Walk-forward validation
2. Slippage & funding modeling
3. Enhanced risk limits

### Phase 2: Core Improvements (Week 2)
4. Performance guard
5. Triple-barrier labeling
6. Regime filter

### Phase 3: Enhancements (Week 3)
7. Volatility-targeted sizing
8. Portfolio risk (if multi-symbol)
9. Monte Carlo (if time permits)

### Phase 4: Automation (Week 4)
10. Automated retraining
11. Health checks
12. Alerting (optional)

---

## Testing Strategy

### Unit Tests
- Each new module/function
- Edge cases and error handling
- Config validation

### Integration Tests
- End-to-end signal generation
- Position sizing with all multipliers
- Performance guard integration
- Walk-forward evaluation

### Backtesting
- Compare v1 vs v2 on historical data
- Walk-forward validation
- Stress tests

### Paper Trading
- Run v2 on testnet for 1-2 weeks
- Monitor performance guard behavior
- Verify regime filter effectiveness

---

## Success Metrics

### Tier 1 Improvements
- ✅ Walk-forward Sharpe within 20% of random split (more realistic)
- ✅ Backtest returns reduced by 0.1-0.2% (slippage/funding)
- ✅ Performance guard triggers during drawdowns
- ✅ No catastrophic losses during bad periods

### Tier 2 Improvements
- ✅ Regime filter reduces trades by 20-30% in ranging markets
- ✅ Win rate improves by 5-10%
- ✅ Triple-barrier labels show better model performance
- ✅ Volatility targeting reduces drawdowns

### Overall
- ✅ Sharpe ratio maintained or improved
- ✅ Maximum drawdown reduced
- ✅ Win rate improved
- ✅ More realistic backtest results

---

## Rollback Plan

### If Issues Arise
1. **Regime filter too conservative**: Lower ADX threshold or allow ranging trades
2. **Performance guard too aggressive**: Relax thresholds or recovery conditions
3. **Triple-barrier issues**: Fall back to simple hold-period
4. **Model performance degrades**: Rollback to v1.0 model

### Version Control
- Keep v1.0 code in git branch
- Tag v2.0 releases
- Maintain backward compatibility

---

## Documentation Updates

### Required Updates
- `README.md`: New features and config options
- `docs/QUICK_START.md`: Updated setup instructions
- `config/config.yaml`: Document new parameters
- Code docstrings: All new modules/functions

### New Documentation
- `docs/OPERATIONS.md`: Performance guard, retraining, monitoring
- `docs/V2_MIGRATION.md`: Migration guide from v1 to v2

---

**Document Date:** December 2025  
**Status:** Ready for Implementation  
**Next Step:** Begin Tier 1 implementation

