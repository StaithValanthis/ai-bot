"""Health check and monitoring for trading bot"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from loguru import logger


class HealthMonitor:
    """Monitor bot health and generate status reports"""
    
    def __init__(self, config: dict, status_file_path: str = "logs/bot_status.json"):
        """
        Initialize health monitor.
        
        Args:
            config: Configuration dictionary
            status_file_path: Path to status JSON file
        """
        self.config = config
        self.status_file_path = Path(status_file_path)
        self.status_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # State tracking
        self.last_candle_time = {}
        self.last_trade_time = None
        self.last_health_check = None
        self.api_error_count = 0
        self.api_error_window_start = None
        
        # Thresholds from config
        ops_config = config.get('operations', {})
        self.health_check_interval = ops_config.get('health_check_interval_seconds', 300)
        self.max_candle_gap_minutes = ops_config.get('max_candle_gap_minutes', 15)
        self.max_api_errors = ops_config.get('max_api_errors', 5)
        self.api_error_window_minutes = ops_config.get('api_error_window_minutes', 10)
        self.max_no_trade_hours = ops_config.get('max_no_trade_hours', 168)  # 7 days
        
        logger.info(f"Initialized HealthMonitor (status file: {self.status_file_path})")
    
    def update_candle(self, symbol: str, timestamp: datetime):
        """
        Update last candle timestamp for a symbol.
        
        Args:
            symbol: Trading symbol
            timestamp: Candle timestamp
        """
        self.last_candle_time[symbol] = timestamp
    
    def update_trade(self, timestamp: datetime):
        """
        Update last trade timestamp.
        
        Args:
            timestamp: Trade timestamp
        """
        self.last_trade_time = timestamp
    
    def record_api_error(self):
        """Record an API error occurrence."""
        now = datetime.utcnow()
        
        # Reset window if too old
        if self.api_error_window_start is None or \
           (now - self.api_error_window_start).total_seconds() > self.api_error_window_minutes * 60:
            self.api_error_count = 0
            self.api_error_window_start = now
        
        self.api_error_count += 1
    
    def check_health(
        self,
        bot_running: bool,
        open_positions: Dict[str, Any],
        performance_guard_status: Dict[str, Any],
        regime_info: Optional[Dict[str, Any]] = None,
        model_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform health check and return status.
        
        Args:
            bot_running: Whether bot is currently running
            open_positions: Dictionary of open positions
            performance_guard_status: Status from performance guard
            regime_info: Current regime information (optional)
            model_info: Model information (optional)
            
        Returns:
            Dictionary with health status
        """
        now = datetime.utcnow()
        self.last_health_check = now
        
        status = {
            'timestamp': now.isoformat(),
            'bot_running': bot_running,
            'health_status': 'HEALTHY',
            'issues': [],
            'warnings': [],
            'metrics': {}
        }
        
        # Check data feed
        data_feed_ok = True
        for symbol, last_time in self.last_candle_time.items():
            if last_time:
                gap_minutes = (now - last_time).total_seconds() / 60
                if gap_minutes > self.max_candle_gap_minutes:
                    status['issues'].append(f"Data feed stalled for {symbol}: {gap_minutes:.1f} minutes")
                    status['health_status'] = 'DEGRADED'
                    data_feed_ok = False
        
        if not self.last_candle_time:
            status['warnings'].append("No candle data received yet")
        
        # Check API errors
        if self.api_error_count >= self.max_api_errors:
            status['issues'].append(f"High API error rate: {self.api_error_count} errors in last {self.api_error_window_minutes} minutes")
            status['health_status'] = 'DEGRADED'
        
        # Check trading activity
        if self.last_trade_time:
            hours_since_trade = (now - self.last_trade_time).total_seconds() / 3600
            if hours_since_trade > self.max_no_trade_hours:
                status['warnings'].append(f"No trades in {hours_since_trade:.1f} hours")
        else:
            status['warnings'].append("No trades recorded yet")
        
        # Add metrics
        status['metrics'] = {
            'open_positions': len(open_positions),
            'performance_guard_status': performance_guard_status.get('status', 'UNKNOWN'),
            'last_trade_hours_ago': (now - self.last_trade_time).total_seconds() / 3600 if self.last_trade_time else None,
            'api_error_count': self.api_error_count,
            'data_feed_ok': data_feed_ok
        }
        
        # Add regime info if available
        if regime_info:
            status['metrics']['current_regime'] = regime_info.get('regime', 'UNKNOWN')
        
        # Add model info if available
        if model_info:
            status['metrics']['model_version'] = model_info.get('version', 'UNKNOWN')
            status['metrics']['model_age_days'] = model_info.get('age_days', None)
        
        # Determine overall health
        if status['issues']:
            if any('stalled' in issue.lower() or 'error' in issue.lower() for issue in status['issues']):
                status['health_status'] = 'UNHEALTHY'
        
        return status
    
    def write_status_file(self, status: Dict[str, Any]):
        """
        Write status to JSON file.
        
        Args:
            status: Health status dictionary
        """
        try:
            with open(self.status_file_path, 'w') as f:
                json.dump(status, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error writing status file: {e}")
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """
        Read current status from file.
        
        Returns:
            Status dictionary or None if file doesn't exist
        """
        if not self.status_file_path.exists():
            return None
        
        try:
            with open(self.status_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading status file: {e}")
            return None

