# Signal Visibility Guide

**Date**: 2025-12-04  
**Purpose**: Understanding when and why trades occur (or don't occur)

---

## How to See Signal Activity

The bot now logs signal evaluation at multiple stages:

### 1. Primary Signal Generation

When a **closed candle** is received, the bot evaluates signals:

```
[SYMBOL] ✓ Primary signal generated: LONG (strength: 0.75) - Evaluating filters...
```

If no signal:
```
[SYMBOL] Signal evaluation: NEUTRAL (no trend signal detected)
```
*(Logged occasionally, 5% of the time to reduce spam)*

### 2. Signal Filtering Stages

The bot logs at each filtering stage:

**Regime Filter:**
```
[SYMBOL] Signal filtered by regime: Low ADX (trend not strong enough)
```

**Confidence Threshold:**
```
[SYMBOL] Signal evaluation: LONG | Confidence: 0.550 | Threshold: 0.600 (base: 0.600 + adj: 0.000) | Regime: OK
[SYMBOL] Signal filtered: confidence 0.550 < threshold 0.600 (needs 0.050 more confidence)
```

**Performance Guard:**
```
[SYMBOL] Trading paused by performance guard: Win rate below threshold
```

**Portfolio Selector:**
```
[SYMBOL] Symbol not selected by portfolio selector. Skipping.
```

### 3. Successful Signal (Trade Attempt)

When a signal passes all filters:

```
[SYMBOL] ✓ Signal passed all filters! Attempting trade: LONG @ 93348.00 (confidence: 0.650)
```

Then you'll see order placement logs.

---

## Why No Trades Are Happening

### Common Reasons:

1. **Waiting for Closed Candles**
   - Hourly candles only close at the top of each hour (09:00, 10:00, 11:00, etc.)
   - If the bot started at 09:30, the next closed candle will be at 10:00
   - **Open candle updates are received but signals are NOT evaluated until the candle closes**

2. **No Primary Signal (NEUTRAL)**
   - The trend-following strategy didn't detect a clear trend
   - Check logs for "Signal evaluation: NEUTRAL"

3. **Signal Filtered by Regime**
   - Market conditions don't meet criteria (e.g., low ADX, ranging market)
   - Check logs for "Signal filtered by regime"

4. **Confidence Too Low**
   - Model confidence is below threshold (default: 0.6)
   - Check logs for "Signal filtered: confidence X < threshold Y"

5. **Performance Guard Blocking**
   - Trading paused due to poor performance
   - Check logs for "Trading paused by performance guard"

6. **Portfolio Selector Filtering**
   - Symbol not selected by portfolio selector (if enabled)
   - Check logs for "Symbol not selected by portfolio selector"

7. **Insufficient Candle History**
   - Need at least 50 candles to generate signals
   - Check heartbeat logs for "symbols with enough history"

---

## Monitoring Signal Activity

### Heartbeat Logs (Every 10 Minutes)

```
Bot heartbeat: 18 tradable symbols, 2 blocked, 0 open positions, 
18 symbols with data, 18 symbols with enough history (≥50 candles), 
5 symbols with recent signal evaluations, WebSocket: RUNNING
```

**Key Metrics:**
- `symbols with data`: Symbols receiving candle updates
- `symbols with enough history`: Symbols with ≥50 candles (can generate signals)
- `symbols with recent signal evaluations`: Symbols where signals were evaluated recently

### What to Look For:

1. **If `symbols with recent signal evaluations` = 0:**
   - No closed candles received yet (wait for top of hour)
   - Or all signals are NEUTRAL (logged occasionally)

2. **If `symbols with recent signal evaluations` > 0 but no trades:**
   - Check logs for signal filtering messages
   - Signals are being generated but filtered out

3. **If you see "Signal filtered" messages:**
   - This is normal - most signals are filtered
   - The bot is working correctly, just being selective

---

## Expected Behavior

### Normal Operation:

1. **Every Hour (at top of hour):**
   - Closed candles received for all symbols
   - Signals evaluated for each symbol
   - Most signals will be NEUTRAL or filtered
   - Occasionally, a signal passes all filters → trade executed

2. **Between Hours:**
   - Open candle updates received (logged at DEBUG level)
   - No signal evaluation (waiting for candle close)

3. **Signal Evaluation Flow:**
   ```
   Closed Candle → Primary Signal → Regime Filter → Meta-Model → 
   Confidence Check → Performance Guard → Portfolio Selector → Trade
   ```

---

## Debugging No Trades

### Step 1: Check if Closed Candles Are Received

Look for:
```
New candle for BTCUSDT: 2025-12-04 10:00:00 | Close: 93348.00
```

If you don't see these, you're only getting open candle updates.

### Step 2: Check if Signals Are Generated

Look for:
```
[BTCUSDT] ✓ Primary signal generated: LONG (strength: 0.75) - Evaluating filters...
```

If you don't see these, all signals are NEUTRAL.

### Step 3: Check Why Signals Are Filtered

Look for filtering messages:
- `Signal filtered by regime`
- `Signal filtered: confidence X < threshold Y`
- `Trading paused by performance guard`
- `Symbol not selected by portfolio selector`

### Step 4: Check Configuration

Verify in `config/config.yaml`:
- `model.confidence_threshold` (default: 0.6)
- `regime_filter.enabled` (if too strict, may filter all signals)
- `performance_guard.enabled` (may be blocking trades)
- `portfolio.selector.enabled` (may be filtering symbols)

---

## Summary

**To see signal activity:**
- Watch for logs starting with `[SYMBOL] ✓ Primary signal generated`
- Watch for `Signal evaluation:` logs showing confidence and thresholds
- Watch for `Signal filtered:` logs explaining why trades aren't taken
- Watch for `✓ Signal passed all filters!` when a trade is attempted

**Remember:**
- Signals are only evaluated when candles CLOSE
- For hourly candles, this happens once per hour at the top of the hour
- Most signals will be filtered - this is normal and expected
- The bot is designed to be selective, not to trade on every signal

