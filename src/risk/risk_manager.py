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
        self.risk_per_trade_pct = self.config.get('risk_per_trade_pct', 0.015)  # 1.5% base risk per trade
        self.stop_loss_pct = self.config.get('stop_loss_pct', 0.015)  # 1.5% stop loss
        
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
        Calculate position size based on risk parameters (risk-based sizing).
        
        Uses risk-based position sizing where:
        - Target Risk = 0.9% - 2.0% of equity (scales with confidence)
        - Position Value = Target Risk / Stop Loss %
        - Quantity = Position Value / Entry Price
        
        This ensures each trade risks 1-2% of equity, regardless of position size.
        
        Args:
            equity: Account equity
            signal_confidence: Meta-model confidence (0.0 to 1.0)
            entry_price: Entry price
            current_volatility: Optional volatility for volatility targeting
            
        Returns:
            Position size in base currency (e.g., token quantity)
        """
        # Get stop loss percentage
        stop_loss_pct = self.config.get('stop_loss_pct', 0.015)
        
        # Target risk per trade (scaled by confidence)
        # Base risk: 1.0% of equity (configurable via risk_per_trade_pct)
        base_risk_pct = self.config.get('risk_per_trade_pct', 0.01)  # 1.0% default
        
        # Scale risk by confidence (higher confidence = higher risk)
        # With base_risk_pct = 0.01: Confidence 0.3 -> 0.6% risk, Confidence 0.5 -> 1.0% risk, Confidence 1.0 -> 1.33% risk
        min_risk_pct = base_risk_pct * 0.6  # 0.6% minimum (with 1.0% base)
        max_risk_pct = base_risk_pct * 1.33  # 1.33% maximum (with 1.0% base)
        target_risk_pct = min_risk_pct + (max_risk_pct - min_risk_pct) * signal_confidence
        
        # Calculate position value based on risk
        # Risk = Position Value * Stop Loss
        # Position Value = Risk / Stop Loss
        target_risk_amount = equity * target_risk_pct
        position_value = target_risk_amount / stop_loss_pct
        
        # Volatility targeting (if enabled and volatility provided)
        volatility_config = self.config.get('volatility_targeting', {})
        if volatility_config.get('enabled', False) and current_volatility is not None:
            target_vol = volatility_config.get('target_volatility', 0.01)
            max_mult = volatility_config.get('max_multiplier', 2.0)
            vol_multiplier = min(target_vol / current_volatility if current_volatility > 0 else 1.0, max_mult)
            position_value *= vol_multiplier
            logger.debug(f"Volatility multiplier: {vol_multiplier:.2f} (vol: {current_volatility:.4f}, target: {target_vol:.4f})")
        
        # Cap at max position size (as percentage of equity)
        max_position_value = equity * self.max_position_size
        position_value = min(position_value, max_position_value)
        
        # Convert to quantity (quantity = value / price)
        quantity = position_value / entry_price if entry_price > 0 else 0
        
        # Calculate actual risk for logging
        actual_risk_pct = (position_value * stop_loss_pct) / equity if equity > 0 else 0
        
        logger.debug(
            f"Position size: {quantity:.6f} (confidence: {signal_confidence:.2f}, "
            f"target_risk: {target_risk_pct:.2%}, actual_risk: {actual_risk_pct:.2%}, "
            f"position_value: ${position_value:.2f})"
        )
        
        return quantity
    
    def check_risk_limits(
        self,
        equity: float,
        open_positions: List[Dict],
        symbol: str,
        proposed_size: float,
        entry_price: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Check if proposed trade violates risk limits.
        
        Args:
            equity: Account equity
            open_positions: List of open positions
            symbol: Trading symbol
            proposed_size: Proposed position size in tokens (quantity)
            entry_price: Entry price per token (required for position value calculation)
            
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
        # proposed_size is in tokens (quantity), not a percentage
        # Position value = quantity × price
        if entry_price is None or entry_price <= 0:
            return False, f"Invalid entry price for position size check: {entry_price}"
        
        position_value = proposed_size * entry_price  # Correct: tokens × price = USD value
        max_position_value = equity * self.max_position_size
        if position_value > max_position_value:
            return False, f"Position size exceeds limit: ${position_value:.2f} > ${max_position_value:.2f} (max {self.max_position_size:.1%} of equity)"
        
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

