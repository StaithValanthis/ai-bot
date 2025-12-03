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
        current_start = start_time
        
        logger.info(f"Fetching candles for {symbol} from {start_time} to {end_time}")
        
        retry_count = 0
        while True:
            try:
                # Convert datetime to timestamp (milliseconds)
                start_ts = int(current_start.timestamp() * 1000) if current_start else None
                end_ts = int(end_time.timestamp() * 1000) if end_time else None
                
                # Make API request with retry logic
                response = None
                for attempt in range(max_retries):
                    try:
                        response = self.session.get_kline(
                            category="linear",
                            symbol=symbol,
                            interval=interval,
                            start=start_ts,
                            end=end_ts,
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
                    break
                
                # Convert to DataFrame
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                
                # Convert types
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = df[col].astype(float)
                
                all_candles.append(df)
                
                # Update start time for next iteration
                last_timestamp = df['timestamp'].iloc[-1]
                if current_start and last_timestamp <= current_start:
                    break
                
                # Calculate interval delta based on interval string
                interval_hours = self._interval_to_hours(interval)
                current_start = last_timestamp + timedelta(hours=interval_hours)
                
                # Check if we've reached end_time
                if end_time and current_start >= end_time:
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
        pattern = f"{symbol}_{timeframe}_*.parquet"
        files = list(data_dir.glob(pattern))
        
        if not files:
            logger.warning(f"No data files found for {symbol} {timeframe}")
            return pd.DataFrame()
        
        # Load and combine all files
        dfs = []
        for file in files:
            df = pd.read_parquet(file)
            dfs.append(df)
        
        result_df = pd.concat(dfs, ignore_index=True)
        result_df = result_df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
        
        logger.info(f"Loaded {len(result_df)} candles for {symbol} {timeframe}")
        return result_df
    
    def download_and_save(
        self,
        symbol: str,
        days: int = 730,
        interval: str = "60",
        data_path: str = "data/historical"
    ) -> pd.DataFrame:
        """
        Download and save historical data.
        
        Args:
            symbol: Trading symbol
            days: Number of days of history to download
            interval: Kline interval
            data_path: Base path for data storage
            
        Returns:
            DataFrame with downloaded data
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        df = self.fetch_candles(symbol, interval, start_time, end_time)
        
        if not df.empty:
            self.save_candles(df, data_path)
        
        return df

