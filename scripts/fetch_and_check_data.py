#!/usr/bin/env python3
"""
Fetch and validate historical data from Bybit.

Downloads OHLCV data, performs quality checks, and generates reports.

Usage:
    python scripts/fetch_and_check_data.py --symbol BTCUSDT --years 2 --timeframe 60
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.config_loader import load_config
from src.data.historical_data import HistoricalDataCollector
from src.data.quality_checks import DataQualityChecker
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
        days_old = (datetime.utcnow() - latest_date).days
        
        if days_old < 1:
            logger.info("Data is recent, skipping download")
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

