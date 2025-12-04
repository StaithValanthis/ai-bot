# Architecture Redesign Summary

**Date**: 2025-12-04  
**Issue**: Bot stuck in infinite training/reload loop  
**Status**: ✅ FIXED - Architecture Redesigned

---

## Root Cause

The bot was stuck in a training/reload loop because:

1. **Training was happening inside the trading bot** (`live_bot.py`)
2. **Model was being reloaded every coverage check** (even when nothing changed)
3. **Coverage checks triggered training**, which triggered reloads, which triggered more checks
4. **Periodic checks ran every loop iteration** (not every 5 minutes as intended)

---

## New Architecture

### Separation of Concerns

**Trading Process (`live_bot.py`)**:
- ✅ Loads model ONCE on startup
- ✅ Classifies symbols into states (TRAINED, UNTRAINED_TRAINABLE, UNTRAINED_SHORT_HISTORY)
- ✅ Only trades TRAINED symbols
- ✅ Skips other symbols (no training, no retraining)
- ✅ Writes to training queue file (if needed) for external process
- ❌ Does NOT train symbols
- ❌ Does NOT reload models during runtime

**Training Process** (separate scripts):
- `train_model.py` - Manual training
- `scripts/scheduled_retrain.py` - Scheduled training + queue processing
- Reads training queue, trains, updates model
- Trading bot picks up changes on restart

### Symbol State Machine

**States**:
1. **TRAINED**: In `trained_symbols` + meets history requirements → **TRADABLE**
2. **UNTRAINED_TRAINABLE**: Not trained but has ≥ min_history_days → **QUEUED FOR TRAINING** (external), skip trading
3. **UNTRAINED_SHORT_HISTORY**: Has < min_history_days → **PERMANENTLY BLOCKED**, skip trading, no training

**Behavior**:
- Trading bot only trades TRAINED symbols
- Other states are logged once, then skipped
- No retraining loops
- No model reloads during trading

### Model Loading

**Rules**:
- Load ONCE on startup
- Only reload on explicit signal (e.g., model rotation file marker)
- Or on process restart
- NO periodic reloads
- NO reloads in coverage checks

---

## Changes Made

### `live_bot.py`

1. **Removed**:
   - `_train_symbols_in_background()`
   - `_train_symbol_worker()`
   - `_queue_symbols_for_training()`
   - `_check_and_unblock_symbols()`
   - `training_threads` and `training_lock` attributes
   - `threading` and `subprocess` imports
   - All training logic from main loop

2. **Replaced**:
   - `_check_model_coverage()` → `_classify_symbol_states()`
   - Model reloads → No reloads (use already-loaded model)

3. **Added**:
   - `_classify_symbol_states()` - Classifies symbols without training
   - `_write_to_training_queue()` - Writes to queue file for external scripts
   - `_refresh_symbol_states()` - Re-classifies after universe refresh
   - `is_symbol_tradable()` - Clean check for tradability

4. **Simplified**:
   - Main loop - removed all training checks
   - Model loading - once on startup
   - Symbol checking - uses `is_symbol_tradable()`

---

## How It Works Now

### Startup Flow

1. Load config
2. Initialize components
3. **Load model ONCE** (MetaPredictor)
4. **Classify symbols** (`_classify_symbol_states()`)
   - Checks trained_symbols from model
   - Checks history requirements
   - Classifies into states
   - Writes to training queue (if needed)
5. Start trading loop

### Trading Loop

1. Every 60 seconds:
   - Monitor positions
   - Check kill switch
   - Health check (every 5 minutes)
   - Process signals for **TRADABLE symbols only**

2. Signal Processing:
   - `_on_new_candle()` → `_process_signal()`
   - **Early return if not tradable** (uses `is_symbol_tradable()`)
   - Generate signals, place orders

### Adding New Symbols

1. **External training**:
   - Run `python train_model.py --symbol SYMBOL`
   - Or use `scripts/scheduled_retrain.py` to process queue

2. **Restart bot**:
   - Bot loads new model
   - Re-classifies symbols
   - New symbol becomes TRADABLE if trained

---

## Testing

### Expected Behavior

1. **On Startup**:
   - ✅ Model loads once
   - ✅ Symbols classified into states
   - ✅ Clear logging of tradable vs blocked symbols
   - ✅ No training triggered

2. **During Runtime**:
   - ✅ Trading loop runs normally
   - ✅ Only TRADABLE symbols are processed
   - ✅ No model reloads
   - ✅ No training loops
   - ✅ Signals generated and orders placed (if conditions met)

3. **With New Symbols**:
   - ✅ New symbols detected as untrained
   - ✅ Queued for training (if sufficient history)
   - ✅ Blocked if insufficient history
   - ✅ Bot continues trading other symbols
   - ✅ No retraining loops

---

## Commands

### Running Training (External)

```bash
# Manual training for a symbol
python train_model.py --symbol BTCUSDT --days 730

# Process training queue
python scripts/scheduled_retrain.py

# Scheduled retraining (via cron/systemd)
# See scripts/scheduled_retrain.py for details
```

### Running Trading Bot (Testnet)

```bash
# Start bot
python live_bot.py

# Or with testnet campaign script
python scripts/run_testnet_campaign.py --profile profile_conservative --duration-minutes 10
```

---

## Summary

**Before**: Bot trained symbols during runtime, reloaded models frequently, got stuck in loops.

**After**: Bot loads model once, classifies symbols, trades only trained symbols, training is external.

**Result**: Clean separation, no loops, stable trading.

