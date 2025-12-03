"""Performance guard for automatic risk throttling"""

from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import deque
from loguru import logger


class PerformanceGuard:
    """
    Monitor recent performance and automatically throttle risk.
    
    Tiers:
    - NORMAL: Full trading
    - REDUCED: 50% position size, +0.1 confidence threshold
    - PAUSED: Stop trading until recovery
    """
    
    def __init__(self, config: dict):
        """
        Initialize performance guard.
        
        Args:
            config: Configuration dictionary with performance_guard settings
        """
        guard_config = config.get('performance_guard', {})
        
        self.enabled = guard_config.get('enabled', True)
        self.rolling_window_trades = guard_config.get('rolling_window_trades', 10)
        
        # Thresholds for reduced risk
        self.win_rate_threshold_reduced = guard_config.get('win_rate_threshold_reduced', 0.40)
        self.drawdown_threshold_reduced = guard_config.get('drawdown_threshold_reduced', 0.05)
        
        # Thresholds for paused
        self.win_rate_threshold_paused = guard_config.get('win_rate_threshold_paused', 0.30)
        self.drawdown_threshold_paused = guard_config.get('drawdown_threshold_paused', 0.10)
        
        # Recovery conditions
        self.recovery_win_rate = guard_config.get('recovery_win_rate', 0.45)
        self.recovery_drawdown = guard_config.get('recovery_drawdown', 0.05)
        
        # State tracking
        self.recent_trades = deque(maxlen=self.rolling_window_trades * 2)  # Keep more for recovery
        self.peak_equity = None
        self.initial_equity = None
        self.current_status = "NORMAL"
        self.status_since = datetime.utcnow()
        
        logger.info(f"Initialized PerformanceGuard (enabled={self.enabled})")
    
    def update_equity(self, equity: float):
        """
        Update current equity for drawdown tracking.
        
        Args:
            equity: Current account equity
        """
        if self.initial_equity is None:
            self.initial_equity = equity
            self.peak_equity = equity
        
        if equity > self.peak_equity:
            self.peak_equity = equity
    
    def record_trade(self, pnl: float, is_win: bool):
        """
        Record a completed trade.
        
        Args:
            pnl: Profit/loss of the trade
            is_win: True if profitable, False otherwise
        """
        self.recent_trades.append({
            'pnl': pnl,
            'is_win': is_win,
            'timestamp': datetime.utcnow()
        })
        
        # Update equity (simplified - assumes pnl is already reflected)
        # In practice, this should be called with actual equity
    
    def get_recent_metrics(self) -> Dict[str, float]:
        """
        Calculate recent performance metrics.
        
        Returns:
            Dictionary with win_rate, total_pnl, drawdown
        """
        if len(self.recent_trades) == 0:
            return {
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'losing_streak': 0,
                'drawdown': 0.0
            }
        
        # Last N trades
        recent = list(self.recent_trades)[-self.rolling_window_trades:]
        
        if len(recent) == 0:
            return {
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'losing_streak': 0,
                'drawdown': 0.0
            }
        
        wins = sum(1 for t in recent if t['is_win'])
        win_rate = wins / len(recent) if len(recent) > 0 else 0.0
        total_pnl = sum(t['pnl'] for t in recent)
        
        # Calculate losing streak
        losing_streak = 0
        for t in reversed(recent):
            if t['is_win']:
                break
            losing_streak += 1
        
        # Drawdown (if peak equity is set)
        drawdown = 0.0
        if self.peak_equity and self.initial_equity:
            current_equity = self.initial_equity + sum(t['pnl'] for t in self.recent_trades)
            if self.peak_equity > 0:
                drawdown = (self.peak_equity - current_equity) / self.peak_equity
        
        return {
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'losing_streak': losing_streak,
            'drawdown': drawdown,
            'num_trades': len(recent)
        }
    
    def check_status(self, current_equity: Optional[float] = None) -> Tuple[str, Dict[str, float]]:
        """
        Check current status and update if needed.
        
        Args:
            current_equity: Current account equity (optional, for drawdown)
            
        Returns:
            Tuple of (status, metrics_dict)
        """
        if not self.enabled:
            return "NORMAL", {}
        
        if current_equity:
            self.update_equity(current_equity)
        
        metrics = self.get_recent_metrics()
        
        # Check if we should pause
        if (metrics['win_rate'] < self.win_rate_threshold_paused and metrics['num_trades'] >= 5) or \
           metrics['losing_streak'] >= 10 or \
           (metrics['drawdown'] > self.drawdown_threshold_paused and self.peak_equity):
            
            if self.current_status != "PAUSED":
                logger.warning(
                    f"Performance guard: PAUSED | "
                    f"Win rate: {metrics['win_rate']:.2%}, "
                    f"Drawdown: {metrics['drawdown']:.2%}, "
                    f"Losing streak: {metrics['losing_streak']}"
                )
                self.current_status = "PAUSED"
                self.status_since = datetime.utcnow()
        
        # Check if we should reduce risk
        elif (metrics['win_rate'] < self.win_rate_threshold_reduced and metrics['num_trades'] >= 5) or \
             metrics['losing_streak'] >= 5 or \
             (metrics['drawdown'] > self.drawdown_threshold_reduced and self.peak_equity):
            
            if self.current_status == "NORMAL":
                logger.warning(
                    f"Performance guard: REDUCED RISK | "
                    f"Win rate: {metrics['win_rate']:.2%}, "
                    f"Drawdown: {metrics['drawdown']:.2%}"
                )
                self.current_status = "REDUCED"
                self.status_since = datetime.utcnow()
        
        # Check recovery conditions
        elif self.current_status in ["PAUSED", "REDUCED"]:
            if metrics['win_rate'] >= self.recovery_win_rate and \
               metrics['num_trades'] >= 5 and \
               metrics['drawdown'] < self.recovery_drawdown:
                
                logger.info(
                    f"Performance guard: RECOVERED to NORMAL | "
                    f"Win rate: {metrics['win_rate']:.2%}, "
                    f"Drawdown: {metrics['drawdown']:.2%}"
                )
                self.current_status = "NORMAL"
                self.status_since = datetime.utcnow()
        
        return self.current_status, metrics
    
    def get_size_multiplier(self) -> float:
        """
        Get position size multiplier based on current status.
        
        Returns:
            Multiplier (1.0 for normal, 0.5 for reduced, 0.0 for paused)
        """
        if not self.enabled:
            return 1.0
        
        if self.current_status == "PAUSED":
            return 0.0
        elif self.current_status == "REDUCED":
            return 0.5
        else:
            return 1.0
    
    def get_confidence_adjustment(self) -> float:
        """
        Get confidence threshold adjustment.
        
        Returns:
            Adjustment to add to base threshold (0.0 for normal, 0.1 for reduced)
        """
        if not self.enabled:
            return 0.0
        
        if self.current_status == "REDUCED":
            return 0.1
        else:
            return 0.0
    
    def should_allow_trade(self) -> Tuple[bool, str]:
        """
        Check if trading should be allowed.
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        if not self.enabled:
            return True, "OK"
        
        if self.current_status == "PAUSED":
            return False, "Performance guard: Trading paused due to poor performance"
        
        return True, "OK"
    
    def get_status(self) -> Dict[str, any]:
        """
        Get current status information.
        
        Returns:
            Dictionary with status, metrics, and multipliers
        """
        metrics = self.get_recent_metrics()
        
        return {
            'status': self.current_status,
            'status_since': self.status_since.isoformat(),
            'size_multiplier': self.get_size_multiplier(),
            'confidence_adjustment': self.get_confidence_adjustment(),
            'metrics': metrics
        }

