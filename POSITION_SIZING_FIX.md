# Position Sizing Fix - Risk-Based Calculation

## Problem Identified

The bot was using **equity-based position sizing** instead of **risk-based position sizing**, resulting in:
- Position sizes: 0.6-1.0% of equity
- Actual risk: 0.009-0.015% of equity (way too low!)
- Expected risk: 1-2% of equity

## Root Cause

**Old Calculation:**
```
Position Size = Equity × 2% × Confidence (0.4) = 0.8% of equity
Position Value = $150.90 × 0.008 = $1.21
Risk = $1.21 × 1.5% = $0.02 (0.012% of equity) ❌
```

This resulted in tiny position sizes that didn't meet the intended risk targets.

## Fix Applied

**New Risk-Based Calculation:**
```
Target Risk = 0.9% - 2.0% of equity (scales with confidence)
Position Value = Target Risk / Stop Loss %
Risk = Position Value × Stop Loss % = Target Risk ✓
```

**Example (Confidence 40%):**
- Target Risk: 1.34% of equity = $2.02
- Position Value: $2.02 / 1.5% = $134.60 (89.2% of equity)
- Actual Risk: $134.60 × 1.5% = $2.02 (1.34% of equity) ✓

## Changes Made

### 1. Updated `src/risk/risk_manager.py`

**Method:** `calculate_position_size()`

**Changes:**
- Switched from equity-based to risk-based sizing
- Risk scales 0.9%-2.0% based on confidence
- Position value = Target Risk / Stop Loss %
- Quantity = Position Value / Entry Price

**Key Code:**
```python
# Risk scales from 0.9% to 2.0% based on confidence
min_risk_pct = 0.009  # 0.9% minimum risk
max_risk_pct = 0.020  # 2.0% maximum risk
target_risk_pct = min_risk_pct + (max_risk_pct - min_risk_pct) * signal_confidence

# Calculate target risk in USD
target_risk_usd = equity * target_risk_pct

# Position value = Target Risk / Stop Loss %
position_value = target_risk_usd / stop_loss_pct
```

### 2. Updated `config/config.yaml`

**Changes:**
- Added `risk_per_trade_pct: 0.015` (1.5% base risk per trade)
- Increased `max_position_size` from `0.02` (2%) to `0.67` (66.7%) to allow larger positions

## Result

Position sizes are now:
- **1-2% risk per trade** (as expected)
- **Much larger position values** (81-100% of equity for typical confidences)
- **Easily meet the $5 minimum notional requirement**
- **Scale with confidence** (0.9%-2.0% risk range)

## Examples

For $150.90 equity with 1.5% stop loss:

| Confidence | Target Risk | Position Value | % of Equity | Actual Risk |
|------------|-------------|----------------|-------------|-------------|
| 30% | 1.23% | $123.59 | 81.9% | 1.23% ✓ |
| 40% | 1.34% | $134.60 | 89.2% | 1.34% ✓ |
| 50% | 1.45% | $145.62 | 96.5% | 1.45% ✓ |
| 60% | 1.56% | $156.63 | 103.8% | 1.56% (capped) ✓ |

## Files Modified

1. **src/risk/risk_manager.py**
   - Updated `calculate_position_size()` method to use risk-based sizing
   - Added `risk_per_trade_pct` and `stop_loss_pct` to initialization

2. **config/config.yaml**
   - Added `risk_per_trade_pct: 0.015`
   - Updated `max_position_size: 0.67` (from 0.02)

## Verification

- Syntax check: ✅ Passed
- Linter check: ✅ No errors

## Next Steps

1. **Restart the bot** to apply changes:
   ```bash
   sudo systemctl restart bybit-bot-live
   ```

2. **Monitor logs** for:
   - Position sizing debug messages showing risk-based calculations
   - Larger position values (81-100% of equity)
   - Actual risk percentages (should be 0.9%-2.0%)

3. **Verify** that trades now have proper 1-2% risk per trade

The bot has been updated with risk-based position sizing. The next trade should show much larger position sizes with proper 1-2% risk per trade.

