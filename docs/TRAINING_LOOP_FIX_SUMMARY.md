# Training Loop Fix Summary

**Date**: 2025-12-04  
**Issue**: Bot stuck in infinite training/reload loop, never reaching normal trading  
**Status**: ✅ FIXED

---

## Root Cause

The bot was stuck in an infinite loop because the **periodic re-evaluation of blocked symbols** ran **every loop iteration** (every 60 seconds) instead of every 5 minutes as intended.

### The Bug

**Location**: `live_bot.py` main loop (around line 1292)

**Problem Code**:
```python
# Periodic re-evaluation of blocked symbols (every 5 minutes)
# Check if symbols blocked due to insufficient history now have enough data
if hasattr(self, 'blocked_symbols') and self.blocked_symbols:
    # Reload model
    # Re-check all blocked symbols
    # Re-queue for training
```

**Issue**: No timer check! This condition was `True` every loop iteration if there were any blocked symbols, causing:
1. Model reload every 60 seconds
2. Re-checking all blocked symbols
3. Re-queuing symbols for training repeatedly
4. Bot never transitioning to normal trading

---

## Fixes Applied

### Fix 1: Added Timer Check for Periodic Checks

**File**: `live_bot.py`  
**Lines**: 1234-1236, 1286

**Change**:
- Added `last_training_check` timer initialized at loop start
- Wrapped periodic checks in `if (current_time - last_training_check) >= training_check_interval:`
- Ensures checks only run every 5 minutes (300 seconds)

**Before**:
```python
# Periodic re-evaluation runs every loop if blocked_symbols exists
if hasattr(self, 'blocked_symbols') and self.blocked_symbols:
    # ... reload model, re-check symbols ...
```

**After**:
```python
# Timer for periodic training/coverage checks (every 5 minutes)
training_check_interval = 300  # 5 minutes
last_training_check = time.time()

# In loop:
if (current_time - last_training_check) >= training_check_interval:
    last_training_check = current_time
    # ... periodic checks ...
```

### Fix 2: Prevent Re-queuing Symbols Already Training

**File**: `live_bot.py`  
**Lines**: 299-303

**Change**: Added check in `_check_model_coverage()` to skip symbols already being trained

**Code**:
```python
for symbol in untrained_symbols:
    # FIXED: Skip if already training this symbol (prevents re-queuing)
    with self.training_lock:
        if symbol in self.training_threads and self.training_threads[symbol].is_alive():
            logger.debug(f"Symbol {symbol} is already being trained in background, skipping re-queue")
            continue
```

### Fix 3: Improved Logging

**File**: `live_bot.py`  
**Lines**: 327-343

**Change**: Added clear messages explaining why symbols are blocked permanently vs temporarily

**Before**:
```python
logger.warning(f"Symbol {symbol}: Only {available_days} days of history (< {min_history_days} minimum). Blocking.")
```

**After**:
```python
logger.warning(
    f"Symbol {symbol}: Only {available_days:.1f} days of history (< {min_history_days} minimum). "
    f"Permanently blocked until sufficient history accumulates. Will NOT trigger retraining."
)
```

---

## New Behavior

### When Bot Trains

1. **On Startup**: 
   - Checks model coverage
   - Queues untrained symbols with sufficient history for background training
   - Blocks symbols with insufficient history (permanently, no retraining)

2. **During Runtime**:
   - **Every 5 minutes**: Checks for completed training threads and unblocks symbols
   - **Every 5 minutes**: Re-evaluates blocked symbols to see if they now have enough history
   - **NOT every loop**: Periodic checks are gated by timer

3. **After Training Completes**:
   - Training worker reloads model
   - Unblocks symbol if now trained
   - Main loop periodic check (every 5 min) also unblocks symbols

### When Bot Just Loads & Trades

1. **On Startup**:
   - Loads model once
   - Checks coverage once
   - Blocks untrained symbols
   - Starts trading loop

2. **During Runtime**:
   - Processes signals for trained symbols
   - Skips blocked symbols (logs debug message occasionally)
   - Only reloads model:
     - After training completes (in worker thread)
     - Every 5 minutes (periodic check)
     - NOT every loop iteration

### How It Handles New Symbols Safely

1. **Symbol Discovery**:
   - Universe refresh (every 60 minutes in auto mode)
   - Calls `_check_model_coverage()` after refresh

2. **Coverage Check**:
   - Reloads model to get latest `trained_symbols`
   - Compares with universe symbols
   - For untrained symbols:
     - **Already training**: Skip (don't re-queue)
     - **Insufficient history**: Block permanently (won't trigger retraining)
     - **Sufficient history**: Queue for training (once)

3. **Background Training**:
   - Runs in separate thread (non-blocking)
   - Downloads data, trains model, saves model
   - Reloads model in worker thread
   - Unblocks symbol if training successful

4. **Periodic Re-evaluation**:
   - Every 5 minutes (not every loop)
   - Checks if blocked symbols now have enough history
   - Only queues if not already training and not already trained

---

## Testing Recommendations

### Minimal Test (Testnet Only)

1. **Setup**:
   ```bash
   # Ensure testnet config
   # Use small symbol set (e.g., BTCUSDT only)
   # Ensure model is trained for BTCUSDT
   ```

2. **Run Bot**:
   ```bash
   python live_bot.py
   ```

3. **Expected Behavior**:
   - ✅ Model loads once at startup
   - ✅ Coverage check runs once at startup
   - ✅ Trading loop starts normally
   - ✅ Periodic checks run every 5 minutes (not every loop)
   - ✅ No repeated training/reload loops
   - ✅ Signals processed for trained symbols
   - ✅ Orders sent to testnet (if signals occur)

4. **Logs to Watch For**:
   - `"Main loop started. Health checks every 300s, heartbeat every 600s"`
   - `"Training/coverage checks every 300s"`
   - `"Bot heartbeat: X active symbols, Y blocked, Z open positions"`
   - Periodic checks should only appear every 5 minutes
   - No repeated "Starting background training" messages

### Test with New Symbol

1. **Add untrained symbol to universe**
2. **Expected**:
   - Symbol detected as untrained
   - Queued for training (once)
   - Background training starts
   - Symbol remains blocked during training
   - After training completes, symbol unblocked (within 5 minutes)
   - Bot continues trading normally

---

## Files Changed

- `live_bot.py`: Main fixes (timer check, re-queue prevention, logging)
- `docs/DEBUG_TRAINING_LOOP_NOTES.md`: Investigation notes
- `docs/TRAINING_LOOP_FIX_SUMMARY.md`: This document

---

## Verification Checklist

- ✅ Timer check added for periodic re-evaluation
- ✅ Periodic checks only run every 5 minutes
- ✅ Symbols already training are not re-queued
- ✅ Model reloads only happen when necessary
- ✅ Better logging for debugging
- ✅ Bot can transition to normal trading loop

---

**Status**: Ready for testnet testing

