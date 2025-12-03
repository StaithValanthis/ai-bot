"""Trade logging and PnL tracking"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from loguru import logger


class TradeLogger:
    """Log trading activity and track PnL"""
    
    def __init__(self, config: dict):
        """
        Initialize trade logger.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config.get('logging', {})
        self.trade_log_path = Path(self.config.get('trade_log_path', 'logs/trades'))
        self.pnl_log_path = Path(self.config.get('pnl_log_path', 'logs/pnl'))
        
        # Create log directories
        self.trade_log_path.mkdir(parents=True, exist_ok=True)
        self.pnl_log_path.mkdir(parents=True, exist_ok=True)
        
        # PnL tracking
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.win_count = 0
        
        logger.info("Initialized TradeLogger")
    
    def log_signal(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        features: Dict
    ):
        """Log signal generation"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': 'SIGNAL_GENERATED',
            'symbol': symbol,
            'direction': direction,
            'confidence': confidence,
            'features': features
        }
        
        self._write_log(self.trade_log_path, event)
        logger.info(f"Signal: {direction} {symbol} (confidence: {confidence:.2f})")
    
    def log_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_id: str,
        order_type: str = "Market"
    ):
        """Log order placement"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': 'ORDER_PLACED',
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'price': price,
            'order_id': order_id,
            'order_type': order_type
        }
        
        self._write_log(self.trade_log_path, event)
        logger.info(f"Order: {side} {qty} {symbol} @ {price} (ID: {order_id})")
    
    def log_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        qty: float,
        pnl: float,
        entry_time: datetime,
        exit_time: datetime
    ):
        """Log completed trade"""
        event = {
            'timestamp': exit_time.isoformat(),
            'event': 'TRADE_CLOSED',
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'qty': qty,
            'pnl': pnl,
            'pnl_pct': (pnl / (entry_price * qty)) * 100 if entry_price * qty > 0 else 0,
            'entry_time': entry_time.isoformat(),
            'exit_time': exit_time.isoformat(),
            'duration_hours': (exit_time - entry_time).total_seconds() / 3600
        }
        
        self._write_log(self.trade_log_path, event)
        
        # Update PnL tracking
        self.total_pnl += pnl
        self.daily_pnl += pnl
        self.trade_count += 1
        if pnl > 0:
            self.win_count += 1
        
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        
        logger.info(
            f"Trade closed: {side} {symbol} | "
            f"Entry: {entry_price} | Exit: {exit_price} | "
            f"PnL: {pnl:.2f} USDT | Win Rate: {win_rate:.1f}%"
        )
    
    def log_error(self, error_type: str, message: str, details: Optional[Dict] = None):
        """Log error"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': 'ERROR',
            'error_type': error_type,
            'message': message,
            'details': details or {}
        }
        
        self._write_log(self.trade_log_path, event)
        logger.error(f"{error_type}: {message}")
    
    def get_summary(self) -> Dict:
        """Get trading summary"""
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        
        return {
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'trade_count': self.trade_count,
            'win_count': self.win_count,
            'win_rate': win_rate
        }
    
    def _write_log(self, log_dir: Path, event: Dict):
        """Write log entry to file"""
        today = datetime.utcnow().strftime('%Y%m%d')
        log_file = log_dir / f"trades_{today}.jsonl"
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(event) + '\n')

