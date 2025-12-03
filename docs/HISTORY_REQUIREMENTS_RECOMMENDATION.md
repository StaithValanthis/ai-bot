# History Requirements Recommendation

**Date**: 2025-12-03  
**Status**: ✅ Recommendation Complete

---

## Executive Summary

**Recommended Default**: `min_history_days_to_train: 90` (3 months)

**Rationale**: Balances safety (sufficient data for ML training) with practicality (allows trading newer symbols). For conservative deployments, consider 180 days (6 months).

---

## Analysis

### Minimum History Requirements for Crypto Trading

For intraday/hourly trading strategies on crypto perpetuals, we need sufficient history to:

1. **Train ML Models**: 
   - Need enough samples for train/validation/test splits
   - 90 days * 24 hours = 2,160 hourly candles
   - With walk-forward validation (e.g., 180-day train, 30-day test), this provides ~3 folds
   - **Minimum viable**: ~60-90 days

2. **Capture Market Regimes**:
   - Crypto markets cycle through bull, bear, ranging, volatile regimes
   - 3 months captures at least one full cycle in most cases
   - 6 months captures multiple cycles (more robust)

3. **Statistical Robustness**:
   - More data = lower variance in performance estimates
   - 90 days: Moderate variance, acceptable for newer symbols
   - 180 days: Lower variance, more conservative

### Recommendation: 90 Days (3 Months)

**Why 90 Days?**

✅ **Pros**:
- **Sufficient for ML**: 2,160 hourly candles is enough for basic training
- **Captures Regimes**: At least one full market cycle in most cases
- **Practical**: Allows trading newer listings sooner
- **Reasonable Risk**: Not too aggressive (avoids trading on weeks of data)

❌ **Cons**:
- **Regime Risk**: May overfit to recent regime if market just shifted
- **Variance**: Higher variance in performance estimates than 6 months
- **Robustness**: Less robust to regime changes

**Trade-off**: Acceptable risk for faster access to new symbols. The model's meta-labeling approach helps mitigate overfitting by learning signal profitability patterns.

### Alternative: 180 Days (6 Months)

**When to Use**:
- More conservative deployments
- If you see overfitting issues with 90-day models
- For higher capital allocations
- When you want maximum robustness

**Pros**:
- More robust to regime changes
- Better statistical power
- Lower variance in estimates

**Cons**:
- Slower access to new listings
- May miss early opportunities

---

## Implementation

### Default Configuration

```yaml
model:
  target_history_days: 730            # Use up to 2 years when available
  min_history_days_to_train: 90        # Minimum: 3 months (recommended)
  min_history_coverage_pct: 0.95       # 95% coverage required
  block_short_history_symbols: true    # Block symbols below minimum
```

### How It Works

1. **Symbol with 2+ years of history**:
   - Downloads up to 730 days
   - Uses most recent 730 days
   - Trains normally

2. **Symbol with 90-730 days**:
   - Downloads available history
   - Uses all available days (up to 730)
   - Trains normally
   - May be flagged as "short history" in metadata

3. **Symbol with < 90 days**:
   - Downloads available history
   - Checks: `available_days < min_history_days_to_train`
   - **BLOCKS** training and trading
   - Logs: "Symbol XYZ has only X days (< 90 minimum). Blocked."
   - Remains blocked until it accumulates 90 days

### Coverage Requirement

The `min_history_coverage_pct: 0.95` requirement ensures:
- At least 95% of expected candles are present
- Accounts for missing data, gaps, exchange downtime
- Symbols with patchy history are blocked

---

## Configuration Examples

### Conservative Deployment

```yaml
model:
  target_history_days: 730
  min_history_days_to_train: 180  # 6 months - more conservative
  min_history_coverage_pct: 0.95
  block_short_history_symbols: true
```

### Aggressive Deployment (Not Recommended)

```yaml
model:
  target_history_days: 730
  min_history_days_to_train: 60   # 2 months - risky
  min_history_coverage_pct: 0.90  # Lower coverage requirement
  block_short_history_symbols: true
```

**Warning**: Lowering below 90 days increases risk of overfitting and regime-specific failures.

---

## Monitoring

Use `scripts/check_model_coverage.py` to monitor:

- Which symbols are trained
- Which symbols are blocked (and why)
- History metrics for untrained symbols

Example output:
```
Symbol NEWCOINUSDT: 45 days (< 90 minimum) - BLOCKED
Symbol ANOTHERUSDT: 120 days, 96.2% coverage - ELIGIBLE
```

---

## Conclusion

**Default Recommendation**: **90 days (3 months)**

This provides:
- ✅ Sufficient data for ML training
- ✅ Reasonable safety margin
- ✅ Practical access to newer symbols
- ✅ Good balance of risk vs. opportunity

**For Conservative Deployments**: Use **180 days (6 months)** for maximum robustness.

**Never Go Below**: 60 days (2 months) - too risky for ML training.

---

**Status**: ✅ Recommendation complete

