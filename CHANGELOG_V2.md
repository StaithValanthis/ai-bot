# Changelog - Version 2.0

## Overview

Version 2.0 introduces significant improvements to robustness, realism, and self-management capabilities while preserving the core meta-labeling strategy.

---

## Breaking Changes

**None** - All changes are backward compatible. Existing v1.0 models and configs will continue to work.

---

## New Features

### 1. Regime Filter
- **Module:** `src/signals/regime_filter.py`
- **Purpose:** Classify market regimes and gate trend-following entries
- **Config:** `regime_filter` section in `config.yaml`
- **Default:** Enabled, blocks trading in ranging markets

### 2. Performance Guard
- **Module:** `src/risk/performance_guard.py`
- **Purpose:** Auto-throttle risk during poor performance
- **Config:** `performance_guard` section in `config.yaml`
- **Default:** Enabled, three tiers (NORMAL, REDUCED, PAUSED)

### 3. Walk-Forward Validation
- **Module:** `src/models/evaluation.py`
- **Purpose:** Proper time-series validation (no look-ahead bias)
- **Impact:** Training now uses time-based splits instead of random

### 4. Triple-Barrier Labeling
- **Location:** `src/models/train.py`
- **Purpose:** More realistic training labels
- **Config:** `labeling` section in `config.yaml`
- **Default:** Enabled (profit: 2%, loss: 1%, time: 24h)

### 5. Volatility-Targeted Position Sizing
- **Location:** `src/risk/risk_manager.py`
- **Purpose:** Adjust position size by market volatility
- **Config:** `volatility_targeting` section in `config.yaml`
- **Default:** Enabled, target 1% daily volatility

### 6. Slippage & Funding Modeling
- **Location:** `src/models/train.py`
- **Purpose:** Realistic cost modeling in backtests
- **Config:** `execution` section in `config.yaml`
- **Default:** 0.01% slippage, 0.01% funding per 8h

---

## Improvements

### Training
- ✅ Time-based train/val/test split (no random split)
- ✅ Triple-barrier label generation
- ✅ Slippage modeling (volatility-adjusted)
- ✅ Funding rate in labels
- ✅ ADX calculation for regime classification

### Risk Management
- ✅ Performance guard (auto-throttling)
- ✅ Volatility-targeted position sizing
- ✅ Regime-based position multipliers
- ✅ Enhanced risk checks

### Signal Generation
- ✅ Regime filter gating
- ✅ ADX indicator
- ✅ Enhanced feature set

### Evaluation
- ✅ Walk-forward validation framework
- ✅ Performance metrics calculation
- ✅ Aggregate statistics

---

## Configuration Changes

### New Sections
- `regime_filter`: Regime classification settings
- `performance_guard`: Performance monitoring and throttling
- `labeling`: Triple-barrier parameters
- `volatility_targeting`: Volatility-based sizing
- `execution`: Slippage and funding parameters

### Default Behavior
- All v2 features **enabled by default**
- Conservative thresholds
- Backward compatible with v1 configs

---

## Migration Guide

### From v1.0 to v2.0

1. **Update Config:**
   - Add new config sections (or use defaults)
   - Review and adjust thresholds as needed

2. **Retrain Model:**
   - Run `train_model.py` with new triple-barrier labeling
   - Model will be saved as v2.0 (or specified version)

3. **Test on Testnet:**
   - Run `live_bot.py` on testnet
   - Monitor regime filter and performance guard behavior
   - Verify all features working correctly

4. **Gradual Rollout:**
   - Can enable features one at a time
   - Start with performance guard (safest)
   - Then regime filter
   - Finally volatility targeting

---

## Files Changed

### New Files
- `src/models/evaluation.py`
- `src/risk/performance_guard.py`
- `src/signals/regime_filter.py`
- `docs/BOT_REVIEW_PHASE2_CONTEXT.md`
- `docs/BOT_REVIEW_PHASE2_FINDINGS.md`
- `docs/IMPROVEMENT_RESEARCH.md`
- `docs/PHASE6_V2_SYSTEM_DESIGN.md`
- `docs/PHASE6_IMPLEMENTATION_PLAN.md`
- `docs/PHASE6_V2_VALIDATION.md`
- `docs/PHASE6_IMPLEMENTATION_SUMMARY.md`

### Modified Files
- `config/config.yaml`: Added v2 sections
- `src/models/train.py`: Triple-barrier, costs, time-based split
- `src/signals/features.py`: ADX calculation
- `src/risk/risk_manager.py`: Volatility targeting
- `live_bot.py`: Integrated new components
- `train_model.py`: Updated for new parameters
- `README.md`: Updated documentation

---

## Testing Recommendations

1. **Backtest v2**: Run walk-forward validation
2. **Compare v1 vs v2**: Use identical data
3. **Paper Trade**: Testnet for 2-4 weeks
4. **Monitor**: Watch performance guard and regime filter

---

## Known Issues

- Funding rate uses default (not historical) - approximation
- No automated retraining yet (Tier 3)
- No portfolio risk aggregation yet (Tier 3)

---

## Future Work

See `docs/PHASE6_IMPLEMENTATION_PLAN.md` for Tier 3 improvements:
- Automated retraining
- Portfolio risk aggregation
- Monte Carlo resampling
- Health checks and alerting

---

**Version:** 2.0  
**Date:** December 2025  
**Status:** Ready for Testing

