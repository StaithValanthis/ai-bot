# Universe Feature Summary

## Overview

The bot has been enhanced from a **fixed-symbol** system to a **universe-aware, multi-symbol scanner** for Bybit USDT-perpetual futures. This allows the bot to dynamically discover, filter, and trade across a broader set of instruments while maintaining strict risk controls.

## Key Changes

### 1. Universe Discovery Module (`src/exchange/universe.py`)

**New Class**: `UniverseManager`

**Responsibilities**:
- Discovers all USDT-margined perpetual futures from Bybit
- Applies liquidity and price filters
- Caches results for efficiency
- Supports both "auto" (dynamic) and "fixed" (explicit list) modes

**Key Methods**:
- `get_symbols(force_refresh=False)`: Returns filtered symbol list
- `_discover_universe()`: Fetches instruments from Bybit API
- `_filter_universe()`: Applies volume/price/exclude filters
- `_get_ticker_data()`: Fetches 24h volume and price data

### 2. Configuration Updates (`config/config.yaml`)

**New Settings**:
```yaml
exchange:
  universe_mode: "fixed"  # or "auto"
  fixed_symbols: []  # Used when mode="fixed"
  min_usd_volume_24h: 50000000  # $50M minimum
  min_price: 0.05  # Minimum price
  max_symbols: 30  # Max symbols after filtering
  universe_refresh_minutes: 60  # Cache refresh interval
  include_symbols: []  # Whitelist
  exclude_symbols: []  # Blacklist
```

**Default**: `universe_mode: "fixed"` (backward compatible)

### 3. Integration Points

#### Live Trading (`live_bot.py`)
- Initializes `UniverseManager` on startup
- Gets symbols from universe (or config fallback)
- Refreshes universe if `auto` mode and cache expired
- All discovered symbols monitored; portfolio selector picks top-K

#### Model Training (`train_model.py`)
- If `--symbol` not provided, uses universe or config
- Backward compatible: explicit `--symbol` still works

#### Research Harness (`research/run_research_suite.py`)
- If `--symbols` not provided, uses universe discovery
- Limits to `max_symbols` for research runs

### 4. Portfolio Selector Integration

When `portfolio.cross_sectional.enabled: true`:
- Universe provides candidate symbols (filtered by liquidity)
- Portfolio selector scores candidates and picks top-K
- Risk allocated across selected symbols

## Typical Symbol Counts

Under **conservative settings** (`min_usd_volume_24h: $50M`, `max_symbols: 30`):
- **Discovered**: ~150 USDT-margined perpetuals (full Bybit universe)
- **After volume filter**: ~25-30 symbols (top liquid instruments)
- **After portfolio selection**: 3-5 symbols (top-K by score)

**Example symbols** (typically included):
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, MATICUSDT, etc.

## Safety Features

1. **Default to Fixed Mode**: `universe_mode: "fixed"` by default (no API calls)
2. **Strict Filters**: High liquidity threshold ($50M) filters out illiquid symbols
3. **Portfolio Limits**: Even with auto universe, portfolio selector limits active trading to top-K
4. **Caching**: Reduces API calls and rate limit risk
5. **Fallbacks**: Falls back to cache → fixed symbols → BTCUSDT/ETHUSDT if API fails

## Usage Examples

### Fixed Mode (Default, Recommended for First Deployment)
```yaml
exchange:
  universe_mode: "fixed"
  # Uses trading.symbols: ["BTCUSDT", "ETHUSDT"]
```

### Auto Mode (After Validation)
```yaml
exchange:
  universe_mode: "auto"
  min_usd_volume_24h: 50000000  # $50M
  max_symbols: 20
```

### With Portfolio Selector
```yaml
exchange:
  universe_mode: "auto"
  max_symbols: 30

portfolio:
  cross_sectional:
    enabled: true
    top_k: 5  # Trade top 5 symbols from universe
```

## Testnet & Research Harness

The universe feature works seamlessly in:
- **Testnet campaigns**: Uses testnet API for discovery
- **Research harness**: Can discover symbols automatically or use explicit list
- **Backtesting**: Universe symbols can be backtested individually or as a portfolio

## Backward Compatibility

**All existing workflows continue to work**:
- Explicit `--symbol` in `train_model.py` → uses that symbol
- Explicit `--symbols` in research harness → uses those symbols
- `trading.symbols` in config → used when `universe_mode: fixed`

## Next Steps

1. **Test on testnet** with `universe_mode: auto` and conservative filters
2. **Monitor logs** to see which symbols are discovered and selected
3. **Gradually enable** portfolio selector after validating universe discovery
4. **Adjust filters** based on your risk tolerance and account size

## Documentation

- **Full Guide**: `docs/UNIVERSE_MANAGEMENT.md`
- **Config Reference**: `config/config.yaml` (comments)
- **Code**: `src/exchange/universe.py`

