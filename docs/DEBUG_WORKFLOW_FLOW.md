# Debug: Workflow Flow Analysis

**Date**: 2025-12-04  
**Issue**: Bot stuck in training/reload loop, never reaches stable trading

---

## STEP 0 - Current Flow (BROKEN)

### Initialization Flow
1. `live_bot.py.__init__()`:
   - Load config
   - Initialize universe manager
   - Initialize components (features, signals, risk, etc.)
   - **Load model** (MetaPredictor)
   - Set leverage
   - **Call `_check_model_coverage()`** ← RELOADS MODEL

2. `_check_model_coverage()`:
   - **RELOADS MODEL** (every call!)
   - Checks trained_symbols vs universe_symbols
   - For untrained symbols:
     - Checks history requirements
     - **Calls `_train_symbols_in_background()`** ← TRAINING IN TRADING BOT!
   - Blocks untrained symbols

3. `start()`:
   - Load existing positions
   - Refresh universe (if auto mode)
   - **Call `_check_model_coverage()` again** ← RELOADS MODEL AGAIN
   - Start WebSocket streams
   - Enter main loop

### Main Loop Flow (BROKEN)
1. Every 60 seconds:
   - Monitor positions
   - Check kill switch
   - **Every 5 minutes**: Check completed training threads
   - **Every 5 minutes**: Re-evaluate blocked symbols ← RELOADS MODEL
   - Health check
   - Process signals (if not blocked)

2. Signal Processing:
   - `_on_new_candle()` → `_process_signal()`
   - **Early return if symbol blocked** ← This is OK
   - Generate signals, place orders

### Training Triggers (PROBLEM)
1. **`_check_model_coverage()`** → Calls `_train_symbols_in_background()`
2. **`_train_symbols_in_background()`** → Starts threads
3. **`_train_symbol_worker()`** → Runs `train_model.py` subprocess
4. **After training**: Reloads model in worker thread
5. **Periodic check**: Reloads model again

### Model Reload Points (TOO MANY)
1. `__init__()` - Initial load (OK)
2. `_check_model_coverage()` - **Every call** (BAD - called multiple times)
3. `_train_symbol_worker()` - After training (BAD - in worker thread)
4. Main loop periodic check - Every 5 minutes (BAD - unnecessary)

---

## Root Cause Analysis

### Problem 1: Training Inside Trading Bot
**Location**: `live_bot.py._check_model_coverage()` line 367
```python
if auto_train and symbols_to_queue:
    self._train_symbols_in_background(symbols_to_queue)
```

**Issue**: Trading bot should NOT train. Training should be separate.

### Problem 2: Model Reloads Every Coverage Check
**Location**: `live_bot.py._check_model_coverage()` line 257
```python
self.meta_predictor = MetaPredictor(...)  # Reloads every call
```

**Issue**: Model is reloaded every time coverage is checked, even if nothing changed.

### Problem 3: Coverage Check Called Too Often
**Location**: 
- `__init__()` line 130
- `start()` line 1185
- Main loop periodic checks

**Issue**: Coverage check triggers training, which triggers reloads, which triggers more checks.

### Problem 4: No Clear Separation
- Trading bot mixes training logic with trading logic
- No clear state machine for symbol status
- Training happens in background threads, causing race conditions

---

## STEP 1 - Target Architecture (FIXED)

### Separation of Concerns

**Trading Process (`live_bot.py`)**:
- Loads model ONCE on startup
- Classifies symbols into states (TRAINED, UNTRAINED_TRAINABLE, UNTRAINED_SHORT_HISTORY)
- Only trades TRAINED symbols
- Skips other symbols (no training, no retraining)
- Writes to training queue file (if needed) for external process

**Training Process** (separate scripts):
- `train_model.py` - Manual training
- `scripts/scheduled_retrain.py` - Scheduled training + queue processing
- Reads training queue, trains, updates model
- Trading bot picks up changes on restart

### Symbol State Machine

**States**:
1. **TRAINED**: In `trained_symbols` + meets history requirements → **TRADABLE**
2. **UNTRAINED_TRAINABLE**: Not in `trained_symbols` but has ≥ min_history_days → **QUEUE FOR TRAINING** (external), skip trading
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

## STEP 2 - Implementation Plan

### Changes to `live_bot.py`

1. **Remove training logic**:
   - Remove `_train_symbols_in_background()`
   - Remove `_train_symbol_worker()`
   - Remove training thread management

2. **Simplify coverage check**:
   - Rename to `_classify_symbol_states()`
   - Classify symbols into states
   - Write to training queue file (if needed)
   - NO model reloads
   - NO training triggers

3. **Simplify model loading**:
   - Load once in `__init__()`
   - No reloads unless explicitly needed

4. **Update main loop**:
   - Remove periodic training checks
   - Remove periodic model reloads
   - Just trade TRAINED symbols

### Changes to Training Queue

- Use `data/new_symbol_training_queue.json` for external training
- Trading bot writes to queue (once per symbol)
- `scripts/scheduled_retrain.py` processes queue

---

## STEP 3 - Implementation Complete

### Changes Made to `live_bot.py`

1. **Removed all training logic**:
   - Removed `_train_symbols_in_background()` method
   - Removed `_train_symbol_worker()` method
   - Removed `_queue_symbols_for_training()` method
   - Removed `_check_and_unblock_symbols()` method
   - Removed `training_threads` and `training_lock` attributes
   - Removed `threading` and `subprocess` imports

2. **Replaced `_check_model_coverage()` with `_classify_symbol_states()`**:
   - Does NOT reload model (uses already-loaded model)
   - Does NOT trigger training
   - Classifies symbols into states: TRAINED, UNTRAINED_TRAINABLE, UNTRAINED_SHORT_HISTORY
   - Writes to training queue file for external scripts
   - Logs clear summary

3. **Simplified model loading**:
   - Model loaded ONCE in `__init__()`
   - No periodic reloads
   - No reloads in coverage checks

4. **Updated main loop**:
   - Removed all training checks
   - Removed periodic model reloads
   - Removed training thread monitoring
   - Just trades tradable symbols

5. **Added helper method**:
   - `is_symbol_tradable(symbol)` - clean check for tradability

6. **Updated `start()` method**:
   - Calls `_refresh_symbol_states()` instead of `_check_model_coverage()`
   - No training triggers

### New Architecture

**Trading Bot (`live_bot.py`)**:
- Loads model once on startup
- Classifies symbols into states
- Only trades TRAINED symbols
- Skips other symbols (no training, no retraining)
- Writes to training queue file (if needed) for external process

**Training (External Scripts)**:
- `train_model.py` - Manual training
- `scripts/scheduled_retrain.py` - Scheduled training + queue processing
- Trading bot picks up changes on restart

### Symbol State Machine

1. **TRAINED**: In `trained_symbols` + meets history requirements → **TRADABLE**
2. **UNTRAINED_TRAINABLE**: Not trained but has ≥ min_history_days → **QUEUED FOR TRAINING** (external), skip trading
3. **UNTRAINED_SHORT_HISTORY**: Has < min_history_days → **PERMANENTLY BLOCKED**, skip trading, no training

### Model Loading Rules

- Load ONCE on startup
- Only reload on explicit signal (e.g., model rotation file marker)
- Or on process restart
- NO periodic reloads
- NO reloads in coverage checks

