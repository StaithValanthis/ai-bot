"""Feature engineering for trading signals"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from loguru import logger


class FeatureCalculator:
    """Calculate technical indicators and features for trading signals"""
    
    def __init__(self, config: dict):
        """
        Initialize feature calculator.
        
        Args:
            config: Configuration dictionary with feature settings
        """
        self.config = config.get('features', {})
        self.lookback = self.config.get('lookback_periods', {})
        logger.info("Initialized FeatureCalculator")
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all technical indicators.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        # Ensure we have required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing required columns. Have: {df.columns.tolist()}")
            return df
        
        # RSI
        if 'rsi' in self.config.get('indicators', []):
            df['rsi'] = self._calculate_rsi(df['close'], self.lookback.get('rsi', 14))
        
        # MACD
        if 'macd' in self.config.get('indicators', []):
            macd_data = self._calculate_macd(
                df['close'],
                fast=self.lookback.get('macd_fast', 12),
                slow=self.lookback.get('macd_slow', 26),
                signal=self.lookback.get('macd_signal', 9)
            )
            df['macd'] = macd_data['macd']
            df['macd_signal'] = macd_data['signal']
            df['macd_hist'] = macd_data['histogram']
        
        # Moving Averages
        if 'ema_9' in self.config.get('indicators', []):
            df['ema_9'] = df['close'].ewm(span=self.lookback.get('ema_short', 9), adjust=False).mean()
        
        if 'ema_21' in self.config.get('indicators', []):
            df['ema_21'] = df['close'].ewm(span=self.lookback.get('ema_long', 21), adjust=False).mean()
        
        if 'ema_50' in self.config.get('indicators', []):
            df['ema_50'] = df['close'].ewm(span=self.lookback.get('ema_trend', 50), adjust=False).mean()
        
        # ATR (Average True Range)
        if 'atr' in self.config.get('indicators', []):
            df['atr'] = self._calculate_atr(
                df['high'],
                df['low'],
                df['close'],
                self.lookback.get('atr_period', 14)
            )
        
        # Bollinger Bands
        if 'bollinger_bands' in self.config.get('indicators', []):
            bb_data = self._calculate_bollinger_bands(
                df['close'],
                period=self.lookback.get('bb_period', 20),
                std=self.lookback.get('bb_std', 2)
            )
            df['bb_upper'] = bb_data['upper']
            df['bb_middle'] = bb_data['middle']
            df['bb_lower'] = bb_data['lower']
            df['bb_width'] = (bb_data['upper'] - bb_data['lower']) / bb_data['middle']
        
        # ADX (Average Directional Index) - for regime classification
        if 'adx' in self.config.get('indicators', []) or self.config.get('regime_filter', {}).get('enabled', False):
            df['adx'] = self._calculate_adx(
                df['high'],
                df['low'],
                df['close'],
                period=14
            )
        
        # Volume indicators
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # Price returns
        df['return_1h'] = df['close'].pct_change(1)
        df['return_4h'] = df['close'].pct_change(4)
        df['return_24h'] = df['close'].pct_change(24)
        
        # Volatility
        df['volatility'] = df['return_1h'].rolling(window=24).std()
        
        return df
    
    def build_meta_features(
        self, 
        df: pd.DataFrame, 
        primary_signal: dict,
        symbol: Optional[str] = None,
        symbol_encoding: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, float]:
        """
        Build feature vector for meta-model.
        
        Args:
            df: DataFrame with latest candle and indicators
            primary_signal: Dictionary with primary signal information
            symbol: Trading symbol (optional, used for symbol encoding in multi-symbol mode)
            symbol_encoding: Dict mapping symbol to one-hot encoding list (optional, used during training)
            
        Returns:
            Dictionary of feature values
        """
        if df.empty:
            return {}
        
        latest = df.iloc[-1]
        features = {}
        
        # Technical indicators
        if 'rsi' in df.columns:
            features['rsi'] = latest['rsi']
        
        if 'macd' in df.columns:
            features['macd'] = latest['macd']
            features['macd_signal'] = latest['macd_signal']
            features['macd_hist'] = latest['macd_hist']
        
        if 'ema_9' in df.columns and 'ema_21' in df.columns:
            features['ema_9'] = latest['ema_9']
            features['ema_21'] = latest['ema_21']
            features['ema_9_21_diff'] = (latest['ema_9'] - latest['ema_21']) / latest['close']
            features['ema_9_21_above'] = 1.0 if latest['ema_9'] > latest['ema_21'] else 0.0
        
        if 'ema_50' in df.columns:
            features['ema_50'] = latest['ema_50']
            features['price_above_ema50'] = 1.0 if latest['close'] > latest['ema_50'] else 0.0
        
        if 'atr' in df.columns:
            features['atr'] = latest['atr']
            features['atr_pct'] = latest['atr'] / latest['close']
        
        if 'bb_width' in df.columns:
            features['bb_width'] = latest['bb_width']
            features['bb_position'] = (latest['close'] - latest['bb_lower']) / (latest['bb_upper'] - latest['bb_lower'])
        
        # Volume features
        if 'volume_ratio' in df.columns:
            features['volume_ratio'] = latest['volume_ratio']
        
        # Return features
        if 'return_1h' in df.columns:
            features['return_1h'] = latest['return_1h']
        if 'return_4h' in df.columns:
            features['return_4h'] = latest['return_4h']
        if 'return_24h' in df.columns:
            features['return_24h'] = latest['return_24h']
        
        # Volatility
        if 'volatility' in df.columns:
            features['volatility'] = latest['volatility']
        
        # ADX (trend strength)
        if 'adx' in df.columns:
            features['adx'] = latest['adx']
        
        # Primary signal features
        features['primary_signal_strength'] = primary_signal.get('strength', 0.0)
        features['primary_signal_direction'] = 1.0 if primary_signal.get('direction') == 'LONG' else (-1.0 if primary_signal.get('direction') == 'SHORT' else 0.0)
        
        # Time features
        if 'timestamp' in df.columns:
            timestamp = pd.to_datetime(latest['timestamp'])
            features['hour'] = timestamp.hour / 24.0  # Normalize to [0, 1]
            features['day_of_week'] = timestamp.dayofweek / 7.0  # Normalize to [0, 1]
        
        # Symbol encoding (for multi-symbol training)
        # If symbol_encoding is provided (training mode), use it
        # If symbol is provided (live mode), extract from df if available
        if symbol_encoding is not None and symbol is not None:
            # Training mode: use provided encoding
            encoding = symbol_encoding.get(symbol, [])
            for i, val in enumerate(encoding):
                features[f'symbol_id_{i}'] = float(val)
        elif symbol is not None and 'symbol_id' in df.columns:
            # Live mode: extract from DataFrame if available
            # This handles the case where symbol_id was added during data preparation
            symbol_id_cols = [col for col in df.columns if col.startswith('symbol_id_')]
            for col in symbol_id_cols:
                features[col] = float(latest[col])
        
        return features
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(
        self,
        prices: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, pd.Series]:
        """Calculate MACD"""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - macd_signal
        
        return {
            'macd': macd,
            'signal': macd_signal,
            'histogram': histogram
        }
    
    def _calculate_atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """Calculate ATR"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    
    def _calculate_bollinger_bands(
        self,
        prices: pd.Series,
        period: int = 20,
        std: float = 2.0
    ) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        middle = prices.rolling(window=period).mean()
        std_dev = prices.rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }
    
    def _calculate_adx(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """Calculate Average Directional Index (ADX)"""
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        up_move = high - high.shift()
        down_move = low.shift() - low
        
        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0),
            index=high.index
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0),
            index=high.index
        )
        
        # Smooth TR and DM
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        # Calculate ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)  # Avoid division by zero
        adx = dx.rolling(window=period).mean()
        
        return adx

