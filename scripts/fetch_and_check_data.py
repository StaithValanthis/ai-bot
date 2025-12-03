#!/usr/bin/env python3
"""
Fetch and validate historical data from Bybit.

Downloads OHLCV data, performs quality checks, and generates reports.

Usage:
    python scripts/fetch_and_check_data.py --symbol BTCUSDT --years 2 --timeframe 60
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add src to path - ensure absolute path regardless of CWD
_script_file = os.path.abspath(__file__)
_script_dir = os.path.dirname(_script_file)
_project_root = os.path.dirname(_script_dir)  # scripts/ -> project root

# Verify src module exists before adding to path
# Use absolute paths to avoid any relative path issues
_src_path = os.path.abspath(os.path.join(_project_root, "src"))
if not os.path.isdir(_src_path):
    # Fallback: try current working directory
    _cwd = os.getcwd()
    _cwd_src = os.path.abspath(os.path.join(_cwd, "src"))
    if os.path.isdir(_cwd_src):
        _project_root = os.path.abspath(_cwd)
        _src_path = _cwd_src
    else:
        print(f"ERROR: Could not find src directory.", file=sys.stderr)
        print(f"  Script dir: {_script_dir}", file=sys.stderr)
        print(f"  Project root: {_project_root}", file=sys.stderr)
        print(f"  Expected src at: {os.path.abspath(os.path.join(_project_root, 'src'))}", file=sys.stderr)
        print(f"  Current working directory: {_cwd}", file=sys.stderr)
        print(f"  Tried CWD src at: {_cwd_src}", file=sys.stderr)
        sys.exit(1)

# Ensure project_root is absolute
_project_root = os.path.abspath(_project_root)

# Verify critical subdirectories exist (use absolute path)
_src_data_path = os.path.abspath(os.path.join(_src_path, "data"))
if not os.path.isdir(_src_data_path):
    print(f"ERROR: src/data directory does not exist!", file=sys.stderr)
    print(f"  Expected at: {_src_data_path}", file=sys.stderr)
    print(f"  Project root: {_project_root}", file=sys.stderr)
    print(f"  src path: {_src_path}", file=sys.stderr)
    print(f"  src path is absolute: {os.path.isabs(_src_path)}", file=sys.stderr)
    print(f"  src path exists: {os.path.isdir(_src_path)}", file=sys.stderr)
    if os.path.isdir(_src_path):
        try:
            contents = os.listdir(_src_path)
            print(f"  Contents of src/: {contents}", file=sys.stderr)
            # Check if 'data' is in the list but not a directory
            if 'data' in contents:
                data_item_path = os.path.join(_src_path, 'data')
                print(f"  'data' found in src/, isdir: {os.path.isdir(data_item_path)}, isfile: {os.path.isfile(data_item_path)}", file=sys.stderr)
        except Exception as e:
            print(f"  Could not list src/ contents: {e}", file=sys.stderr)
    sys.exit(1)

# Verify __init__.py files exist (Python packages)
_src_init = os.path.join(_src_path, "__init__.py")
_src_data_init = os.path.join(_src_data_path, "__init__.py")
if not os.path.isfile(_src_init):
    print(f"WARNING: src/__init__.py not found at {_src_init}", file=sys.stderr)
if not os.path.isfile(_src_data_init):
    print(f"WARNING: src/data/__init__.py not found at {_src_data_init}", file=sys.stderr)

# CRITICAL: Remove script directory from sys.path if present
# Python automatically adds the script's directory to sys.path[0], which causes
# issues when the script is in a subdirectory (like scripts/)
# We need to check both the exact path and normalize paths for comparison
_script_dir_normalized = os.path.normpath(_script_dir)
_project_root_normalized = os.path.normpath(_project_root)

# Remove script directory from sys.path (check all entries)
sys.path = [p for p in sys.path if os.path.normpath(p) != _script_dir_normalized]

# Ensure project root is at sys.path[0] (highest priority)
# Remove it first if it exists elsewhere
sys.path = [p for p in sys.path if os.path.normpath(p) != _project_root_normalized]
sys.path.insert(0, _project_root)

# Clear any cached src modules
import importlib
modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('src')]
for m in modules_to_remove:
    del sys.modules[m]

# Verify path setup before importing
if os.getenv('DEBUG_IMPORTS'):
    print(f"DEBUG: Path setup complete", file=sys.stderr)
    print(f"  Script dir: {_script_dir}", file=sys.stderr)
    print(f"  Project root: {_project_root}", file=sys.stderr)
    print(f"  sys.path[0:3]: {sys.path[:3]}", file=sys.stderr)
    print(f"  src path exists: {os.path.isdir(_src_path)}", file=sys.stderr)

# Now import
try:
    # Test import of src package first
    import src
    if not hasattr(src, '__path__'):
        raise ImportError("src is not a package")
    
    # Now import the modules we need
    from src.config.config_loader import load_config
    from src.data.historical_data import HistoricalDataCollector
    from src.data.quality_checks import DataQualityChecker
except ImportError as e:
    print(f"ERROR: Cannot import src modules. Path setup may have failed.", file=sys.stderr)
    print(f"  Script dir: {_script_dir}", file=sys.stderr)
    print(f"  Project root: {_project_root}", file=sys.stderr)
    print(f"  CWD: {os.getcwd()}", file=sys.stderr)
    print(f"  sys.path[0:3]: {sys.path[:3]}", file=sys.stderr)
    print(f"  _src_path: {_src_path}", file=sys.stderr)
    print(f"  src path exists: {os.path.isdir(_src_path)}", file=sys.stderr)
    if os.path.isdir(_src_path):
        try:
            src_contents = os.listdir(_src_path)
            print(f"  Contents of src/: {src_contents}", file=sys.stderr)
        except Exception as list_err:
            print(f"  Could not list src/ contents: {list_err}", file=sys.stderr)
    data_path = os.path.join(_src_path, 'data')
    print(f"  Expected src/data path: {data_path}", file=sys.stderr)
    print(f"  src/data exists: {os.path.isdir(data_path)}", file=sys.stderr)
    if os.path.isdir(data_path):
        try:
            data_contents = os.listdir(data_path)
            print(f"  Contents of src/data/: {data_contents}", file=sys.stderr)
        except Exception as list_err:
            print(f"  Could not list src/data/ contents: {list_err}", file=sys.stderr)
    print(f"  Error: {e}", file=sys.stderr)
    sys.exit(1)

import pandas as pd


def fetch_and_check(
    symbol: str,
    years: int = 2,
    timeframe: str = "60",
    data_path: str = "data/raw/bybit",
    force_redownload: bool = False,
    config_path: str = "config/config.yaml"
):
    """
    Fetch and check historical data.
    
    Args:
        symbol: Trading symbol
        years: Years of history to fetch
        timeframe: Kline interval
        data_path: Path to store data
        force_redownload: If True, re-download even if data exists
        config_path: Path to config file
    """
    logger.info("=" * 60)
    logger.info(f"Fetching and Checking Data: {symbol}")
    logger.info(f"Years: {years}, Timeframe: {timeframe}")
    logger.info("=" * 60)
    
    # Load config
    config = load_config(config_path)
    
    # Initialize data collector
    data_collector = HistoricalDataCollector(
        api_key=config['exchange'].get('api_key'),
        api_secret=config['exchange'].get('api_secret'),
        testnet=config['exchange'].get('testnet', True)  # Use testnet for data fetching (public endpoint)
    )
    
    # Check if data already exists
    existing_data = data_collector.load_candles(
        symbol=symbol,
        timeframe=timeframe,
        data_path=data_path
    )
    
    if not existing_data.empty and not force_redownload:
        logger.info(f"Found existing data: {len(existing_data)} candles")
        logger.info(f"Date range: {existing_data['timestamp'].min()} to {existing_data['timestamp'].max()}")
        
        # Check if we need to update
        latest_date = existing_data['timestamp'].max()
        earliest_date = existing_data['timestamp'].min()
        days_old = (datetime.utcnow() - latest_date).days
        days_of_history = (latest_date - earliest_date).days
        required_days = years * 365
        
        if days_old < 1 and days_of_history >= required_days:
            logger.info(f"Data is recent and has sufficient history ({days_of_history} days >= {required_days} days), skipping download")
            df = existing_data
        elif days_of_history < required_days:
            # Need to fetch more history
            logger.info(f"Existing data has {days_of_history} days, but need {required_days} days. Fetching additional history...")
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=required_days)
            
            new_data = data_collector.fetch_candles(
                symbol=symbol,
                interval=timeframe,
                start_time=start_time,
                end_time=end_time
            )
            
            if not new_data.empty:
                # Merge with existing
                df = pd.concat([existing_data, new_data], ignore_index=True)
                df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last')
                df = df.reset_index(drop=True)
                logger.info(f"Updated data: {len(df)} total candles")
            else:
                df = existing_data
        else:
            logger.info(f"Data is {days_old} days old, updating...")
            # Download only missing data
            end_time = datetime.utcnow()
            start_time = latest_date + timedelta(hours=1)
            new_data = data_collector.fetch_candles(
                symbol=symbol,
                interval=timeframe,
                start_time=start_time,
                end_time=end_time
            )
            
            if not new_data.empty:
                # Merge with existing
                df = pd.concat([existing_data, new_data], ignore_index=True)
                df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last')
                df = df.reset_index(drop=True)
                logger.info(f"Updated data: {len(df)} total candles")
            else:
                df = existing_data
    else:
        # Download fresh data
        if force_redownload:
            logger.info("Force re-download enabled")
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=years * 365)
        
        logger.info(f"Downloading data from {start_time} to {end_time}")
        df = data_collector.fetch_candles(
            symbol=symbol,
            interval=timeframe,
            start_time=start_time,
            end_time=end_time
        )
        
        if df.empty:
            logger.error(f"Failed to download data for {symbol}")
            return False
    
    # Add symbol and timeframe if not present
    if 'symbol' not in df.columns:
        df['symbol'] = symbol
    if 'timeframe' not in df.columns:
        df['timeframe'] = timeframe
    
    # Save data
    saved_path = data_collector.save_candles(df, data_path=data_path, merge_existing=True)
    logger.info(f"Data saved to {saved_path}")
    
    # Run quality checks
    logger.info("Running quality checks...")
    quality_checker = DataQualityChecker(expected_interval_minutes=int(timeframe) if timeframe.isdigit() else 60)
    results = quality_checker.check_dataframe(df, symbol, timeframe)
    
    # Generate report
    report_path = Path("logs") / f"data_quality_{symbol}_{timeframe}.md"
    report_text = quality_checker.generate_report(results, symbol, timeframe, report_path)
    
    # Print summary
    logger.info("=" * 60)
    logger.info("Quality Check Summary")
    logger.info("=" * 60)
    logger.info(f"Status: {'✅ PASSED' if results['passed'] else '❌ FAILED'}")
    logger.info(f"Issues: {results['issue_count']}")
    logger.info(f"Warnings: {results['warning_count']}")
    
    if results['date_range']:
        dr = results['date_range']
        logger.info(f"Date Range: {dr.get('start')} to {dr.get('end')}")
        logger.info(f"Duration: {dr.get('duration_days', 0):.1f} days")
        logger.info(f"Candle Count: {dr.get('candle_count', 0)}")
    
    if results['issues']:
        logger.warning("Issues found:")
        for issue in results['issues']:
            logger.warning(f"  - {issue}")
    
    if results['warnings']:
        logger.info("Warnings:")
        for warning in results['warnings']:
            logger.info(f"  - {warning}")
    
    logger.info(f"Full report: {report_path}")
    
    return results['passed']


def main():
    parser = argparse.ArgumentParser(description='Fetch and check historical data')
    parser.add_argument('--symbol', type=str, required=True, help='Trading symbol (e.g., BTCUSDT)')
    parser.add_argument('--years', type=int, default=2, help='Years of history to fetch')
    parser.add_argument('--timeframe', type=str, default='60', help='Timeframe (60=1h, 240=4h)')
    parser.add_argument('--data-path', type=str, default='data/raw/bybit', help='Data storage path')
    parser.add_argument('--force-redownload', action='store_true', help='Force re-download even if data exists')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file')
    parser.add_argument('--symbols', nargs='+', help='Multiple symbols (alternative to --symbol)')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.add("logs/fetch_data_{time}.log", rotation="1 day", level="INFO")
    
    symbols = args.symbols if args.symbols else [args.symbol]
    
    all_passed = True
    for symbol in symbols:
        passed = fetch_and_check(
            symbol=symbol,
            years=args.years,
            timeframe=args.timeframe,
            data_path=args.data_path,
            force_redownload=args.force_redownload,
            config_path=args.config
        )
        if not passed:
            all_passed = False
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    import pandas as pd
    sys.exit(main())

