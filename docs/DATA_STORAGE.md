# Data Storage Guide

## Overview

Historical candle data is stored as **Parquet files** (not a database) in the project root directory. The data is **NOT venv-specific** - it's stored in the project directory and persists across virtual environment recreations.

## Storage Location

### Default Paths

- **Primary location**: `data/raw/bybit/` (used by `fetch_and_check_data.py`)
- **Alternative location**: `data/historical/` (default in `historical_data.py`, but configurable)

### File Format

- **Format**: Parquet files (columnar, compressed, efficient)
- **Naming**: `{SYMBOL}_{TIMEFRAME}.parquet`
  - Example: `BTCUSDT_60.parquet` (BTCUSDT, 60-minute candles)
  - Example: `ETHUSDT_60.parquet` (ETHUSDT, 60-minute candles)

### Directory Structure

```
ai-bot/
├── data/
│   ├── raw/
│   │   └── bybit/
│   │       ├── BTCUSDT_60.parquet
│   │       ├── ETHUSDT_60.parquet
│   │       └── ...
│   └── historical/  # Alternative location (if used)
│       └── ...
├── venv/  # Virtual environment (data is NOT here)
└── ...
```

## Data Persistence

### ✅ Data Persists When:
- Recreating the virtual environment (`python3 -m venv venv`)
- Running `install.sh` again (now checks for existing data)
- Updating Python packages
- Restarting the server

### ❌ Data is Lost When:
- Deleting the `data/` directory
- Manually deleting `.parquet` files
- Running with `--force-redownload` flag

## Why Data Was Being Re-downloaded

### Previous Issue (Now Fixed)

The `install.sh` script was **always prompting** to fetch data, even if data already existed. This has been fixed:

1. **Before**: Script always asked "Do you want to fetch historical data?"
2. **After**: Script checks for existing `.parquet` files first
   - If data exists: Asks "Historical data files already exist. Re-download anyway?" (default: No)
   - If no data: Asks "Do you want to fetch historical data now?" (default: No)

### Smart Data Updates

The `fetch_and_check_data.py` script now intelligently handles existing data:

1. **Checks for existing data** before downloading
2. **If data exists and is recent** (< 1 day old) and has sufficient history: **Skips download**
3. **If data is old**: Only downloads missing candles (incremental update)
4. **If data is insufficient**: Downloads additional history to meet requirements
5. **Merges new data** with existing data automatically (deduplicates)

## Configuration

### Config File

The data path is configured in `config/config.yaml`:

```yaml
data:
  historical_data_path: "data/raw/bybit"  # Path for historical OHLCV data (Parquet files)
```

### Script Defaults

- `scripts/fetch_and_check_data.py`: Uses `data/raw/bybit` (can be overridden with `--data-path`)
- `src/data/historical_data.py`: Defaults to `data/historical` (but uses config if available)

**Note**: There's a path inconsistency that should be standardized. The config file uses `data/raw/bybit`, which is the recommended location.

## Data File Details

### Parquet File Contents

Each `.parquet` file contains:
- `timestamp` (datetime)
- `open`, `high`, `low`, `close` (float)
- `volume`, `turnover` (float)
- `symbol` (string)
- `timeframe` (string)

### File Size

- **1 year of hourly data**: ~500KB - 1MB per symbol
- **2 years of hourly data**: ~1-2MB per symbol
- **Compression**: Parquet uses columnar compression (very efficient)

## Best Practices

1. **Backup data**: The `data/` directory is gitignored, so back it up separately if needed
2. **Don't delete venv**: Data is NOT in venv, so you can safely recreate venv without losing data
3. **Use incremental updates**: The script automatically updates old data instead of re-downloading everything
4. **Check before downloading**: The script now checks for existing data before prompting

## Troubleshooting

### Data Not Found

If the script says "No data files found":
1. Check if files exist: `ls -la data/raw/bybit/*.parquet`
2. Check the path in `config/config.yaml`
3. Verify the symbol name matches exactly (case-sensitive)

### Data Being Re-downloaded

If data keeps getting re-downloaded:
1. Check if files exist in the expected location
2. Verify the `data_path` parameter matches between scripts
3. Use `--force-redownload` only when you actually want to re-download

### Path Mismatch

If you see warnings about "No data files found" but files exist:
- Check if files are in `data/raw/bybit/` vs `data/historical/`
- Update `config/config.yaml` to use the correct path
- Or use `--data-path` flag to specify the correct path

## Summary

- **Storage**: Parquet files in `data/raw/bybit/` (project root, not venv)
- **Format**: One file per symbol/timeframe (e.g., `BTCUSDT_60.parquet`)
- **Persistence**: Data survives venv recreation
- **Smart Updates**: Script checks for existing data and only downloads what's needed
- **install.sh**: Now checks for existing data before prompting

