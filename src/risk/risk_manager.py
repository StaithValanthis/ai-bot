"""Risk management and position sizing"""

from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from loguru import logger


class RiskManager:
    """Manage risk limits and position sizing"""
    
    def __init__(self, config: dict):
        """
        Initialize risk manager.
        
        Args:
            config: Configuration dictionary with risk settings
        """
        self.config = config.get('risk', {})
        self.max_leverage = self.config.get('max_leverage', 3.0)
        self.max_position_size = self.config.get('max_position_size', 0.10)
        self.max_daily_loss = self.config.get('max_daily_loss', 0.05)
        self.max_drawdown = self.config.get('max_drawdown', 0.15)
        self.max_open_positions = self.config.get('max_open_positions', 3)
        self.base_position_size = self.config.get('base_position_size', 0.02)
        
        # Track daily PnL
        self.daily_pnl = 0.0
        self.daily_reset_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        self.peak_equity = None
        self.initial_equity = None
        
        logger.info("Initialized RiskManager")
    
    def update_account_state(self, equity: float):
        """
        Update account equity for drawdown tracking.
        
        Args:
            equity: Current account equity
        """
        if self.initial_equity is None:
            self.initial_equity = equity
            self.peak_equity = equity
        
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Reset daily PnL at midnight UTC
        now = datetime.utcnow()
        if now.date() > self.daily_reset_time.date():
            self.daily_pnl = 0.0
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    def update_daily_pnl(self, pnl: float):
        """
        Update daily PnL.
        
        Args:
            pnl: PnL to add (can be negative)
        """
        self.daily_pnl += pnl
    
    def calculate_position_size(
        self,
        equity: float,
        signal_confidence: float,
        entry_price: float,
        current_volatility: Optional[float] = None
    ) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            equity: Account equity
            signal_confidence: Meta-model confidence (0.0 to 1.0)
            entry_price: Entry price
            
        Returns:
            Position size in base currency (e.g., BTC quantity)
        """
        # Base position size
        base_size_pct = self.base_position_size
        
        # Scale by confidence
        confidence_multiplier = signal_confidence
        adjusted_size_pct = base_size_pct * confidence_multiplier
        
        # Volatility targeting (if enabled and volatility provided)
        volatility_config = self.config.get('volatility_targeting', {})
        if volatility_config.get('enabled', False) and current_volatility is not None:
            target_vol = volatility_config.get('target_volatility', 0.01)
            max_mult = volatility_config.get('max_multiplier', 2.0)
            vol_multiplier = min(target_vol / current_volatility if current_volatility > 0 else 1.0, max_mult)
            adjusted_size_pct *= vol_multiplier
            logger.debug(f"Volatility multiplier: {vol_multiplier:.2f} (vol: {current_volatility:.4f}, target: {target_vol:.4f})")
        
        # Cap at max position size
        adjusted_size_pct = min(adjusted_size_pct, self.max_position_size)
        
        # Calculate position value
        position_value = equity * adjusted_size_pct
        
        # Convert to quantity (assuming USDT perp, so quantity = value / price)
        quantity = position_value / entry_price
        
        logger.debug(f"Position size: {quantity:.6f} (confidence: {signal_confidence:.2f}, size_pct: {adjusted_size_pct:.2%})")
        
        return quantity
    
    def check_risk_limits(
        self,
        equity: float,
        open_positions: List[Dict],
        symbol: str,
        proposed_size: float
    ) -> Tuple[bool, str]:
        """
        Check if proposed trade violates risk limits.
        
        Args:
            equity: Account equity
            open_positions: List of open positions
            symbol: Trading symbol
            proposed_size: Proposed position size
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        # Check daily loss limit
        if self.daily_pnl < -abs(equity * self.max_daily_loss):
            return False, f"Daily loss limit exceeded: {self.daily_pnl:.2f}"
        
        # Check drawdown
        if self.peak_equity:
            current_drawdown = (self.peak_equity - equity) / self.peak_equity
            if current_drawdown > self.max_drawdown:
                return False, f"Max drawdown exceeded: {current_drawdown:.2%}"
        
        # Check max open positions
        if len(open_positions) >= self.max_open_positions:
            return False, f"Max open positions reached: {len(open_positions)}"
        
        # Check position size
        position_value = proposed_size * equity  # Simplified
        if position_value > equity * self.max_position_size:
            return False, f"Position size exceeds limit: {position_value:.2f}"
        
        # Check if already have position in this symbol
        for pos in open_positions:
            if pos.get('symbol') == symbol:
                return False, f"Already have position in {symbol}"
        
        return True, "OK"
    
    def should_trigger_kill_switch(
        self,
        equity: float,
        error_count: int = 0
    ) -> Tuple[bool, str]:
        """
        Check if kill switch should be triggered.
        
        Args:
            equity: Current account equity
            error_count: Number of recent errors
            
        Returns:
            Tuple of (should_trigger, reason)
        """
        # Check drawdown
        if self.peak_equity:
            drawdown = (self.peak_equity - equity) / self.peak_equity
            if drawdown > self.max_drawdown:
                return True, f"Drawdown exceeded: {drawdown:.2%}"
        
        # Check daily loss
        if self.daily_pnl < -abs(equity * self.max_daily_loss):
            return True, f"Daily loss limit exceeded: {self.daily_pnl:.2f}"
        
        # Check error count
        if error_count > 10:
            return True, f"Too many errors: {error_count}"
        
        return False, "OK"

