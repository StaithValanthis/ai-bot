"""Primary trend-following signal generation"""

import pandas as pd
from typing import Dict, Optional
from loguru import logger


class PrimarySignalGenerator:
    """Generate primary trend-following signals"""
    
    def __init__(self, config: dict):
        """
        Initialize primary signal generator.
        
        Args:
            config: Configuration dictionary with primary signal settings
        """
        self.config = config.get('primary_signal', {})
        logger.info("Initialized PrimarySignalGenerator")
    
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Generate primary trading signal from indicators.
        
        Args:
            df: DataFrame with calculated indicators
            
        Returns:
            Dictionary with signal information:
            {
                'direction': 'LONG', 'SHORT', or 'NEUTRAL',
                'strength': float (0.0 to 1.0),
                'components': dict of individual signal components
            }
        """
        if df.empty or len(df) < 50:  # Need enough history for indicators
            return {
                'direction': 'NEUTRAL',
                'strength': 0.0,
                'components': {}
            }
        
        latest = df.iloc[-1]
        signals = []
        components = {}
        
        # EMA Crossover
        if self.config.get('ema_crossover', True):
            if 'ema_9' in df.columns and 'ema_21' in df.columns:
                ema_signal = self._ema_crossover_signal(latest, df)
                if ema_signal['direction'] != 'NEUTRAL':
                    signals.append(ema_signal)
                    components['ema'] = ema_signal
        
        # RSI Extremes
        if self.config.get('rsi_extremes', True):
            if 'rsi' in df.columns:
                rsi_signal = self._rsi_extreme_signal(
                    latest,
                    oversold=self.config.get('rsi_oversold', 30),
                    overbought=self.config.get('rsi_overbought', 70)
                )
                if rsi_signal['direction'] != 'NEUTRAL':
                    signals.append(rsi_signal)
                    components['rsi'] = rsi_signal
        
        # MACD Crossover
        if self.config.get('macd_crossover', True):
            if 'macd' in df.columns and 'macd_signal' in df.columns:
                macd_signal = self._macd_crossover_signal(latest, df)
                if macd_signal['direction'] != 'NEUTRAL':
                    signals.append(macd_signal)
                    components['macd'] = macd_signal
        
        # Combine signals
        if not signals:
            return {
                'direction': 'NEUTRAL',
                'strength': 0.0,
                'components': {}
            }
        
        combination_method = self.config.get('signal_combination', 'weighted')
        
        if combination_method == 'voting':
            return self._combine_voting(signals, components)
        else:  # weighted
            return self._combine_weighted(signals, components)
    
    def _ema_crossover_signal(self, latest: pd.Series, df: pd.DataFrame) -> Dict:
        """Generate signal from EMA crossover"""
        if len(df) < 2:
            return {'direction': 'NEUTRAL', 'strength': 0.0}
        
        prev = df.iloc[-2]
        current_above = latest['ema_9'] > latest['ema_21']
        prev_above = prev['ema_9'] > prev['ema_21']
        
        # Bullish crossover
        if current_above and not prev_above:
            strength = min(abs(latest['ema_9'] - latest['ema_21']) / latest['close'], 0.05) / 0.05
            return {'direction': 'LONG', 'strength': min(strength, 1.0)}
        
        # Bearish crossover
        elif not current_above and prev_above:
            strength = min(abs(latest['ema_9'] - latest['ema_21']) / latest['close'], 0.05) / 0.05
            return {'direction': 'SHORT', 'strength': min(strength, 1.0)}
        
        # Trend continuation
        elif current_above:
            strength = min(abs(latest['ema_9'] - latest['ema_21']) / latest['close'], 0.05) / 0.05
            return {'direction': 'LONG', 'strength': min(strength * 0.7, 1.0)}  # Lower strength for continuation
        
        elif not current_above:
            strength = min(abs(latest['ema_9'] - latest['ema_21']) / latest['close'], 0.05) / 0.05
            return {'direction': 'SHORT', 'strength': min(strength * 0.7, 1.0)}
        
        return {'direction': 'NEUTRAL', 'strength': 0.0}
    
    def _rsi_extreme_signal(
        self,
        latest: pd.Series,
        oversold: float = 30,
        overbought: float = 70
    ) -> Dict:
        """Generate signal from RSI extremes"""
        rsi = latest['rsi']
        
        if rsi < oversold:
            strength = (oversold - rsi) / oversold  # Normalize to [0, 1]
            return {'direction': 'LONG', 'strength': min(strength, 1.0)}
        
        elif rsi > overbought:
            strength = (rsi - overbought) / (100 - overbought)  # Normalize to [0, 1]
            return {'direction': 'SHORT', 'strength': min(strength, 1.0)}
        
        return {'direction': 'NEUTRAL', 'strength': 0.0}
    
    def _macd_crossover_signal(self, latest: pd.Series, df: pd.DataFrame) -> Dict:
        """Generate signal from MACD crossover"""
        if len(df) < 2:
            return {'direction': 'NEUTRAL', 'strength': 0.0}
        
        prev = df.iloc[-2]
        current_above = latest['macd'] > latest['macd_signal']
        prev_above = prev['macd'] > prev['macd_signal']
        
        # Bullish crossover
        if current_above and not prev_above:
            strength = min(abs(latest['macd_hist']) / (latest['close'] * 0.01), 1.0)  # Normalize
            return {'direction': 'LONG', 'strength': min(strength, 1.0)}
        
        # Bearish crossover
        elif not current_above and prev_above:
            strength = min(abs(latest['macd_hist']) / (latest['close'] * 0.01), 1.0)
            return {'direction': 'SHORT', 'strength': min(strength, 1.0)}
        
        # Trend continuation
        elif current_above and latest['macd_hist'] > 0:
            strength = min(abs(latest['macd_hist']) / (latest['close'] * 0.01), 1.0) * 0.7
            return {'direction': 'LONG', 'strength': min(strength, 1.0)}
        
        elif not current_above and latest['macd_hist'] < 0:
            strength = min(abs(latest['macd_hist']) / (latest['close'] * 0.01), 1.0) * 0.7
            return {'direction': 'SHORT', 'strength': min(strength, 1.0)}
        
        return {'direction': 'NEUTRAL', 'strength': 0.0}
    
    def _combine_voting(self, signals: list, components: dict) -> Dict:
        """Combine signals using voting"""
        long_votes = sum(1 for s in signals if s['direction'] == 'LONG')
        short_votes = sum(1 for s in signals if s['direction'] == 'SHORT')
        
        if long_votes > short_votes:
            avg_strength = sum(s['strength'] for s in signals if s['direction'] == 'LONG') / long_votes
            return {
                'direction': 'LONG',
                'strength': min(avg_strength, 1.0),
                'components': components
            }
        elif short_votes > long_votes:
            avg_strength = sum(s['strength'] for s in signals if s['direction'] == 'SHORT') / short_votes
            return {
                'direction': 'SHORT',
                'strength': min(avg_strength, 1.0),
                'components': components
            }
        else:
            return {
                'direction': 'NEUTRAL',
                'strength': 0.0,
                'components': components
            }
    
    def _combine_weighted(self, signals: list, components: dict) -> Dict:
        """Combine signals using weighted average"""
        weights = {'LONG': 0.0, 'SHORT': 0.0}
        
        for signal in signals:
            direction = signal['direction']
            strength = signal['strength']
            weights[direction] += strength
        
        if weights['LONG'] > weights['SHORT']:
            total_strength = weights['LONG'] / len(signals)  # Normalize
            return {
                'direction': 'LONG',
                'strength': min(total_strength, 1.0),
                'components': components
            }
        elif weights['SHORT'] > weights['LONG']:
            total_strength = weights['SHORT'] / len(signals)
            return {
                'direction': 'SHORT',
                'strength': min(total_strength, 1.0),
                'components': components
            }
        else:
            return {
                'direction': 'NEUTRAL',
                'strength': 0.0,
                'components': components
            }

