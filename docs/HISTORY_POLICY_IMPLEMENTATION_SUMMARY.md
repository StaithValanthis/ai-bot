# Flexible History Policy - Implementation Summary

**Date**: 2025-12-03  
**Status**: ✅ Complete

---

## Problem Statement

**Original Issue**: The config defined `required_history_days: 730` (2 years), but this was **NOT enforced**. The training pipeline would train on whatever data was available, even if it was only a few weeks old.

**Questions Answered**:
1. ✅ Does a symbol with < 2 years remain permanently blocked? **NO** - old code didn't block based on history
2. ✅ Does training insist on 730 days? **NO** - it used whatever was available
3. ✅ Should we train on available history up to a target? **YES** - implemented

---

## Solution: Flexible History Policy

### New Configuration

```yaml
model:
  # Target: Use up to 2 years when available (preferred for robustness)
  target_history_days: 730
  
  # Minimum: Block symbols below this threshold (safety)
  min_history_days_to_train: 90  # 3 months (recommended default)
  
  # Coverage: Ensure data quality
  min_history_coverage_pct: 0.95  # 95%
  
  # Enforcement
  block_short_history_symbols: true
```

### Behavior

**Training**:
- Requests up to `target_history_days` (730 days)
- Calculates actual available history
- If `available_days < min_history_days_to_train`: **BLOCKS** training
- If `available_days >= min_history_days_to_train`: Trains using `min(available_days, target_history_days)`
- If more than target available, uses most recent `target_history_days`

**Live Trading**:
- Checks history for untrained symbols
- Blocks symbols with insufficient history
- Only queues symbols that meet minimum requirements

---

## Implementation Details

### Files Modified

1. **`config/config.yaml`**:
   - Added `target_history_days: 730`
   - Added `min_history_days_to_train: 90`
   - Added `block_short_history_symbols: true`
   - Deprecated `required_history_days` (kept for backward compatibility)

2. **`src/data/historical_data.py`**:
   - Added `calculate_history_metrics()` static method
   - Calculates: available_days, coverage_pct, total_candles, date_range

3. **`train_model.py`**:
   - Reads history policy from config
   - Checks minimum requirements before training
   - Uses `min(available_days, target_history_days)` for training
   - Saves per-symbol history days in metadata

4. **`live_bot.py`**:
   - Enhanced `_check_model_coverage()` to check history requirements
   - Blocks symbols with insufficient history
   - Only queues symbols that meet minimum requirements

5. **`src/models/train.py`**:
   - Saves `symbol_history_days` mapping in model config

6. **`scripts/check_model_coverage.py`**:
   - Shows history metrics for untrained symbols
   - Indicates which symbols are blocked due to insufficient history

7. **`install.sh`**:
   - Sets new history policy defaults

### New Files

1. **`docs/HISTORY_REQUIREMENTS_ANALYSIS.md`** - Current behavior analysis
2. **`docs/HISTORY_REQUIREMENTS_RECOMMENDATION.md`** - Recommendation (90 days default)
3. **`docs/HISTORY_POLICY_IMPLEMENTATION_SUMMARY.md`** - This file

---

## Recommendation: 90 Days Minimum

**Default**: `min_history_days_to_train: 90` (3 months)

**Rationale**:
- ✅ Sufficient for ML training (2,160 hourly candles)
- ✅ Captures at least one market cycle
- ✅ Practical (allows trading newer symbols)
- ✅ Reasonable safety margin

**Alternative**: 180 days (6 months) for more conservative deployments

**Never**: < 60 days (too risky)

---

## Behavior Examples

### Symbol with 2+ Years

```
Available: 800 days
Action: Use most recent 730 days
Result: ✅ Trained on 730 days
```

### Symbol with 6 Months

```
Available: 180 days
Action: Use all 180 days (meets minimum)
Result: ✅ Trained on 180 days
```

### Symbol with 2 Months

```
Available: 60 days
Action: Check: 60 < 90 minimum
Result: ❌ BLOCKED - "Symbol has only 60 days (< 90 minimum)"
```

### Symbol with 3 Months but Poor Coverage

```
Available: 90 days, Coverage: 85%
Action: Check: 85% < 95% required
Result: ❌ BLOCKED - "Symbol has 85% coverage (< 95% required)"
```

---

## Testing

### Verify Behavior

```bash
# Check coverage and history
python scripts/check_model_coverage.py

# Try training a symbol with < 90 days (should fail)
python train_model.py --symbol NEWCOINUSDT --days 730
# Expected: "Symbol has only X days (< 90 minimum). Cannot train."

# Try training a symbol with 90-730 days (should succeed)
python train_model.py --symbol ANOTHERUSDT --days 730
# Expected: "Using X candles (Y days)" where Y < 730
```

---

## Backward Compatibility

✅ **Fully backward compatible**:
- Old models without `symbol_history_days` continue to work
- Config defaults are safe (block_short_history_symbols: true)
- `required_history_days` is deprecated but still accepted (mapped to target_history_days)

---

## Summary

**Before**: Symbols with any amount of history could be trained (no minimum enforced)

**After**: 
- ✅ Symbols with 2+ years: Train on 2 years (robust)
- ✅ Symbols with 3-6 months: Train on available history (flexible)
- ❌ Symbols with < 3 months: Blocked until sufficient history (safe)

**Default**: 90 days (3 months) minimum - recommended balance of safety and practicality

---

**Status**: ✅ Implementation complete, ready for testing

