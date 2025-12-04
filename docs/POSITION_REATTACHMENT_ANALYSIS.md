# Position Re-attachment Analysis

## Executive Summary

**Current Behavior: Case C - No Re-attachment (Partial Awareness)**

When the bot restarts, it:
- ✅ **Sees** existing positions when checking risk limits (prevents duplicate trades)
- ✅ **Counts** existing positions for health monitoring
- ❌ **Does NOT** monitor existing positions for stop-loss/take-profit
- ❌ **Does NOT** track entry price, stop-loss, or take-profit for positions opened before restart
- ❌ **Does NOT** actively manage positions it didn't open in this session

**Risk Level: HIGH** - Existing positions are left unmanaged until manually closed or until new signals trigger actions.

---

## STEP 0 - Relevant Modules Identified

### Core Files
1. **`live_bot.py`** - Main trading bot class (`TradingBot`)
   - `__init__()` - Initialization (line 44)
   - `start()` - Startup sequence (line 636)
   - `_execute_trade()` - Trade execution (line 439)
   - `_monitor_positions()` - Position monitoring (line 551)
   - `_close_position()` - Position closing (line 578)

2. **`src/execution/bybit_client.py`** - Bybit API wrapper
   - `get_positions()` - Fetches positions from exchange (line 67)

3. **`src/risk/risk_manager.py`** - Risk management
   - `check_risk_limits()` - Checks if trade is allowed (line 110)
   - Uses `open_positions` list to prevent duplicates (line 148-151)

---

## STEP 1 - Startup Behavior Analysis

### 1.1 Initialization (`__init__`)

**Location:** `live_bot.py:44-106`

```python
def __init__(self, config_path: str = "config/config.yaml"):
    # ... component initialization ...
    
    # Data storage
    self.candle_data = {}  # Store candles per symbol
    self.positions = {}  # Track open positions  <-- EMPTY DICT
    self.symbol_confidence_cache = {}  # Cache recent model confidence per symbol
    
    # ... no position loading logic ...
    
    logger.info("Trading bot initialized")
```

**Finding:** 
- `self.positions = {}` is initialized as **empty dictionary**
- **No call** to `self.bybit_client.get_positions()` to fetch existing positions
- **No logic** to populate `self.positions` with existing positions from Bybit

### 1.2 Startup Sequence (`start()`)

**Location:** `live_bot.py:636-678`

```python
def start(self):
    """Start the trading bot"""
    logger.info("=" * 60)
    logger.info("Starting trading bot")
    logger.info("=" * 60)
    
    # Refresh universe if in auto mode
    if self.config['exchange'].get('universe_mode') == 'auto':
        # ... universe refresh logic ...
    
    # Initialize data streams
    symbols = self.trading_symbols
    # ... WebSocket setup ...
    
    self.running = True
    logger.info(f"Bot running. Monitoring {len(symbols)} symbols...")
```

**Finding:**
- **No position loading** in `start()` method
- Bot enters main loop with `self.positions = {}` still empty
- No synchronization with exchange state

---

## STEP 2 - Live Loop Position Usage

### 2.1 Position Monitoring (`_monitor_positions()`)

**Location:** `live_bot.py:551-576`

```python
def _monitor_positions(self):
    """Monitor open positions and check exit conditions"""
    try:
        open_positions = self.bybit_client.get_positions()  # Fetches from exchange
        
        for pos in open_positions:
            symbol = pos['symbol']
            mark_price = pos['mark_price']
            
            if symbol in self.positions:  # <-- CRITICAL: Only monitors tracked positions
                tracked = self.positions[symbol]
                
                # Check stop loss / take profit
                if pos['side'] == 'Buy':  # Long position
                    if mark_price <= tracked['stop_loss']:
                        self._close_position(symbol, "STOP_LOSS")
                    elif mark_price >= tracked['take_profit']:
                        self._close_position(symbol, "TAKE_PROFIT")
                # ... short position logic ...
    
    except Exception as e:
        logger.error(f"Error monitoring positions: {e}")
```

**Finding:**
- **Line 560: `if symbol in self.positions:`** - Only positions in `self.positions` dict are monitored
- If a position exists on Bybit but is NOT in `self.positions`, it is **completely ignored**
- Stop-loss and take-profit checks require `tracked['stop_loss']` and `tracked['take_profit']` from `self.positions`
- **No fallback** to exchange-level stop-loss/take-profit orders

### 2.2 Trade Execution (`_execute_trade()`)

**Location:** `live_bot.py:439-545`

```python
def _execute_trade(self, symbol, direction, confidence, current_price, ...):
    # Get account balance
    balance = self.bybit_client.get_account_balance()
    equity = balance['total_equity']
    
    # Get open positions
    open_positions = self.bybit_client.get_positions()  # <-- Fetches from exchange
    
    # ... position sizing ...
    
    # Check risk limits (use final position size)
    is_allowed, reason = self.risk_manager.check_risk_limits(
        equity=equity,
        open_positions=open_positions,  # <-- Passes exchange positions
        symbol=symbol,
        proposed_size=final_position_size
    )
    
    if not is_allowed:
        logger.warning(f"Trade not allowed: {reason}")
        return
    
    # ... place order ...
    
    # Track position
    self.positions[symbol] = {  # <-- Only adds NEW positions
        'entry_price': current_price,
        'side': side,
        'qty': final_position_size,
        'entry_time': datetime.utcnow(),
        'stop_loss': stop_loss,
        'take_profit': take_profit
    }
```

**Finding:**
- **Line 462:** Fetches `open_positions` from exchange (sees existing positions)
- **Line 490-495:** Passes positions to risk manager (prevents duplicates)
- **Line 538-545:** Only adds NEW positions to `self.positions` dict
- **Existing positions are NOT added** to `self.positions` on startup

### 2.3 Risk Manager Check

**Location:** `src/risk/risk_manager.py:148-151`

```python
# Check if already have position in this symbol
for pos in open_positions:
    if pos.get('symbol') == symbol:
        return False, f"Already have position in {symbol}"
```

**Finding:**
- Risk manager **sees** existing positions and blocks duplicate trades
- This is a **passive check** - it prevents new trades but doesn't manage existing ones

---

## STEP 3 - Explicit Answer to Restart/Re-attach Question

### 3.1 Current Behavior Classification

**Case C: No Re-attachment (with Partial Awareness)**

The bot does **NOT** properly re-attach to existing positions. Here's what happens:

#### What the Bot DOES:
1. **Sees existing positions** when checking risk limits (`_execute_trade()` line 462)
2. **Prevents duplicate trades** in same symbol (risk manager line 148-151)
3. **Counts positions** for health monitoring (line 712-713)
4. **Respects max_open_positions** limit (risk manager line 140)

#### What the Bot DOES NOT:
1. **Does NOT load positions** into `self.positions` on startup
2. **Does NOT monitor stop-loss/take-profit** for existing positions (line 560 check fails)
3. **Does NOT track entry price** for existing positions
4. **Does NOT actively manage** positions opened before restart

### 3.2 Specific Behavior on Restart

**Scenario:** Bot restarts with 2 open positions on Bybit (BTCUSDT long, ETHUSDT short)

1. **On Startup:**
   - `self.positions = {}` (empty)
   - No position loading logic executed
   - Bot enters main loop

2. **In Main Loop:**
   - `_monitor_positions()` is called every minute (line 688)
   - Fetches positions from exchange: `[BTCUSDT, ETHUSDT]`
   - **Line 560 check:** `if symbol in self.positions:` → **FALSE** for both
   - **Result:** No stop-loss/take-profit monitoring for these positions

3. **When New Signal Arrives:**
   - `_execute_trade()` fetches positions (line 462)
   - Risk manager sees existing positions (line 148-151)
   - **Blocks** new trade in BTCUSDT or ETHUSDT (duplicate prevention)
   - **Allows** new trade in other symbols (if under max_open_positions)

4. **If Position Hits Stop-Loss:**
   - **Bot does NOT detect it** (not in `self.positions`)
   - Position remains open until:
     - Manually closed by user
     - New signal triggers action (but blocked by duplicate check)
     - Exchange-level stop-loss triggers (if set via API)

### 3.3 Position Metadata Loss

**In-Memory State (Lost on Restart):**
- `entry_price` - Used for PnL calculation
- `entry_time` - Used for trade logging
- `stop_loss` - Used for exit monitoring
- `take_profit` - Used for exit monitoring
- `qty` - Position size

**Exchange State (Persists):**
- Position size (`pos['size']`)
- Entry price (`pos['avgPrice']` from exchange)
- Mark price (`pos['markPrice']`)
- Unrealized PnL (`pos['unrealisedPnl']`)
- Side (`pos['side']`)

**Critical Gap:**
- Exchange does NOT store bot's intended stop-loss/take-profit levels
- These are only in `self.positions` dict (lost on restart)
- Bot cannot recover these values

---

## STEP 4 - Recommended Robust Behavior

### 4.1 What SHOULD Happen

#### On Startup:
1. **Fetch all open positions** from Bybit
2. **Populate `self.positions`** with existing positions
3. **Reconstruct stop-loss/take-profit** from:
   - Exchange-level orders (if bot set them via API)
   - Config defaults (if exchange orders not found)
   - Or use exchange's current stop-loss/take-profit if available
4. **Log warning** for positions without stop-loss/take-profit
5. **Attach monitoring** to all positions

#### In Main Loop:
1. **Periodic reconciliation** (every N minutes):
   - Fetch positions from exchange
   - Compare with `self.positions`
   - Handle discrepancies (position closed externally, etc.)
2. **Always monitor** all positions in `self.positions`
3. **Fallback to exchange state** if in-memory state is missing

### 4.2 Minimal Implementation Changes

#### Change 1: Add `_load_existing_positions()` Method

**Location:** `live_bot.py` (add after `__init__`)

```python
def _load_existing_positions(self):
    """
    Load existing positions from Bybit and populate self.positions.
    Called on startup to re-attach to positions opened before restart.
    """
    try:
        logger.info("Loading existing positions from Bybit...")
        open_positions = self.bybit_client.get_positions()
        
        if not open_positions:
            logger.info("No existing positions found")
            return
        
        logger.info(f"Found {len(open_positions)} existing position(s)")
        
        for pos in open_positions:
            symbol = pos['symbol']
            entry_price = pos['entry_price']  # From exchange
            side = pos['side']
            qty = pos['size']
            
            # Try to get stop-loss/take-profit from exchange orders
            # (Bybit API: get_open_orders with stop_loss/take_profit)
            # For now, use config defaults as fallback
            stop_loss_pct = self.config['risk']['stop_loss_pct']
            take_profit_pct = self.config['risk']['take_profit_pct']
            
            if side == 'Buy':  # Long
                stop_loss = entry_price * (1 - stop_loss_pct)
                take_profit = entry_price * (1 + take_profit_pct)
            else:  # Short
                stop_loss = entry_price * (1 + stop_loss_pct)
                take_profit = entry_price * (1 - take_profit_pct)
            
            # Populate self.positions
            self.positions[symbol] = {
                'entry_price': entry_price,
                'side': side,
                'qty': qty,
                'entry_time': None,  # Lost, but not critical
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'loaded_from_exchange': True  # Flag to indicate re-attached
            }
            
            logger.info(f"Re-attached to position: {symbol} {side} {qty} @ {entry_price}")
            logger.warning(f"  Stop-loss: {stop_loss:.2f}, Take-profit: {take_profit:.2f} (using config defaults)")
        
    except Exception as e:
        logger.error(f"Error loading existing positions: {e}")
        # Don't fail startup, but log error
```

#### Change 2: Call `_load_existing_positions()` in `start()`

**Location:** `live_bot.py:636` (modify `start()` method)

```python
def start(self):
    """Start the trading bot"""
    logger.info("=" * 60)
    logger.info("Starting trading bot")
    logger.info("=" * 60)
    
    # Load existing positions from exchange
    self._load_existing_positions()  # <-- ADD THIS
    
    # Refresh universe if in auto mode
    # ... rest of method ...
```

#### Change 3: Enhance `_monitor_positions()` for Reconciliation

**Location:** `live_bot.py:551` (modify `_monitor_positions()`)

```python
def _monitor_positions(self):
    """Monitor open positions and check exit conditions"""
    try:
        open_positions = self.bybit_client.get_positions()
        exchange_positions_dict = {pos['symbol']: pos for pos in open_positions}
        
        # Monitor tracked positions
        for symbol, tracked in list(self.positions.items()):
            if symbol in exchange_positions_dict:
                pos = exchange_positions_dict[symbol]
                mark_price = pos['mark_price']
                
                # Check stop loss / take profit
                if pos['side'] == 'Buy':  # Long position
                    if mark_price <= tracked['stop_loss']:
                        self._close_position(symbol, "STOP_LOSS")
                    elif mark_price >= tracked['take_profit']:
                        self._close_position(symbol, "TAKE_PROFIT")
                else:  # Short position
                    if mark_price >= tracked['stop_loss']:
                        self._close_position(symbol, "STOP_LOSS")
                    elif mark_price <= tracked['take_profit']:
                        self._close_position(symbol, "TAKE_PROFIT")
            else:
                # Position closed externally (not by bot)
                logger.warning(f"Position {symbol} closed externally, removing from tracking")
                del self.positions[symbol]
        
        # Detect positions on exchange not in self.positions (shouldn't happen, but handle it)
        for symbol, pos in exchange_positions_dict.items():
            if symbol not in self.positions:
                logger.warning(f"Found untracked position {symbol} on exchange - loading now")
                # Optionally call _load_existing_positions() or handle inline
        
    except Exception as e:
        logger.error(f"Error monitoring positions: {e}")
```

#### Change 4: (Optional) Store Position Metadata Persistently

For more robust recovery, consider storing position metadata in a JSON file:

```python
# On position open: save to data/positions_state.json
# On startup: load from data/positions_state.json
# On position close: remove from file
```

This would preserve entry_time and exact stop-loss/take-profit levels across restarts.

---

## STEP 5 - Final Summary

### 5.1 Does the bot re-attach on restart?

**NO** - The bot does NOT properly re-attach to existing positions.

### 5.2 Current Behavior Details

**What Works:**
- Bot sees existing positions when checking risk limits
- Prevents opening duplicate positions
- Counts positions for health monitoring

**What Doesn't Work:**
- Bot does NOT monitor stop-loss/take-profit for existing positions
- Bot does NOT track entry price/metadata for existing positions
- Bot does NOT actively manage positions opened before restart

**Code Evidence:**
- `live_bot.py:95` - `self.positions = {}` initialized empty
- `live_bot.py:636` - `start()` has no position loading
- `live_bot.py:560` - `if symbol in self.positions:` - only monitors tracked positions
- `live_bot.py:538` - Only NEW positions added to `self.positions`

### 5.3 Recommended Fix

**Minimal Changes Required:**
1. Add `_load_existing_positions()` method to fetch and populate `self.positions`
2. Call it in `start()` method
3. Enhance `_monitor_positions()` for reconciliation

**Estimated Effort:** 1-2 hours for basic implementation, 3-4 hours for robust version with persistent storage.

**Priority:** **HIGH** - This is a critical gap that could lead to unmanaged positions and unexpected losses.

---

## Appendix: Code References

| Location | Line | Description |
|----------|------|-------------|
| `live_bot.py` | 95 | `self.positions = {}` - Empty dict initialization |
| `live_bot.py` | 636 | `start()` - No position loading |
| `live_bot.py` | 462 | `_execute_trade()` - Fetches positions for risk check |
| `live_bot.py` | 538 | `_execute_trade()` - Only adds NEW positions |
| `live_bot.py` | 551 | `_monitor_positions()` - Main monitoring loop |
| `live_bot.py` | 560 | `_monitor_positions()` - Critical check: `if symbol in self.positions` |
| `live_bot.py` | 688 | Main loop - Calls `_monitor_positions()` every minute |
| `src/risk/risk_manager.py` | 148 | Checks for duplicate positions |
| `src/execution/bybit_client.py` | 67 | `get_positions()` - Fetches from exchange |

---

**Document Version:** 1.0  
**Date:** 2024  
**Author:** Code Analysis

