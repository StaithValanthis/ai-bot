"""Cross-sectional symbol selection and portfolio allocation"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from loguru import logger


class PortfolioSelector:
    """
    Selects symbols to trade based on cross-sectional ranking.
    
    Scores symbols by:
    - Recent risk-adjusted return (Sharpe-like)
    - Trend strength (ADX)
    - Model confidence (predicted edge)
    - Volatility (lower is better for trend-following)
    
    Selects top K symbols and allocates risk across them.
    """
    
    def __init__(self, config: dict):
        """
        Initialize portfolio selector.
        
        Args:
            config: Configuration dictionary with portfolio settings
        """
        portfolio_config = config.get('portfolio', {}).get('cross_sectional', {})
        
        self.enabled = portfolio_config.get('enabled', False)
        self.rebalance_interval_minutes = portfolio_config.get('rebalance_interval_minutes', 1440)  # 24 hours default
        self.top_k = portfolio_config.get('top_k', 3)
        self.max_symbol_risk_pct = portfolio_config.get('max_symbol_risk_pct', 0.10)  # 10% per symbol
        self.min_liquidity = portfolio_config.get('min_liquidity', 1000000)  # $1M 24h volume
        
        # Score component weights
        score_weights = portfolio_config.get('score_weights', {})
        self.weight_sharpe = score_weights.get('sharpe', 0.4)
        self.weight_adx = score_weights.get('adx', 0.3)
        self.weight_confidence = score_weights.get('confidence', 0.2)
        self.weight_volatility = score_weights.get('volatility', 0.1)
        
        # Normalize weights
        total_weight = self.weight_sharpe + self.weight_adx + self.weight_confidence + self.weight_volatility
        if total_weight > 0:
            self.weight_sharpe /= total_weight
            self.weight_adx /= total_weight
            self.weight_confidence /= total_weight
            self.weight_volatility /= total_weight
        
        # State tracking
        self.last_rebalance = None
        self.selected_symbols = []
        self.symbol_scores = {}
        
        logger.info(f"Initialized PortfolioSelector (enabled={self.enabled}, top_k={self.top_k})")
    
    def calculate_sharpe_score(self, returns: pd.Series, lookback_days: int = 30) -> float:
        """
        Calculate risk-adjusted return score (Sharpe-like).
        
        Args:
            returns: Series of returns
            lookback_days: Lookback period in days
            
        Returns:
            Sharpe-like score (normalized)
        """
        if len(returns) < lookback_days or returns.std() == 0:
            return 0.0
        
        recent_returns = returns.tail(lookback_days)
        sharpe = recent_returns.mean() / recent_returns.std() if recent_returns.std() > 0 else 0.0
        
        # Normalize to [0, 1] range (assuming Sharpe typically [-2, 2])
        return float(np.clip((sharpe + 2) / 4, 0.0, 1.0))
    
    def calculate_trend_strength(self, adx: float) -> float:
        """
        Calculate trend strength score from ADX.
        
        Args:
            adx: ADX value
            
        Returns:
            Normalized trend strength [0, 1]
        """
        # ADX > 25 is strong trend, normalize to [0, 1]
        return float(np.clip(adx / 50.0, 0.0, 1.0))
    
    def calculate_volatility_score(self, volatility: float, avg_volatility: float) -> float:
        """
        Calculate volatility score (lower is better for trend-following).
        
        Args:
            volatility: Current volatility
            avg_volatility: Average volatility
            
        Returns:
            Normalized score [0, 1] (higher = lower volatility relative to average)
        """
        if avg_volatility == 0:
            return 0.5
        
        ratio = volatility / avg_volatility
        # Lower volatility relative to average = higher score
        # If ratio < 1 (below average), score > 0.5
        # If ratio > 1 (above average), score < 0.5
        score = 1.0 / (1.0 + ratio)  # Inverse relationship
        
        return float(np.clip(score, 0.0, 1.0))
    
    def score_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        recent_confidence: Optional[float] = None
    ) -> float:
        """
        Calculate composite score for a symbol.
        
        Args:
            symbol: Trading symbol
            df: DataFrame with OHLCV and indicators
            recent_confidence: Recent model confidence (optional)
            
        Returns:
            Composite score [0, 1]
        """
        if df.empty or len(df) < 30:
            return 0.0
        
        latest = df.iloc[-1]
        
        # 1. Risk-adjusted return (Sharpe-like)
        if 'close' in df.columns:
            returns = df['close'].pct_change().dropna()
            sharpe_score = self.calculate_sharpe_score(returns)
        else:
            sharpe_score = 0.0
        
        # 2. Trend strength (ADX)
        if 'adx' in df.columns:
            adx_value = latest.get('adx', 0)
            adx_score = self.calculate_trend_strength(adx_value)
        else:
            adx_score = 0.0
        
        # 3. Model confidence (if available)
        if recent_confidence is not None:
            confidence_score = float(recent_confidence)  # Already [0, 1]
        else:
            confidence_score = 0.5  # Neutral if not available
        
        # 4. Volatility (lower is better)
        if 'atr' in df.columns and 'close' in df.columns:
            current_atr = latest.get('atr', 0)
            avg_atr = df['atr'].tail(30).mean() if len(df) >= 30 else current_atr
            volatility_score = self.calculate_volatility_score(current_atr / latest['close'], avg_atr / df['close'].tail(30).mean())
        else:
            volatility_score = 0.5  # Neutral if not available
        
        # Weighted composite score
        composite_score = (
            self.weight_sharpe * sharpe_score +
            self.weight_adx * adx_score +
            self.weight_confidence * confidence_score +
            self.weight_volatility * volatility_score
        )
        
        return float(np.clip(composite_score, 0.0, 1.0))
    
    def select_symbols(
        self,
        symbol_data: Dict[str, pd.DataFrame],
        symbol_confidence: Optional[Dict[str, float]] = None
    ) -> List[str]:
        """
        Select top K symbols to trade.
        
        Args:
            symbol_data: Dictionary of {symbol: DataFrame} with market data
            symbol_confidence: Optional dictionary of {symbol: confidence} from model
            
        Returns:
            List of selected symbol names
        """
        if not self.enabled:
            # If disabled, return all symbols (backward compatibility)
            return list(symbol_data.keys())
        
        if not symbol_data:
            return []
        
        # Calculate scores for all symbols
        scores = {}
        for symbol, df in symbol_data.items():
            confidence = symbol_confidence.get(symbol) if symbol_confidence else None
            score = self.score_symbol(symbol, df, confidence)
            scores[symbol] = score
        
        # Sort by score (descending)
        sorted_symbols = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Select top K
        selected = [symbol for symbol, score in sorted_symbols[:self.top_k]]
        
        # Store scores and selection
        self.symbol_scores = scores
        self.selected_symbols = selected
        self.last_rebalance = datetime.utcnow()
        
        logger.info(f"Selected symbols: {selected} (scores: {[f'{s:.2f}' for s in [scores[s] for s in selected]]})")
        
        return selected
    
    def should_rebalance(self) -> bool:
        """
        Check if rebalancing is needed.
        
        Returns:
            True if rebalancing interval has passed
        """
        if not self.enabled:
            return False
        
        if self.last_rebalance is None:
            return True
        
        minutes_elapsed = (datetime.utcnow() - self.last_rebalance).total_seconds() / 60
        return minutes_elapsed >= self.rebalance_interval_minutes
    
    def is_symbol_selected(self, symbol: str) -> bool:
        """
        Check if a symbol is currently selected for trading.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if symbol is selected
        """
        if not self.enabled:
            return True  # All symbols allowed if disabled
        
        return symbol in self.selected_symbols
    
    def get_symbol_risk_limit(self, symbol: str, total_equity: float) -> float:
        """
        Get maximum risk allocation for a symbol.
        
        Args:
            symbol: Trading symbol
            total_equity: Total account equity
            
        Returns:
            Maximum position value for this symbol
        """
        if not self.enabled:
            # If disabled, use global max position size
            return total_equity * self.max_symbol_risk_pct
        
        if symbol not in self.selected_symbols:
            return 0.0  # Not selected, no allocation
        
        # Equal allocation across selected symbols (could be improved with risk parity)
        num_selected = len(self.selected_symbols)
        if num_selected == 0:
            return 0.0
        
        # Per-symbol allocation, capped at max_symbol_risk_pct
        allocation = total_equity / num_selected
        max_allocation = total_equity * self.max_symbol_risk_pct
        
        return min(allocation, max_allocation)
    
    def get_status(self) -> Dict[str, any]:
        """
        Get current portfolio selection status.
        
        Returns:
            Dictionary with status information
        """
        return {
            'enabled': self.enabled,
            'selected_symbols': self.selected_symbols.copy(),
            'symbol_scores': self.symbol_scores.copy(),
            'last_rebalance': self.last_rebalance.isoformat() if self.last_rebalance else None,
            'top_k': self.top_k
        }

