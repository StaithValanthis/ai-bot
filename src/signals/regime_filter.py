"""Market regime classification and filtering"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from loguru import logger


class RegimeFilter:
    """
    Classify market regimes and gate trend-following entries.
    
    Regimes:
    - TRENDING_UP: Clear uptrend
    - TRENDING_DOWN: Clear downtrend
    - RANGING: Sideways movement
    - HIGH_VOLATILITY: Extreme volatility
    """
    
    def __init__(self, config: dict):
        """
        Initialize regime filter.
        
        Args:
            config: Configuration dictionary with regime_filter settings
        """
        regime_config = config.get('regime_filter', {})
        
        self.enabled = regime_config.get('enabled', True)
        self.adx_threshold = regime_config.get('adx_threshold', 25)
        self.volatility_threshold = regime_config.get('volatility_threshold', 2.0)  # 2x average ATR
        self.allow_ranging = regime_config.get('allow_ranging', False)
        self.high_vol_multiplier = regime_config.get('high_vol_multiplier', 0.5)
        
        logger.info(f"Initialized RegimeFilter (enabled={self.enabled})")
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average Directional Index (ADX).
        
        Args:
            df: DataFrame with high, low, close columns
            period: ADX period
            
        Returns:
            Series with ADX values
        """
        if len(df) < period * 2:
            return pd.Series(index=df.index, dtype=float)
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate Directional Movement
        up_move = high - high.shift()
        down_move = low.shift() - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        plus_dm = pd.Series(plus_dm, index=df.index)
        minus_dm = pd.Series(minus_dm, index=df.index)
        
        # Smooth TR and DM
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        # Calculate ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    def classify_regime(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Classify current market regime.
        
        Args:
            df: DataFrame with OHLCV and indicators (should have ema_50, atr, volatility)
            
        Returns:
            Dictionary with regime, confidence, and features
        """
        if df.empty or len(df) < 50:
            return {
                'regime': 'UNKNOWN',
                'confidence': 0.0,
                'allows_trend_following': True,
                'size_multiplier': 1.0
            }
        
        latest = df.iloc[-1]
        
        # Calculate ADX if not present
        if 'adx' not in df.columns:
            adx = self.calculate_adx(df)
            latest_adx = adx.iloc[-1] if len(adx) > 0 else 0
        else:
            latest_adx = latest.get('adx', 0)
        
        # Get volatility (ATR or volatility column)
        if 'atr' in df.columns:
            current_atr = latest['atr']
            avg_atr = df['atr'].rolling(window=20).mean().iloc[-1] if len(df) >= 20 else current_atr
            volatility_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
        elif 'volatility' in df.columns:
            current_vol = latest['volatility']
            avg_vol = df['volatility'].rolling(window=20).mean().iloc[-1] if len(df) >= 20 else current_vol
            volatility_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        else:
            volatility_ratio = 1.0
        
        # Get trend direction
        if 'ema_50' in df.columns and 'close' in df.columns:
            price_above_ema = latest['close'] > latest['ema_50']
            # Check momentum
            if len(df) >= 10:
                price_change = (latest['close'] - df.iloc[-10]['close']) / df.iloc[-10]['close']
                positive_momentum = price_change > 0.02  # 2% over 10 periods
                negative_momentum = price_change < -0.02
            else:
                positive_momentum = price_above_ema
                negative_momentum = not price_above_ema
        else:
            price_above_ema = True
            positive_momentum = True
            negative_momentum = False
        
        # Classify regime
        if volatility_ratio > self.volatility_threshold:
            regime = 'HIGH_VOLATILITY'
            confidence = min(volatility_ratio / self.volatility_threshold, 1.0)
            allows_trend_following = True  # Allow but with reduced size
            size_multiplier = self.high_vol_multiplier
        
        elif latest_adx > self.adx_threshold:
            if positive_momentum and price_above_ema:
                regime = 'TRENDING_UP'
                confidence = min(latest_adx / 50, 1.0)  # Normalize to [0, 1]
                allows_trend_following = True
                size_multiplier = 1.0
            elif negative_momentum and not price_above_ema:
                regime = 'TRENDING_DOWN'
                confidence = min(latest_adx / 50, 1.0)
                allows_trend_following = True
                size_multiplier = 1.0
            else:
                regime = 'RANGING'
                confidence = 0.5
                allows_trend_following = self.allow_ranging
                size_multiplier = 0.5 if self.allow_ranging else 0.0
        
        else:
            regime = 'RANGING'
            confidence = 1.0 - (latest_adx / self.adx_threshold)  # Low ADX = high confidence in ranging
            allows_trend_following = self.allow_ranging
            size_multiplier = 0.5 if self.allow_ranging else 0.0
        
        return {
            'regime': regime,
            'confidence': float(confidence),
            'allows_trend_following': allows_trend_following,
            'size_multiplier': size_multiplier,
            'adx': float(latest_adx),
            'volatility_ratio': float(volatility_ratio)
        }
    
    def should_allow_trade(
        self,
        df: pd.DataFrame,
        signal_direction: str
    ) -> Tuple[bool, str, float]:
        """
        Check if trade should be allowed based on regime.
        
        Args:
            df: DataFrame with market data
            signal_direction: 'LONG', 'SHORT', or 'NEUTRAL'
            
        Returns:
            Tuple of (is_allowed, reason, size_multiplier)
        """
        if not self.enabled:
            return True, "OK", 1.0
        
        if signal_direction == 'NEUTRAL':
            return False, "No signal", 0.0
        
        regime_info = self.classify_regime(df)
        
        if not regime_info['allows_trend_following']:
            return False, f"Regime {regime_info['regime']} does not allow trend-following", 0.0
        
        # Check if signal direction matches regime
        if signal_direction == 'LONG' and regime_info['regime'] == 'TRENDING_DOWN':
            return False, "LONG signal in downtrend regime", 0.0
        
        if signal_direction == 'SHORT' and regime_info['regime'] == 'TRENDING_UP':
            return False, "SHORT signal in uptrend regime", 0.0
        
        return True, f"Regime {regime_info['regime']} allows trading", regime_info['size_multiplier']

