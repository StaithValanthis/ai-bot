# New Symbol Onboarding System

**Date**: 2025-12-03  
**Status**: Implementation in Progress

---

## Overview

The bot implements automatic onboarding for new symbols that appear in the universe but have not been trained. This ensures that **no symbol is traded until it has been properly trained with sufficient historical data**.

---

## Key Features

1. **Model Coverage Tracking**: The system tracks which symbols are covered by the current model
2. **Automatic Detection**: New symbols are detected when the universe is refreshed
3. **Training Queue**: Untrained symbols are queued for training (not trained inline)
4. **Trading Block**: Untrained symbols are blocked from trading until training completes
5. **History Requirements**: Symbols must have 2+ years of history (configurable)

---

## Configuration

In `config/config.yaml`:

```yaml
model:
  auto_train_new_symbols: true        # Enable/disable auto-training
  block_untrained_symbols: true      # Block trading for untrained symbols
  
  # History Requirements Policy
  target_history_days: 730            # Target: up to 2 years (use most recent N days)
  min_history_days_to_train: 90       # Minimum: 3 months (symbols below this are blocked)
  min_history_coverage_pct: 0.95      # 95% data coverage required
  block_short_history_symbols: true   # Block symbols with < min_history_days_to_train
```

### History Requirements Policy

**Target History (`target_history_days: 730`)**:
- Use up to this many days when available (preferred for robustness)
- If more history is available, use the most recent `target_history_days`
- This is a **target/cap**, not a requirement

**Minimum History (`min_history_days_to_train: 90`)**:
- Minimum number of days required to train and trade a symbol
- Symbols with less than this are **blocked** from training and trading
- Default: **90 days (3 months)** - recommended minimum
- Can be increased to 180 days (6 months) for more conservative deployments

**Coverage Requirement (`min_history_coverage_pct: 0.95`)**:
- Minimum percentage of expected candles that must be present
- Accounts for missing data, gaps, etc.
- Symbols below this threshold are blocked

### Recommendation: 90 Days Minimum

**Why 90 days (3 months)?**
- **Pros**:
  - Allows trading newer symbols sooner
  - Captures at least one full quarter of market cycles
  - Sufficient for basic trend-following patterns
  - Reasonable sample size for ML training (90 * 24 = 2,160 hourly candles)
  
- **Cons**:
  - May overfit to recent market regime
  - Less robust to regime changes
  - Higher variance in performance estimates

**Alternative: 180 days (6 months)**
- **Pros**:
  - More robust, captures multiple market regimes
  - Better statistical power
  - Lower risk of overfitting
  
- **Cons**:
  - Slower access to new listings
  - May miss early opportunities

**Recommendation**: Start with **90 days** as default. For conservative deployments or if you see overfitting issues, increase to **180 days**.

---

## How It Works

### 1. Model Coverage Metadata

When a model is trained, it saves metadata including:
- `trained_symbols`: List of symbols used in training
- `training_days`: Number of days of history used
- `training_end_timestamp`: Last timestamp in training data
- `training_mode`: `single_symbol` or `multi_symbol`

This metadata is stored in `models/model_config_v{version}.json`.

### 2. Coverage Checking

When `live_bot.py` starts or refreshes the universe:

1. Gets current universe symbols via `UniverseManager`
2. Gets trained symbols from `meta_predictor.trained_symbols`
3. Computes `untrained_symbols = universe_symbols - trained_symbols`
4. For each untrained symbol:
   - Adds to `blocked_symbols` set
   - Logs warning: "Symbol XYZ is new/untrained - blocking trading"
   - If `auto_train_new_symbols` is true: adds to training queue

### 3. Training Queue

Untrained symbols are added to `data/new_symbol_training_queue.json`:

```json
{
  "queued_symbols": ["NEWCOINUSDT", "ANOTHERUSDT"],
  "queued_at": {
    "NEWCOINUSDT": "2025-12-03T12:00:00",
    "ANOTHERUSDT": "2025-12-03T12:05:00"
  }
}
```

### 4. Training Process

The training queue is processed by `scripts/scheduled_retrain.py` (or a dedicated script):

1. Reads queue file
2. For each queued symbol:
   - Fetches up to `target_history_days` of historical data (e.g., 730 days)
   - Verifies data meets requirements:
     - `available_days >= min_history_days_to_train` (e.g., >= 90 days)
     - `coverage_pct >= min_history_coverage_pct` (e.g., >= 95%)
   - If requirements met:
     - Uses `min(available_days, target_history_days)` days for training
     - If more than target available, uses most recent `target_history_days`
     - Trains model in appropriate mode:
       - **Single-symbol mode**: Trains new model for that symbol (or updates existing)
       - **Multi-symbol mode**: Re-trains global model including new symbol
     - Updates model metadata
     - Removes symbol from queue
   - If requirements NOT met:
     - Symbol remains in queue (or is removed with error)
     - Symbol remains blocked until it accumulates sufficient history

### 5. Trading Block

In `live_bot.py`, before placing any order:

```python
if symbol in self.blocked_symbols:
    logger.debug(f"Symbol {symbol} is untrained, skipping order")
    return  # Do not place order
```

---

## Implementation Details

### Files Modified

1. **`src/models/train.py`**: Saves model coverage metadata
2. **`src/signals/meta_predictor.py`**: Exposes coverage metadata via properties
3. **`live_bot.py`**: Implements coverage checking and trading blocks
4. **`scripts/scheduled_retrain.py`**: Processes training queue
5. **`config/config.yaml`**: New configuration options

### New Files

1. **`scripts/check_model_coverage.py`**: Diagnostic script to check coverage
2. **`data/new_symbol_training_queue.json`**: Training queue file (created automatically)

---

## Usage

### Check Model Coverage

```bash
python scripts/check_model_coverage.py
```

Output:
```
Model Coverage Report
=====================
Trained symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
Universe symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'NEWCOINUSDT']
Untrained symbols: ['NEWCOINUSDT']
Queued for training: ['NEWCOINUSDT']
```

### Manual Training Queue Management

The queue file can be manually edited if needed:

```bash
# View queue
cat data/new_symbol_training_queue.json

# Clear queue (if needed)
echo '{"queued_symbols": [], "queued_at": {}}' > data/new_symbol_training_queue.json
```

---

## Limitations & Caveats

1. **Training Time**: Training new symbols can take significant time (especially multi-symbol mode)
2. **Data Availability**: 
   - Symbols with < `min_history_days_to_train` (e.g., < 90 days) remain blocked
   - Symbols with insufficient coverage (< 95%) remain blocked
   - New symbols will be trainable once they accumulate sufficient history
3. **Single-Symbol Mode**: In single-symbol mode, adding a new symbol requires training a new model (or switching to multi-symbol mode)
4. **Model Updates**: After training, the bot must be restarted or model reloaded to unblock symbols

---

## Future Enhancements

1. **Hot Reload**: Automatically reload model when training completes
2. **Incremental Training**: For multi-symbol mode, incrementally add symbols without full re-train
3. **Symbol Clustering**: Group similar symbols for faster training
4. **Priority Queue**: Prioritize high-liquidity symbols

---

**Status**: ✅ Core implementation complete, ready for testing

