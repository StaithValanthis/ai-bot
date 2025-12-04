# Debug: Training/Reload Loop Investigation

**Date**: 2025-12-04  
**Issue**: Bot stuck in constant training/reload loop, never reaches normal trading

---

## STEP 0 – Training & Reload Triggers Map

### 0.1. Training Triggers

**Direct Training Calls:**
1. `train_model.py` (CLI script)
   - Called by: `install.sh`, `scripts/scheduled_retrain.py`, `live_bot.py` (subprocess)
   - Triggers: CLI arguments, model discovery (if no compatible model)

2. `live_bot.py._train_symbols_in_background()`
   - Called by: `_check_model_coverage()`, periodic re-evaluation
   - Triggers: Untrained symbols detected, symbols with sufficient history

3. `scripts/scheduled_retrain.py`
   - Called by: Cron/systemd timer
   - Triggers: Scheduled retraining, training queue processing

### 0.2. Model Reload Triggers

**Model Reload Locations:**
1. `live_bot.py.__init__()` - Initial load
2. `live_bot.py._check_model_coverage()` - **Reloads at start** (LINE 253-261)
3. `live_bot.py._train_symbol_worker()` - **Reloads after training** (LINE 686-693)
4. `live_bot.py` main loop - **Periodic reload** (LINE 1276-1284)
5. `live_bot.py` periodic re-evaluation - **Reloads before checking** (LINE 1305-1313)

**SUSPICIOUS**: Multiple reload points, especially in coverage checks that run frequently!

---

## SUMMARY

**Root Cause**: Periodic re-evaluation of blocked symbols ran every loop iteration (60s) instead of every 5 minutes, causing infinite training/reload loop.

**Fix**: Added timer check to ensure periodic checks only run every 5 minutes.

**Status**: ✅ FIXED

---

## STEP 1 – Coverage & Onboarding Logic

### 1.1. Coverage Check Flow (`live_bot.py._check_model_coverage()`)

**Called From:**
- `__init__()` - LINE 130 (startup)
- `start()` - LINE 1185 (after universe refresh)
- **Main loop** - Potentially every iteration? (NEED TO CHECK)

**Logic Flow:**
1. **Reloads model** (LINE 253-261) - ⚠️ **HAPPENS EVERY TIME**
2. Gets `trained_symbols` from model
3. Compares with `universe_symbols`
4. For untrained symbols:
   - Checks history requirements
   - Blocks if insufficient
   - Queues for training if sufficient
5. Calls `_train_symbols_in_background()` if symbols to queue

**Potential Issues:**
- Model reload happens every call (expensive, but necessary for accuracy)
- Symbols might be re-queued if not properly tracked
- Need to check if this runs in main loop

### 1.2. Background Training (`live_bot.py._train_symbol_worker()`)

**Flow:**
1. Downloads/loads data
2. Checks history requirements
3. Runs `train_model.py` as subprocess
4. **Reloads model** after training (LINE 686-693)
5. Unblocks symbol if now trained

**Potential Issues:**
- Model reload happens in worker thread
- Main thread might not see updated model until periodic check
- Race condition between worker reload and main thread checks

### 1.3. Periodic Checks (Main Loop)

**Every 5 Minutes:**
- Checks for completed training threads
- Reloads model
- Calls `_check_and_unblock_symbols()`
- Re-evaluates blocked symbols

**Potential Issues:**
- Re-evaluation might re-queue symbols that are already trained
- Model reload might not see latest changes if file locking is involved

---

## STEP 2 – Model Discovery & Selection

### 2.1. Model Registry (`src/models/model_registry.py`)

**`select_best_model()`:**
- Checks `training_mode` compatibility
- Checks `symbol_encoding` compatibility (if multi_symbol)
- Scores models by:
  - Number of trained symbols
  - Recency (training_end_timestamp)
  - Version number

**Potential Issues:**
- If no compatible model found, training is triggered
- Compatibility checks might be too strict

### 2.2. Training Script (`train_model.py`)

**Model Discovery:**
- LINE 144-155: Checks for existing compatible model
- If found and not `--force-train`, skips training
- If not found, proceeds with training

**Potential Issues:**
- Model discovery happens before training
- But coverage checks happen in live bot, not training script
- Race condition: training completes, but live bot doesn't see it

---

## STEP 3 – Main Trading Loop Analysis

**NEED TO CHECK:**
- Does `_check_model_coverage()` run in main loop?
- What are all early exit conditions?
- Is there a condition that always evaluates to "not ready"?

---

## STEP 4 – Root Cause Hypothesis

**Most Likely Causes:**

1. **Coverage check runs too frequently**:
   - Called every universe refresh (every 60 minutes)
   - Called on startup
   - Might be called in main loop (NEED TO VERIFY)

2. **Symbols re-queued repeatedly**:
   - Training completes, model reloaded
   - But coverage check doesn't see updated `trained_symbols`
   - Re-queues same symbols

3. **Model reload race condition**:
   - Worker thread reloads model
   - Main thread doesn't see update until periodic check
   - Coverage check uses stale model

4. **Universe refresh triggers re-check**:
   - Every 60 minutes, universe refreshes
   - Coverage check runs again
   - Might re-queue symbols if model not properly updated

---

## STEP 5 – Root Cause Identified & Fixed

### 5.1. Critical Bug Found

**Location**: `live_bot.py` main loop (LINE 1292-1361)

**Issue**: Periodic re-evaluation of blocked symbols ran **every loop iteration** (every 60 seconds) instead of every 5 minutes as intended.

**Code Before Fix:**
```python
# Periodic re-evaluation of blocked symbols (every 5 minutes)
# Check if symbols blocked due to insufficient history now have enough data
if hasattr(self, 'blocked_symbols') and self.blocked_symbols:
    # ... reload model, re-check symbols, re-queue for training ...
```

**Problem**: No timer check! This condition was true every loop if there were blocked symbols, causing:
1. Model reload every 60 seconds
2. Re-checking all blocked symbols
3. Re-queuing symbols for training repeatedly
4. Infinite training/reload loop

### 5.2. Additional Issues Fixed

1. **`_check_model_coverage()` re-queuing**: Added check to skip symbols already training (LINE 299-303)
2. **Better logging**: Added clear messages explaining why symbols are blocked permanently vs temporarily
3. **Timer check**: Added `last_training_check` timer to ensure periodic checks only run every 5 minutes

### 5.3. Fixes Applied

**File**: `live_bot.py`

**Changes**:
1. Added `last_training_check` timer (LINE 1219)
2. Wrapped periodic checks in timer condition (LINE 1275)
3. Added check in `_check_model_coverage()` to skip symbols already training (LINE 299-303)
4. Improved logging for permanently blocked symbols (LINE 327-343)

**Result**: 
- Periodic checks now run every 5 minutes (not every loop)
- Symbols already training are not re-queued
- Model reloads only happen when necessary
- Bot can transition to normal trading loop

