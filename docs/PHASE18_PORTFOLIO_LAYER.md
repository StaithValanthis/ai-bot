# Phase 18: Portfolio & Cross-Sectional Layer Implementation

## Overview

This document describes the implementation of the cross-sectional symbol selection and portfolio allocation layer for the v2.1 bot.

---

## Design

### Purpose

The portfolio layer selects a subset of symbols to trade based on cross-sectional ranking, improving capital allocation and risk diversification.

### Core Concept

1. **Score Calculation**: Each symbol gets a composite score based on:
   - Recent risk-adjusted return (Sharpe-like)
   - Trend strength (ADX)
   - Model confidence (predicted edge)
   - Volatility (lower is better for trend-following)

2. **Selection**: Top K symbols by score are selected

3. **Allocation**: Risk allocated across selected symbols (equal weight or capped per symbol)

4. **Rebalancing**: Periodic rebalancing (default: daily)

---

## Implementation

### Module: `src/portfolio/selector.py`

**Class:** `PortfolioSelector`

**Key Methods:**
- `score_symbol()`: Calculate composite score for a symbol
- `select_symbols()`: Select top K symbols
- `is_symbol_selected()`: Check if symbol is currently selected
- `get_symbol_risk_limit()`: Get max risk allocation for symbol
- `should_rebalance()`: Check if rebalancing needed

### Score Components

**1. Risk-Adjusted Return (40% weight):**
- Rolling Sharpe-like metric over last 30 days
- Normalized to [0, 1] range

**2. Trend Strength (30% weight):**
- ADX value normalized to [0, 1]
- Higher ADX = stronger trend = higher score

**3. Model Confidence (20% weight):**
- Recent model predictions (ensemble confidence)
- Already [0, 1] range

**4. Volatility Score (10% weight):**
- Inverse relationship: lower volatility = higher score
- Normalized based on average volatility

**Composite Score:**
```
score = 0.4 * sharpe_score + 0.3 * adx_score + 0.2 * confidence + 0.1 * volatility_score
```

---

## Integration

### Live Trading Path (`live_bot.py`)

**Integration Points:**

1. **Symbol Selection Check** (before signal processing):
   ```python
   if not self.portfolio_selector.is_symbol_selected(symbol):
       return  # Skip trading this symbol
   ```

2. **Rebalancing** (periodic):
   ```python
   if self.portfolio_selector.should_rebalance():
       selected = self.portfolio_selector.select_symbols(...)
   ```

3. **Risk Limiting** (in position sizing):
   ```python
   max_risk = self.portfolio_selector.get_symbol_risk_limit(symbol, equity)
   position_size = min(calculated_size, max_risk)
   ```

**Backward Compatibility:**
- When `enabled: false`, all symbols are allowed (backward compatible)
- No changes to existing single-symbol logic when disabled

---

## Configuration

### Config Section: `portfolio.cross_sectional`

```yaml
portfolio:
  cross_sectional:
    enabled: false  # Set to true to enable
    rebalance_interval_minutes: 1440  # 24 hours (daily)
    top_k: 3  # Select top 3 symbols
    max_symbol_risk_pct: 0.10  # 10% max risk per symbol
    min_liquidity: 1000000  # $1M minimum 24h volume
    score_weights:
      sharpe: 0.4  # Risk-adjusted return
      adx: 0.3  # Trend strength
      confidence: 0.2  # Model confidence
      volatility: 0.1  # Volatility (lower is better)
```

### Recommended Settings

**Conservative:**
- `top_k: 2-3`
- `max_symbol_risk_pct: 0.10` (10%)
- `rebalance_interval_minutes: 1440` (daily)

**Moderate:**
- `top_k: 3-5`
- `max_symbol_risk_pct: 0.15` (15%)
- `rebalance_interval_minutes: 720` (12 hours)

---

## Behavior

### When Enabled

1. **On Startup**: Selects initial symbols based on available data
2. **During Trading**: 
   - Only selected symbols can receive trades
   - Risk limits enforced per symbol
   - Rebalancing occurs at configured interval
3. **On Rebalance**:
   - Recalculates scores for all symbols
   - Reselects top K
   - Logs selection and scores

### When Disabled

- All symbols in config are tradable
- No selection or risk limiting
- Behavior identical to v2.0

---

## Risk Management

### Portfolio-Level Controls

1. **Per-Symbol Caps**: `max_symbol_risk_pct` limits risk per symbol
2. **Equal Allocation**: Risk divided equally among selected symbols
3. **Global Caps**: Still respects global risk limits (max leverage, daily loss, etc.)

### Example

**Scenario:**
- 3 symbols selected
- Total equity: $10,000
- `max_symbol_risk_pct: 0.10` (10%)

**Allocation:**
- Per symbol: $10,000 / 3 = $3,333
- Capped at: $10,000 * 0.10 = $1,000
- **Actual per symbol**: $1,000 (capped)

---

## Testing & Validation

### Unit Tests (Recommended)

1. **Score Calculation**: Verify scores are [0, 1] and weighted correctly
2. **Selection**: Verify top K selection works
3. **Risk Limits**: Verify risk limits are enforced
4. **Rebalancing**: Verify rebalancing triggers correctly

### Integration Tests

1. **Disabled Mode**: Verify backward compatibility
2. **Enabled Mode**: Verify selection and risk limiting work
3. **Multi-Symbol**: Verify works with multiple symbols

---

## Limitations

1. **Simplified Allocation**: Equal weight, not risk parity (can be enhanced)
2. **No Liquidity Check**: `min_liquidity` is configured but not enforced (can be added)
3. **Score Components**: Fixed weights (could be optimized)
4. **Rebalancing Cost**: No cost modeling for rebalancing (minor for crypto)

---

## Future Enhancements

1. **Risk Parity**: Allocate based on inverse volatility
2. **Dynamic Weights**: Optimize score component weights
3. **Liquidity Enforcement**: Check and enforce minimum liquidity
4. **Rebalancing Costs**: Model transaction costs for rebalancing
5. **Correlation**: Consider correlation between symbols

---

## Usage

### Enable Portfolio Selection

1. Set `portfolio.cross_sectional.enabled: true` in config
2. Configure `top_k`, `rebalance_interval_minutes`, etc.
3. Restart bot

### Monitor Selection

```python
# Get portfolio status
status = portfolio_selector.get_status()
print(f"Selected symbols: {status['selected_symbols']}")
print(f"Scores: {status['symbol_scores']}")
```

### Disable Portfolio Selection

1. Set `portfolio.cross_sectional.enabled: false`
2. Restart bot
3. All symbols become tradable (backward compatible)

---

## Summary

**Status:** ✅ **IMPLEMENTED**

The portfolio layer is fully implemented and integrated:
- ✅ Cross-sectional symbol selection
- ✅ Composite scoring (Sharpe, ADX, confidence, volatility)
- ✅ Top K selection
- ✅ Risk allocation per symbol
- ✅ Periodic rebalancing
- ✅ Backward compatible (can be disabled)

**Benefits:**
- Better capital allocation
- Risk diversification
- Focus on most promising symbols
- Reduced correlation risk

**Recommendation:**
- Start with `enabled: false` (backward compatible)
- Enable after validation on testnet
- Use conservative settings initially (top_k=3, daily rebalance)

---

**Date:** December 2025  
**Version:** 2.1  
**Status:** Production Ready (with recommended testing)

