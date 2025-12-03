"""Historical data collection from Bybit"""

import time
import pandas as pd
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
from loguru import logger


class HistoricalDataCollector:
    """Collect and store historical OHLCV data from Bybit"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True
    ):
        """
        Initialize historical data collector.
        
        Args:
            api_key: Bybit API key (optional for public endpoints)
            api_secret: Bybit API secret (optional for public endpoints)
            testnet: Use testnet API
        """
        self.testnet = testnet
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )
        logger.info(f"Initialized HistoricalDataCollector (testnet={testnet})")
    
    def fetch_candles(
        self,
        symbol: str,
        interval: str = "60",  # 60 = 1 hour
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200,  # Max per request
        max_retries: int = 3
    ) -> pd.DataFrame:
        """
        Fetch historical candles from Bybit.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            interval: Kline interval ("60" = 1h, "240" = 4h)
            start_time: Start datetime
            end_time: End datetime
            limit: Maximum candles per request (max 200)
            
        Returns:
            DataFrame with OHLCV data
        """
        all_candles = []
        # Paginate backwards from end_time to start_time
        # Bybit returns candles in reverse chronological order (newest first)
        current_end = end_time
        end_ts = int(end_time.timestamp() * 1000) if end_time else None
        start_ts = int(start_time.timestamp() * 1000) if start_time else None
        
        logger.info(f"Fetching candles for {symbol} from {start_time} to {end_time}")
        
        retry_count = 0
        iteration = 0
        while True:
            iteration += 1
            try:
                # Convert current_end to timestamp (milliseconds)
                current_end_ts = int(current_end.timestamp() * 1000) if current_end else None
                
                # Make API request with retry logic
                # Request from start_time to current_end to get candles going backwards
                response = None
                for attempt in range(max_retries):
                    try:
                        response = self.session.get_kline(
                            category="linear",
                            symbol=symbol,
                            interval=interval,
                            start=start_ts,  # Always start from the original start_time
                            end=current_end_ts,  # Move end backwards as we paginate
                            limit=limit
                        )
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # Exponential backoff
                            logger.warning(f"API request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            raise
                
                if response is None or response.get('retCode') != 0:
                    error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                    logger.error(f"API error: {error_msg}")
                    if retry_count < max_retries:
                        retry_count += 1
                        time.sleep(2)
                        continue
                    break
                
                retry_count = 0  # Reset on success
                candles = response.get('result', {}).get('list', [])
                
                if not candles:
                    logger.info(f"No more candles returned, stopping pagination")
                    break
                
                # Convert to DataFrame
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                
                # Convert types
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = df[col].astype(float)
                
                # Bybit returns candles in reverse chronological order (newest first)
                # Sort to chronological order for easier processing
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                # Filter out candles that are outside our desired range (safety check)
                if start_time:
                    df = df[df['timestamp'] >= start_time]
                if end_time:
                    df = df[df['timestamp'] <= end_time]
                
                if df.empty:
                    logger.info(f"Filtered out all candles, stopping pagination")
                    break
                
                all_candles.append(df)
                
                # Get the oldest timestamp in this batch (first row after sorting)
                oldest_timestamp = df['timestamp'].iloc[0]
                newest_timestamp = df['timestamp'].iloc[-1]
                
                # Log progress (info level so user can see pagination working)
                logger.info(f"Iteration {iteration}: Fetched {len(df)} candles, range: {oldest_timestamp} to {newest_timestamp} (total so far: {sum(len(c) for c in all_candles)})")
                
                # Check if we've reached or passed start_time
                if start_time and oldest_timestamp <= start_time:
                    logger.info(f"Reached start_time ({start_time}), stopping pagination")
                    break
                
                # Calculate interval delta based on interval string
                interval_hours = self._interval_to_hours(interval)
                
                # Move current_end backwards to the oldest candle we got (inclusive)
                # Bybit will return candles up to and including this timestamp
                # We'll filter duplicates when combining all_candles
                current_end = oldest_timestamp
                
                # Safety check: if we got fewer candles than requested, we've likely reached the end
                if len(candles) < limit:
                    logger.info(f"Received fewer candles than requested ({len(candles)} < {limit}), stopping pagination")
                    break
                
                # Additional safety: if we've gone past start_time, we're done
                if start_time and current_end < start_time:
                    logger.info(f"Reached start_time ({start_time}), stopping pagination")
                    break
                
                # Safety check: if oldest_timestamp didn't move backwards, we might be stuck
                # (This should be rare, but helps avoid infinite loops)
                if iteration > 1:
                    prev_oldest = all_candles[-2]['timestamp'].iloc[0]
                    if oldest_timestamp >= prev_oldest:
                        logger.warning(f"Oldest timestamp didn't move backwards (current: {oldest_timestamp}, previous: {prev_oldest}), stopping pagination")
                        break
                
                # Rate limiting (be more conservative)
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error fetching candles: {e}")
                if retry_count < max_retries:
                    retry_count += 1
                    time.sleep(2)
                    continue
                break
        
        if not all_candles:
            logger.warning(f"No candles fetched for {symbol}")
            return pd.DataFrame()
        
        if not all_candles:
            logger.warning(f"No candles fetched for {symbol}")
            return pd.DataFrame()
        
        # Combine all candles
        result_df = pd.concat(all_candles, ignore_index=True)
        result_df = result_df.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last').reset_index(drop=True)
        
        # Add symbol and timeframe columns if not present
        if 'symbol' not in result_df.columns:
            result_df['symbol'] = symbol
        if 'timeframe' not in result_df.columns:
            result_df['timeframe'] = interval
        
        logger.info(f"Fetched {len(result_df)} candles for {symbol}")
        return result_df
    
    def _interval_to_hours(self, interval: str) -> float:
        """Convert interval string to hours"""
        interval_map = {
            "1": 1/60,      # 1 minute
            "3": 3/60,      # 3 minutes
            "5": 5/60,      # 5 minutes
            "15": 15/60,    # 15 minutes
            "30": 30/60,    # 30 minutes
            "60": 1.0,      # 1 hour
            "120": 2.0,     # 2 hours
            "240": 4.0,     # 4 hours
            "360": 6.0,     # 6 hours
            "720": 12.0,    # 12 hours
            "D": 24.0,      # 1 day
            "W": 168.0,     # 1 week
            "M": 720.0      # 1 month (approximate)
        }
        return interval_map.get(interval, 1.0)
    
    def save_candles(
        self,
        df: pd.DataFrame,
        data_path: str = "data/historical",
        merge_existing: bool = True
    ) -> Path:
        """
        Save candles to parquet file, with optional merging of existing data.
        
        Args:
            df: DataFrame with candle data
            data_path: Base path for data storage
            merge_existing: If True, merge with existing data and deduplicate
            
        Returns:
            Path to saved file
        """
        if df.empty:
            logger.warning("Cannot save empty DataFrame")
            return Path()
        
        data_dir = Path(data_path)
        data_dir.mkdir(parents=True, exist_ok=True)
        
        symbol = df['symbol'].iloc[0]
        timeframe = df['timeframe'].iloc[0]
        
        # If merging, load existing data first
        if merge_existing:
            existing = self.load_candles(symbol, timeframe, data_path)
            if not existing.empty:
                # Combine and deduplicate
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.sort_values('timestamp')
                combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
                df = combined.sort_values('timestamp').reset_index(drop=True)
                logger.info(f"Merged with existing data: {len(df)} total candles")
        
        # Save as single file per symbol/timeframe (overwrite or append based on strategy)
        # For simplicity, save as one file per symbol/timeframe
        filename = f"{symbol}_{timeframe}.parquet"
        filepath = data_dir / filename
        
        df.to_parquet(filepath, index=False)
        logger.info(f"Saved {len(df)} candles to {filepath}")
        
        return filepath
    
    @staticmethod
    def calculate_history_metrics(df: pd.DataFrame, expected_interval_minutes: int = 60) -> dict:
        """
        Calculate history metrics for a DataFrame.
        
        Args:
            df: DataFrame with 'timestamp' column
            expected_interval_minutes: Expected interval between candles in minutes
            
        Returns:
            Dictionary with:
                - available_days: Actual number of days of history
                - coverage_pct: Percentage of expected candles present
                - total_candles: Total number of candles
                - date_range: (start_date, end_date)
        """
        if df.empty or 'timestamp' not in df.columns:
            return {
                'available_days': 0,
                'coverage_pct': 0.0,
                'total_candles': 0,
                'date_range': (None, None)
            }
        
        df = df.sort_values('timestamp').reset_index(drop=True)
        start_date = pd.to_datetime(df['timestamp'].min())
        end_date = pd.to_datetime(df['timestamp'].max())
        
        # Calculate actual days
        available_days = (end_date - start_date).days
        
        # Calculate expected number of candles
        expected_candles = (available_days * 24 * 60) / expected_interval_minutes
        actual_candles = len(df)
        
        # Calculate coverage percentage
        coverage_pct = (actual_candles / expected_candles) if expected_candles > 0 else 0.0
        
        return {
            'available_days': available_days,
            'coverage_pct': coverage_pct,
            'total_candles': actual_candles,
            'date_range': (start_date, end_date)
        }
    
    def load_candles(
        self,
        symbol: str,
        timeframe: str = "60",
        data_path: str = "data/historical"
    ) -> pd.DataFrame:
        """
        Load candles from parquet files.
        
        Args:
            symbol: Trading symbol
            timeframe: Kline interval
            data_path: Base path for data storage
            
        Returns:
            DataFrame with candle data
        """
        data_dir = Path(data_path)
        
        # Find all matching files
        # Match both {symbol}_{timeframe}.parquet and {symbol}_{timeframe}_*.parquet
        # to support both current save format and any legacy files with suffixes
        pattern = f"{symbol}_{timeframe}*.parquet"
        files = list(data_dir.glob(pattern))
        
        if not files:
            logger.warning(f"No data files found for {symbol} {timeframe} in {data_path}")
            return pd.DataFrame()
        
        # Load and combine all files
        dfs = []
        for file in files:
            df = pd.read_parquet(file)
            dfs.append(df)
        
        result_df = pd.concat(dfs, ignore_index=True)
        result_df = result_df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
        
        logger.info(f"Loaded {len(result_df)} candles for {symbol} {timeframe} from {len(files)} file(s)")
        return result_df
    
    def download_and_save(
        self,
        symbol: str,
        days: int = 730,
        interval: str = "60",
        data_path: str = "data/historical",
        merge_existing: bool = True
    ) -> pd.DataFrame:
        """
        Download and save historical data.
        
        Args:
            symbol: Trading symbol
            days: Number of days of history to download
            interval: Kline interval
            data_path: Base path for data storage
            merge_existing: If True, merge with existing data; if False, overwrite
            
        Returns:
            DataFrame with downloaded data
        """
        # Check for existing data first
        existing_df = self.load_candles(symbol, interval, data_path)
        
        if not existing_df.empty:
            # Calculate what date range we already have
            existing_start = existing_df['timestamp'].min()
            existing_end = existing_df['timestamp'].max()
            existing_days = (existing_end - existing_start).days
            
            logger.info(f"Found existing data for {symbol}: {len(existing_df)} candles from {existing_start.date()} to {existing_end.date()} ({existing_days} days)")
            
            # Check if we need to download more data
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)
            
            # If existing data covers the requested range, return it
            if existing_start <= start_time and existing_end >= end_time - timedelta(days=1):
                logger.info(f"Existing data already covers requested range ({days} days), skipping download")
                return existing_df
            
            # Otherwise, download missing data
            if existing_end < end_time - timedelta(days=1):
                logger.info(f"Downloading missing data from {existing_end} to {end_time}")
                new_df = self.fetch_candles(symbol, interval, existing_end, end_time)
                if not new_df.empty:
                    # Merge with existing
                    combined = pd.concat([existing_df, new_df], ignore_index=True)
                    combined = combined.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last')
                    self.save_candles(combined, data_path, merge_existing=False)
                    return combined
            
            # If we need older data
            if existing_start > start_time:
                logger.info(f"Downloading older data from {start_time} to {existing_start}")
                older_df = self.fetch_candles(symbol, interval, start_time, existing_start)
                if not older_df.empty:
                    # Merge with existing
                    combined = pd.concat([older_df, existing_df], ignore_index=True)
                    combined = combined.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last')
                    self.save_candles(combined, data_path, merge_existing=False)
                    return combined
            
            return existing_df
        
        # No existing data, download fresh
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        logger.info(f"Downloading {days} days of data for {symbol} from {start_time.date()} to {end_time.date()}")
        df = self.fetch_candles(symbol, interval, start_time, end_time)
        
        if not df.empty:
            self.save_candles(df, data_path, merge_existing=merge_existing)
        
        return df
