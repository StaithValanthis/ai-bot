# Universe Management

## Overview

The Bybit AI trading bot now supports **dynamic universe discovery** for USDT-margined perpetual futures. Instead of hardcoding a fixed list of symbols, the bot can automatically discover, filter, and select tradable instruments from Bybit's full universe.

## Features

- **Automatic Discovery**: Fetches all USDT-margined perpetual futures from Bybit
- **Liquidity Filtering**: Filters symbols by minimum 24h volume (USD turnover)
- **Price Filtering**: Filters out symbols below a minimum price threshold
- **Whitelist/Blacklist**: Override filters with explicit include/exclude lists
- **Caching**: Caches discovered universe to reduce API calls
- **Portfolio Integration**: Works seamlessly with the portfolio selector for top-K symbol selection

## Configuration

### Universe Mode

The bot supports two modes for symbol selection:

#### Fixed Mode (Default)

```yaml
exchange:
  universe_mode: "fixed"  # Use explicit symbol list
  fixed_symbols: []  # Empty = use trading.symbols from config
```

In fixed mode:
- Uses `trading.symbols` from config (or `fixed_symbols` if specified)
- No API calls for universe discovery
- Backward compatible with existing setups
- Recommended for initial deployment and testing

#### Auto Mode

```yaml
exchange:
  universe_mode: "auto"  # Dynamic discovery
  min_usd_volume_24h: 50000000  # $50M minimum
  min_price: 0.05  # $0.05 minimum
  max_symbols: 30  # Max symbols to include
  universe_refresh_minutes: 60  # Cache refresh interval
```

In auto mode:
- Discovers all USDT-margined perpetuals from Bybit
- Applies liquidity and price filters
- Sorts by volume (descending)
- Clips to `max_symbols` (keeps top N by liquidity)
- Caches results for `universe_refresh_minutes`

### Filtering Parameters

**`min_usd_volume_24h`** (default: $50M)
- Minimum 24-hour USD turnover (volume × price)
- Filters out illiquid symbols
- Higher values = more conservative, fewer symbols

**`min_price`** (default: $0.05)
- Minimum price per unit
- Filters out very low-priced tokens (often volatile/unstable)
- Adjust based on your risk tolerance

**`max_symbols`** (default: 30)
- Maximum number of symbols to include after filtering
- Keeps top N by liquidity
- Lower values = more focused, easier to manage

**`universe_refresh_minutes`** (default: 60)
- How often to refresh the universe cache
- Lower values = more up-to-date but more API calls
- Higher values = fewer API calls but potentially stale data

### Whitelist/Blacklist

```yaml
exchange:
  include_symbols: ["BTCUSDT", "ETHUSDT"]  # Always include these
  exclude_symbols: ["SHIBUSDT", "DOGEUSDT"]  # Always exclude these
```

- **`include_symbols`**: Always included, even if below thresholds (with warning)
- **`exclude_symbols`**: Always excluded, even if above thresholds
- Applied in both fixed and auto modes

## Integration Points

### Live Trading (`live_bot.py`)

- Universe manager initialized on bot startup
- Symbols refreshed if `universe_mode: auto` and cache expired
- All discovered symbols are monitored for signals
- Portfolio selector filters to top-K symbols for actual trading

### Model Training (`train_model.py`)

- If `--symbol` not provided, uses universe or config fallback
- Trains one model per symbol (can run multiple times for multi-symbol)
- Backward compatible: explicit `--symbol` still works

### Research Harness (`research/run_research_suite.py`)

- If `--symbols` not provided, uses universe discovery
- Limits to `max_symbols` for research runs (keeps runs reasonable)
- Logs which symbols were used and why

### Data Pipeline (`scripts/fetch_and_check_data.py`)

- Still requires explicit `--symbol` (for now)
- Can be extended to support universe mode in future

## Portfolio Selector Integration

When `portfolio.cross_sectional.enabled: true`:

1. Universe manager provides candidate symbols (filtered by liquidity/price)
2. Portfolio selector scores all candidates based on:
   - Recent risk-adjusted return (Sharpe-like)
   - Trend strength (ADX)
   - Model confidence
   - Volatility (lower is better)
3. Selects top-K symbols for trading
4. Allocates risk across selected symbols

**Example Flow:**
```
Universe Discovery → 30 symbols (filtered by liquidity)
  ↓
Portfolio Selector → Scores all 30 symbols
  ↓
Top-K Selection → 5 symbols selected
  ↓
Live Trading → Only trades these 5 symbols
```

## Recommended Settings by Profile

### Conservative Profile

```yaml
exchange:
  universe_mode: "fixed"  # Start with fixed symbols for safety
  fixed_symbols: []  # Uses trading.symbols: ["BTCUSDT", "ETHUSDT"]
```

**Rationale**: Fixed mode is safer for initial deployment. Start with 1-2 major symbols.

### Moderate Profile

```yaml
exchange:
  universe_mode: "auto"
  min_usd_volume_24h: 50000000  # $50M
  min_price: 0.10  # $0.10
  max_symbols: 20
```

**Rationale**: Auto discovery with moderate filters. Good balance of opportunity and safety.

### Aggressive Profile

```yaml
exchange:
  universe_mode: "auto"
  min_usd_volume_24h: 20000000  # $20M (lower threshold)
  min_price: 0.05  # $0.05
  max_symbols: 50
```

**Rationale**: More aggressive filters allow more symbols. Higher risk, higher opportunity.

## Caching

Universe discovery results are cached to `data/universe_cache.json`:

```json
{
  "timestamp": "2025-01-15T10:30:00",
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", ...],
  "universe_size": 150
}
```

Cache is refreshed if:
- Cache file doesn't exist
- Cache age > `universe_refresh_minutes`
- `force_refresh=True` is passed to `get_symbols()`

## Logging

The universe manager logs:
- Discovery: Number of USDT perps found
- Filtering: Symbols passed/failed each filter
- Selection: Final symbol list and top symbols
- Cache: Cache hits/misses

Example log output:
```
[INFO] Discovered 150 USDT-margined perpetuals
[INFO] Universe filtering complete:
[INFO]   - Passed filters: 25 symbols
[INFO]   - Filtered out (low volume): 100
[INFO]   - Filtered out (low price): 20
[INFO]   - Filtered out (excluded): 5
[INFO]   - Top symbols: ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', ...]
```

## Troubleshooting

### No Symbols Returned

**Possible causes:**
1. Filters too strict (`min_usd_volume_24h` too high)
2. API error (check logs)
3. Cache stale and API unavailable

**Solutions:**
- Lower `min_usd_volume_24h`
- Check API connectivity
- Use fixed mode as fallback

### Symbols Missing from Universe

**Possible causes:**
1. Below volume/price thresholds
2. In exclude list
3. Not USDT-margined perpetual

**Solutions:**
- Add to `include_symbols` whitelist
- Lower thresholds
- Verify symbol exists on Bybit

### API Rate Limits

**Symptoms:**
- Errors fetching instruments/tickers
- Slow universe refresh

**Solutions:**
- Increase `universe_refresh_minutes` (cache longer)
- Use fixed mode (no API calls)
- Reduce `max_symbols` (fewer ticker requests)

## Safety Considerations

1. **Always start with fixed mode** for initial deployment
2. **Test auto mode on testnet** before mainnet
3. **Monitor universe changes** (new symbols added/removed)
4. **Set reasonable `max_symbols`** (don't try to trade 100+ symbols)
5. **Use portfolio selector** to limit active trading to top-K symbols
6. **Review logs** to understand which symbols are selected and why

## Future Enhancements

Potential improvements:
- Symbol health scoring (beyond liquidity)
- Dynamic threshold adjustment based on market conditions
- Multi-exchange support
- Symbol correlation filtering
- Automatic blacklist of delisted/suspended symbols

