# Phase 25: Historical Data Ingestion & Integrity Checks

## Overview

This document describes the robust historical data ingestion pipeline for the v2.1 bot, including data fetching, quality checks, and storage.

---

## Data Pipeline Architecture

### Components

1. **`src/data/historical_data.py`** - `HistoricalDataCollector`
   - Fetches OHLCV data from Bybit API
   - Handles pagination and rate limiting
   - Saves data as Parquet files
   - Loads and merges existing data

2. **`src/data/quality_checks.py`** - `DataQualityChecker`
   - Validates data integrity
   - Detects gaps, duplicates, outliers
   - Checks price/volume validity
   - Generates quality reports

3. **`scripts/fetch_and_check_data.py`** - CLI tool
   - Downloads data for specified symbols
   - Runs quality checks
   - Generates reports

---

## Data Storage

### Directory Structure

```
data/
└── raw/
    └── bybit/
        ├── BTCUSDT_60.parquet
        ├── ETHUSDT_60.parquet
        └── ...
```

### File Format

**Parquet files** (one per symbol/timeframe):
- Filename: `{symbol}_{timeframe}.parquet`
- Columns:
  - `timestamp` (datetime)
  - `open`, `high`, `low`, `close` (float)
  - `volume`, `turnover` (float)
  - `symbol` (string)
  - `timeframe` (string)

### Data Merging

- When saving, existing data is automatically merged
- Duplicates are removed (by timestamp)
- Data is sorted chronologically

---

## Fetching Data

### Using the CLI Script

**Single Symbol:**
```bash
python scripts/fetch_and_check_data.py \
  --symbol BTCUSDT \
  --years 2 \
  --timeframe 60
```

**Multiple Symbols:**
```bash
python scripts/fetch_and_check_data.py \
  --symbols BTCUSDT ETHUSDT BNBUSDT \
  --years 2 \
  --timeframe 60
```

**Force Re-download:**
```bash
python scripts/fetch_and_check_data.py \
  --symbol BTCUSDT \
  --years 2 \
  --force-redownload
```

### Programmatic Usage

```python
from src.data.historical_data import HistoricalDataCollector
from datetime import datetime, timedelta

collector = HistoricalDataCollector(testnet=True)

# Download data
end_time = datetime.utcnow()
start_time = end_time - timedelta(days=730)  # 2 years

df = collector.fetch_candles(
    symbol="BTCUSDT",
    interval="60",
    start_time=start_time,
    end_time=end_time
)

# Save data
collector.save_candles(df, data_path="data/raw/bybit")
```

---

## Quality Checks

### Checks Performed

1. **Required Columns**
   - Verifies: `timestamp`, `open`, `high`, `low`, `close`, `volume`

2. **Timestamp Validation**
   - Converts to datetime
   - Checks for duplicates
   - Detects gaps in time series

3. **Price Validity**
   - Non-negative prices
   - No NaN values
   - OHLC relationships (high >= open/low/close, low <= open/high/close)

4. **Volume Validity**
   - Non-negative volumes
   - No NaN values

5. **Outlier Detection**
   - Extreme price changes (IQR method)
   - Zero volume periods

6. **Gap Detection**
   - Missing candles in time series
   - Reports total missing time

### Quality Report

Reports are saved to: `logs/data_quality_{symbol}_{timeframe}.md`

**Example Report:**
```markdown
# Data Quality Report: BTCUSDT (60)

## Summary
- Status: ✅ PASSED
- Issues: 0
- Warnings: 2

## Data Range
- Start: 2023-01-01 00:00:00
- End: 2025-01-01 00:00:00
- Duration: 730.0 days
- Candle Count: 17520

## Warnings (Review)
- ⚠️ Found 3 gaps (total missing time: 12.0 hours)
- ⚠️ Found 5 extreme price changes (> 15.00%)
```

---

## Data Loading

### In Research Harness

The research harness automatically:
1. Loads existing data from `data/raw/bybit/`
2. Downloads missing data if needed
3. Runs quality checks (if enabled)
4. Filters to requested time range

### In Training Scripts

Training scripts use the same data pipeline:
```python
from src.data.historical_data import HistoricalDataCollector

collector = HistoricalDataCollector()
df = collector.load_candles(
    symbol="BTCUSDT",
    timeframe="60",
    data_path="data/raw/bybit"
)
```

---

## Rate Limiting & Error Handling

### Rate Limiting
- 0.2 second delay between API requests
- Respects Bybit API rate limits
- Handles rate limit errors gracefully

### Error Handling
- Retry logic (3 attempts with exponential backoff)
- Logs errors clearly
- Continues on non-critical errors
- Fails fast on critical errors

### Pagination
- Automatically handles pagination
- Fetches data in chunks (200 candles per request)
- Continues until all data is fetched

---

## Known Limitations

### API Limitations
1. **Historical Data Availability**
   - Bybit provides limited historical data (typically 1-2 years)
   - Older data may not be available
   - Solution: Use external data sources for very old data (if needed)

2. **Rate Limits**
   - Bybit has rate limits on API requests
   - Large downloads may take time
   - Solution: Rate limiting built into downloader

3. **Data Gaps**
   - Exchange downtime can cause gaps
   - Some periods may have missing data
   - Solution: Quality checks detect and report gaps

### Data Quality
1. **Missing Bars**
   - Some periods may have no trading activity
   - Gaps are detected but not automatically filled
   - Solution: Gaps are reported, operator can decide how to handle

2. **Outliers**
   - Extreme price movements may be legitimate (flash crashes)
   - Outliers are flagged but not removed
   - Solution: Review outliers manually

3. **Funding Rates**
   - Historical funding rates not included in OHLCV
   - Uses default/approximate rates in backtesting
   - Solution: Acceptable for most use cases

---

## Configuration

### Config File Settings

```yaml
data:
  historical_data_path: "data/raw/bybit"  # Storage path
  data_quality_checks_enabled: true  # Enable quality checks
```

### Environment Variables

```bash
BYBIT_API_KEY=your_key  # Optional (public endpoints work without)
BYBIT_API_SECRET=your_secret  # Optional
```

---

## Usage Examples

### Example 1: Initial Data Fetch

```bash
# Fetch 2 years of BTCUSDT data
python scripts/fetch_and_check_data.py \
  --symbol BTCUSDT \
  --years 2 \
  --timeframe 60
```

### Example 2: Update Existing Data

```bash
# Updates existing data with latest candles
python scripts/fetch_and_check_data.py \
  --symbol BTCUSDT \
  --years 2
```

### Example 3: Multiple Symbols

```bash
# Fetch data for multiple symbols
python scripts/fetch_and_check_data.py \
  --symbols BTCUSDT ETHUSDT BNBUSDT SOLUSDT \
  --years 2 \
  --timeframe 60
```

### Example 4: Force Re-download

```bash
# Re-download all data (useful if data corruption suspected)
python scripts/fetch_and_check_data.py \
  --symbol BTCUSDT \
  --years 2 \
  --force-redownload
```

---

## Troubleshooting

### Issue: No Data Downloaded

**Possible Causes:**
- API key issues (though public endpoints should work)
- Network connectivity
- Symbol not available on Bybit

**Solutions:**
1. Check network connectivity
2. Verify symbol name (e.g., "BTCUSDT" not "BTC/USDT")
3. Check Bybit API status
4. Review logs: `logs/fetch_data_*.log`

### Issue: Data Quality Failures

**Possible Causes:**
- API returned invalid data
- Data corruption during save/load
- Exchange issues

**Solutions:**
1. Review quality report: `logs/data_quality_{symbol}_{timeframe}.md`
2. Re-download data: `--force-redownload`
3. Check for known exchange issues
4. Manually inspect data if needed

### Issue: Gaps in Data

**Possible Causes:**
- Exchange downtime
- Low liquidity periods
- API limitations

**Solutions:**
1. Review gap report in quality check
2. Decide if gaps are acceptable
3. Consider filling gaps (interpolation) if needed
4. Adjust backtest period to avoid large gaps

---

## Best Practices

1. **Regular Updates**
   - Update data weekly or monthly
   - Keep data fresh for training

2. **Quality Checks**
   - Always run quality checks after download
   - Review warnings and issues
   - Fix critical issues before using data

3. **Data Backup**
   - Backup data files regularly
   - Keep multiple versions if needed

4. **Version Control**
   - Don't commit large data files to git
   - Use `.gitignore` for data directories
   - Document data sources and versions

---

## Integration with Research Harness

The research harness automatically uses this pipeline:

1. **On First Run:**
   - Checks for existing data
   - Downloads if missing
   - Runs quality checks

2. **On Subsequent Runs:**
   - Loads existing data
   - Updates with latest candles
   - Re-runs quality checks

3. **Quality Check Results:**
   - Logged to research logs
   - Warnings don't stop execution
   - Critical issues cause failure

---

## Summary

**Status:** ✅ **IMPLEMENTED**

The data pipeline provides:
- ✅ Robust data fetching from Bybit
- ✅ Quality checks and validation
- ✅ Automatic merging and deduplication
- ✅ CLI tool for easy data management
- ✅ Integration with research harness

**Next Steps:**
1. Fetch data for target symbols (BTCUSDT, ETHUSDT)
2. Run quality checks
3. Use data in research harness
4. Monitor data quality over time

---

**Date:** December 2025  
**Version:** 2.1+  
**Status:** Production Ready

