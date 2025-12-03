# Model Coverage & New Symbol Onboarding - Implementation Summary

**Date**: 2025-12-03  
**Status**: ✅ Complete

---

## Overview

This document summarizes the implementation of model coverage tracking and automatic new symbol onboarding. The system ensures that **no symbol is traded until it has been properly trained with sufficient historical data**.

---

## What Was Implemented

### 1. Enhanced `install.sh`

**New Prompts**:
- Model training mode selection (`single_symbol` vs `multi_symbol`)
- Symbol encoding method (`one_hot` vs `index`) for multi-symbol mode
- Core symbols selection for multi-symbol training
- Auto-training configuration defaults

**Config Updates**:
- Automatically sets `model.training_mode` in `config.yaml`
- Sets `model.symbol_encoding` if multi-symbol mode
- Sets `model.multi_symbol_symbols` if explicit list provided
- Sets new symbol onboarding defaults:
  - `auto_train_new_symbols: true`
  - `required_history_days: 730`
  - `min_history_coverage_pct: 0.95`
  - `block_untrained_symbols: true`

**Training Integration**:
- Respects `training_mode` when running initial training
- For multi-symbol: uses configured symbols or auto universe
- For single-symbol: prompts for one symbol

**Start Bot Prompt**:
- Offers to start bot immediately after installation
- Provides clear manual start/stop/monitor instructions
- Includes systemd, screen/tmux, and direct run options

### 2. Model Coverage Metadata Persistence

**Training Pipeline (`src/models/train.py`, `train_model.py`)**:
- Saves `trained_symbols` list to model config
- Saves `training_days` (e.g., 730)
- Saves `training_end_timestamp` (last timestamp in training data)
- Saves `min_history_days_per_symbol`
- Saves `training_mode` and `symbol_encoding_type`
- Saves `symbol_encoding_map` for multi-symbol models

**Metadata Location**: `models/model_config_v{version}.json`

### 3. MetaPredictor Coverage API

**New Properties** (`src/signals/meta_predictor.py`):
- `trained_symbols`: List of symbols used in training
- `training_days`: Number of days of history
- `training_mode`: `single_symbol` or `multi_symbol`
- `training_end_timestamp`: Last timestamp in training data
- `min_history_days_per_symbol`: Minimum history requirement
- `is_symbol_covered(symbol)`: Check if symbol is covered

**Backward Compatibility**: Older models without metadata log warnings but continue to work.

### 4. New Symbol Onboarding in Live Trading

**Coverage Checking** (`live_bot.py`):
- On initialization: checks model coverage vs universe
- On universe refresh: re-checks coverage
- Computes `untrained_symbols = universe_symbols - trained_symbols`
- Blocks trading for untrained symbols

**Trading Block**:
- `blocked_symbols` set tracks untrained symbols
- `_process_signal()` returns early for blocked symbols
- Logs occasionally (1% chance) to avoid spam

**Training Queue**:
- Untrained symbols added to `data/new_symbol_training_queue.json`
- Queue format:
  ```json
  {
    "queued_symbols": ["NEWCOINUSDT"],
    "queued_at": {
      "NEWCOINUSDT": "2025-12-03T12:00:00"
    }
  }
  ```
- Queue processed by `scripts/scheduled_retrain.py` (or dedicated script)

**Auto-Unblocking**:
- `_check_and_unblock_symbols()` periodically checks if blocked symbols are now trained
- Unblocks symbols after successful training

### 5. Diagnostic Script

**`scripts/check_model_coverage.py`**:
- Reads model metadata
- Reads current universe
- Compares and reports:
  - Trained symbols
  - Universe symbols
  - Untrained symbols
  - Queued symbols
  - Configuration status

**Usage**:
```bash
python scripts/check_model_coverage.py
```

### 6. Configuration Options

**New Config Keys** (`config/config.yaml`):
```yaml
model:
  auto_train_new_symbols: true        # Enable/disable auto-training
  block_untrained_symbols: true      # Block trading for untrained symbols
  
  # History Requirements Policy
  target_history_days: 730            # Target: up to 2 years (use most recent N days)
  min_history_days_to_train: 90       # Minimum: 3 months (symbols below this are blocked)
  min_history_coverage_pct: 0.95      # 95% data coverage required
  block_short_history_symbols: true    # Block symbols with < min_history_days_to_train
```

**History Policy**:
- **Target**: Train on up to 2 years when available (robust)
- **Minimum**: Block symbols with < 3 months (safe)
- **Flexible**: Train on 3-6 months for newer symbols (practical)

---

## File Changes Summary

### Modified Files

1. **`install.sh`**
   - Added training mode prompts
   - Added symbol encoding prompts
   - Updated config.yaml writing logic
   - Updated training section to respect training_mode
   - Added start bot prompt
   - Updated next steps instructions

2. **`config/config.yaml`**
   - Added new symbol onboarding config options

3. **`src/models/train.py`**
   - Updated `save_model()` to save coverage metadata
   - Added metadata properties to trainer

4. **`train_model.py`**
   - Sets coverage metadata before saving model
   - Handles both single and multi-symbol modes

5. **`src/signals/meta_predictor.py`**
   - Added coverage metadata properties
   - Added `is_symbol_covered()` method

6. **`live_bot.py`**
   - Added `blocked_symbols` tracking
   - Added `_check_model_coverage()` method
   - Added `_queue_symbols_for_training()` method
   - Added `_check_and_unblock_symbols()` method
   - Updated `_process_signal()` to block untrained symbols
   - Updated universe refresh to re-check coverage

### New Files

1. **`scripts/check_model_coverage.py`**
   - Diagnostic script for coverage checking

2. **`docs/NEW_SYMBOL_ONBOARDING.md`**
   - Comprehensive documentation

3. **`docs/MODEL_COVERAGE_AND_ONBOARDING_SUMMARY.md`**
   - This summary document

---

## How It Works

### Installation Flow

1. User runs `bash install.sh`
2. Prompts for training mode (single/multi-symbol)
3. If multi-symbol: prompts for encoding and symbols
4. Updates `config.yaml` with all settings
5. Optionally runs initial training
6. Optionally starts bot immediately
7. Prints manual start/monitor instructions

### Live Trading Flow

1. Bot starts, loads model
2. Gets universe symbols from `UniverseManager`
3. Compares with `meta_predictor.trained_symbols`
4. Blocks untrained symbols
5. Queues untrained symbols for training (if auto-train enabled)
6. Processes signals only for covered symbols
7. Periodically checks if blocked symbols are now trained

### Training Queue Processing

1. `scripts/scheduled_retrain.py` (or dedicated script) reads queue
2. For each queued symbol:
   - Fetches 2 years of historical data
   - Verifies data meets requirements
   - Trains model (mode-dependent)
   - Updates model metadata
   - Removes from queue
3. Bot unblocks symbol after training

---

## Usage Examples

### Check Model Coverage

```bash
python scripts/check_model_coverage.py
```

### Manual Training Queue Management

```bash
# View queue
cat data/new_symbol_training_queue.json

# Clear queue (if needed)
echo '{"queued_symbols": [], "queued_at": {}}' > data/new_symbol_training_queue.json
```

### Start Bot

```bash
# Direct run
source venv/bin/activate
python live_bot.py

# Systemd
sudo systemctl start bybit-bot-live.service
sudo journalctl -u bybit-bot-live.service -f

# Screen
screen -S trading_bot
source venv/bin/activate
python live_bot.py
# Ctrl+A then D to detach
```

---

## Limitations & Caveats

1. **Training Time**: Training new symbols can take significant time
2. **Data Availability**: Some symbols may not have 2 years of history (will remain blocked)
3. **Single-Symbol Mode**: Adding new symbols requires training new model (or switching to multi-symbol mode)
4. **Model Reload**: After training, bot must be restarted or model reloaded to unblock symbols
5. **Queue Processing**: Training queue must be processed manually or via scheduled_retrain (not automatic inline)

---

## Backward Compatibility

✅ **Fully backward compatible**:
- Older models without metadata continue to work (with warnings)
- Default config: `block_untrained_symbols: true` (safe default)
- Single-symbol mode remains default
- Existing workflows unchanged

---

## Next Steps (Future Enhancements)

1. **Hot Reload**: Automatically reload model when training completes
2. **Incremental Training**: For multi-symbol mode, incrementally add symbols
3. **Priority Queue**: Prioritize high-liquidity symbols
4. **Auto-Queue Processing**: Background process to automatically process queue
5. **Symbol Clustering**: Group similar symbols for faster training

---

## Testing Recommendations

1. **Test Coverage Checking**:
   ```bash
   python scripts/check_model_coverage.py
   ```

2. **Test Blocking**:
   - Add a new symbol to universe (not in trained_symbols)
   - Start bot, verify it's blocked
   - Check queue file exists

3. **Test Training Queue**:
   - Manually add symbol to queue
   - Run training script
   - Verify symbol is removed from queue
   - Verify model metadata updated

4. **Test Unblocking**:
   - Train a new symbol
   - Restart bot
   - Verify symbol is unblocked

---

**Status**: ✅ Implementation complete, ready for testing

