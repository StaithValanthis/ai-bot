# Position Re-attachment Implementation

## Summary

Successfully implemented position re-attachment functionality to ensure the bot properly manages positions after restart.

## Changes Made

### 1. Added `get_open_orders()` Method to BybitClient

**File:** `src/execution/bybit_client.py`

**Purpose:** Retrieve open orders (including conditional stop-loss/take-profit orders) from Bybit exchange.

**Implementation:**
- Fetches open orders for linear perpetuals
- Extracts stop-loss and take-profit prices from conditional orders
- Returns structured order data for position re-attachment

### 2. Added `_load_existing_positions()` Method to TradingBot

**File:** `live_bot.py` (lines 133-223)

**Purpose:** Load existing positions from Bybit on startup and populate `self.positions` for monitoring.

**Behavior:**
1. Fetches all open positions from Bybit exchange
2. Attempts to retrieve stop-loss/take-profit from exchange orders
3. Falls back to config defaults if orders not found
4. Populates `self.positions` dictionary with:
   - Entry price (from exchange)
   - Side (Buy/Sell)
   - Quantity
   - Stop-loss (from orders or config)
   - Take-profit (from orders or config)
   - `loaded_from_exchange` flag

**Error Handling:**
- Logs errors but doesn't fail startup
- Warns if stop-loss/take-profit not found (uses config defaults)
- Continues operation even if position loading fails

### 3. Enhanced `start()` Method

**File:** `live_bot.py` (line 791)

**Change:** Added call to `_load_existing_positions()` at the start of bot initialization.

**Result:** Positions are loaded immediately when bot starts, before entering main trading loop.

### 4. Enhanced `_monitor_positions()` Method

**File:** `live_bot.py` (lines 609-720)

**Improvements:**
1. **Reconciliation:** Detects positions closed externally and removes from tracking
2. **Side Verification:** Checks if position side matches between tracked and exchange state
3. **Untracked Position Detection:** Automatically loads positions found on exchange but not in `self.positions`
4. **Better Error Handling:** More detailed logging and exception handling

**Behavior:**
- Monitors all positions in `self.positions` for stop-loss/take-profit triggers
- Removes positions from tracking if closed externally
- Automatically loads untracked positions found on exchange
- Logs warnings for discrepancies

## How It Works

### On Startup:
1. Bot calls `_load_existing_positions()` in `start()` method
2. Fetches all open positions from Bybit
3. Attempts to get stop-loss/take-profit from exchange orders
4. Falls back to config defaults if not found
5. Populates `self.positions` for monitoring

### During Operation:
1. `_monitor_positions()` runs every minute
2. Fetches current positions from exchange
3. Compares with `self.positions` to detect:
   - Positions closed externally → Remove from tracking
   - Untracked positions on exchange → Load them
4. Monitors all tracked positions for stop-loss/take-profit triggers
5. Closes positions when triggers are hit

## Benefits

1. **Position Safety:** Existing positions are now monitored for stop-loss/take-profit
2. **Restart Resilience:** Bot can safely restart without losing position management
3. **Reconciliation:** Automatically handles positions closed externally
4. **Fallback Safety:** Uses config defaults if exchange orders not found
5. **Error Resilience:** Continues operation even if position loading fails

## Testing Recommendations

1. **Test Restart with Open Positions:**
   - Open a position manually or via bot
   - Restart bot
   - Verify position is loaded and monitored
   - Check logs for "Re-attached to position" message

2. **Test Stop-Loss/Take-Profit:**
   - Open position with known entry price
   - Restart bot
   - Verify stop-loss/take-profit levels are set correctly
   - Monitor that triggers work when price hits levels

3. **Test External Position Closure:**
   - Open position via bot
   - Close position manually on exchange
   - Verify bot detects and removes from tracking

4. **Test Untracked Position:**
   - Open position manually on exchange
   - Start bot
   - Verify bot loads and monitors the position

## Known Limitations

1. **Entry Time Lost:** `entry_time` is set to `None` for re-attached positions (not critical for monitoring)
2. **Stop-Loss/Take-Profit Recovery:** If stop-loss/take-profit orders are not found on exchange, config defaults are used (may differ from original values)
3. **Order Retrieval:** Stop-loss/take-profit retrieval from orders depends on Bybit API response format

## Future Enhancements (Optional)

1. **Persistent Storage:** Store position metadata in JSON file to preserve exact stop-loss/take-profit levels
2. **Position History:** Track position history across restarts
3. **Advanced Reconciliation:** More sophisticated handling of position discrepancies
4. **Order Type Detection:** Better detection of conditional orders vs regular orders

---

**Implementation Date:** 2024  
**Status:** ✅ Complete and Ready for Testing

