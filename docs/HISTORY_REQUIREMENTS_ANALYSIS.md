# History Requirements - Current Behavior Analysis

**Date**: 2025-12-03  
**Status**: Analysis Complete

---

## Current Behavior

### How `required_history_days` is Used

**Finding**: `required_history_days` is **NOT actively enforced** in the current codebase.

1. **Config Definition**: 
   - `config/config.yaml` defines `model.required_history_days: 730`
   - `install.sh` sets this value during installation

2. **Training Pipeline**:
   - `train_model.py` accepts `--days` argument (default: 730)
   - This is passed to `HistoricalDataCollector.download_and_save(days=...)`
   - The download method attempts to fetch `days` of history, but:
     - If less data is available, it uses whatever is available
     - There is **no check** that the symbol actually has 730 days
     - There is **no blocking** if history is insufficient

3. **Live Trading**:
   - `live_bot.py` checks `trained_symbols` but does NOT check history length
   - Symbols are blocked if not in `trained_symbols`, but not based on history length

### What Happens in Practice

**Scenario 1: Symbol with 180 days of history**
- Training: `train_model.py --days 730` downloads 180 days (all available)
- Training proceeds with 180 days
- Symbol is trained and can be traded
- **Result**: Symbol is NOT blocked, even though it has < 2 years

**Scenario 2: Symbol with 730+ days of history**
- Training: Downloads 730 days (or more, but uses most recent 730)
- Training proceeds normally
- **Result**: Symbol is trained and can be traded

**Scenario 3: Symbol with patchy history (< 95% coverage)**
- Training: Downloads available data
- Quality checks may flag issues, but training still proceeds
- **Result**: Symbol is trained (with warnings)

### Answer to Key Questions

**Q: Does a symbol with < 2 years of history remain permanently blocked?**
**A: NO** - The current code does NOT block symbols based on history length. It trains on whatever data is available.

**Q: Does the training pipeline insist on 730 days?**
**A: NO** - The pipeline uses `--days` as a target/request, but trains on whatever is available if less data exists.

**Q: Is `required_history_days` actually enforced?**
**A: NO** - It's defined in config but not used in any enforcement logic.

---

## Problem Statement

The current implementation has a **gap**:
- Config suggests a 2-year requirement
- Documentation suggests symbols are blocked if they don't meet it
- But the code does NOT enforce this requirement

This means:
- New symbols (< 2 years) can be trained and traded immediately
- There's no minimum history threshold to prevent trading on insufficient data
- Operators may assume symbols are blocked when they're not

---

## Recommended Solution

Implement a **flexible history policy** with:
1. **Target history** (`target_history_days: 730`): Use up to this much, but not required
2. **Minimum history** (`min_history_days_to_train: 90`): Block symbols below this threshold
3. **Coverage requirement** (`min_history_coverage_pct: 0.95`): Ensure data quality

This allows:
- Training on 2 years when available (robust)
- Training on 3-6 months for newer symbols (flexible)
- Blocking symbols with < 3 months (safe)

---

**Status**: ✅ Analysis complete, implementation complete

---

## Implementation Summary

### New Flexible History Policy

**Config** (`config/config.yaml`):
```yaml
model:
  target_history_days: 730            # Target: up to 2 years (use most recent N days)
  min_history_days_to_train: 90        # Minimum: 3 months (symbols below this are blocked)
  min_history_coverage_pct: 0.95       # 95% data coverage required
  block_short_history_symbols: true    # Block symbols with < min_history_days_to_train
```

### Behavior

**Training Pipeline**:
- Requests up to `target_history_days` (730 days)
- Calculates actual available history for each symbol
- If `available_days < min_history_days_to_train`: **BLOCKS** training (symbol remains blocked)
- If `available_days >= min_history_days_to_train`: Trains using `min(available_days, target_history_days)`
- If more than target available, uses most recent `target_history_days`

**Live Trading**:
- Checks history for untrained symbols
- Blocks symbols with insufficient history (< 90 days by default)
- Only queues symbols that meet minimum requirements

**Result**:
- ✅ Symbols with 2+ years: Train on 2 years (robust)
- ✅ Symbols with 3-6 months: Train on available history (flexible)
- ❌ Symbols with < 3 months: Blocked until they accumulate sufficient history (safe)

---

**Status**: ✅ Implementation complete

