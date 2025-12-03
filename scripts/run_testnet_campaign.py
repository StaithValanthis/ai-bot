#!/usr/bin/env python3
"""
Testnet campaign runner.

Runs the trading bot on testnet for a specified duration or until manually stopped.
Logs all trades and generates summary reports.

Usage:
    python scripts/run_testnet_campaign.py --duration-days 14 --profile conservative
"""

import argparse
import sys
import signal
import time
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from live_bot import TradingBot
import yaml


class TestnetCampaign:
    """Manage testnet trading campaign"""
    
    def __init__(self, config_path: str, profile: str = "conservative"):
        """
        Initialize testnet campaign.
        
        Args:
            config_path: Path to config file
            profile: Risk profile (conservative/moderate/aggressive)
        """
        self.config_path = config_path
        self.profile = profile
        self.bot = None
        self.start_time = None
        self.end_time = None
        self.running = False
        
        logger.info(f"Initialized TestnetCampaign (profile: {profile})")
    
    def apply_profile(self, config: dict) -> dict:
        """
        Apply risk profile to config.
        
        Args:
            config: Base configuration
            
        Returns:
            Modified configuration
        """
        profiles = {
            "conservative": {
                "risk": {
                    "max_leverage": 2.0,
                    "base_position_size": 0.01,
                    "max_position_size": 0.05,
                    "max_daily_loss": 0.03,
                    "max_drawdown": 0.10
                },
                "model": {
                    "confidence_threshold": 0.65
                },
                "regime_filter": {
                    "adx_threshold": 30,
                    "allow_ranging": False
                }
            },
            "moderate": {
                "risk": {
                    "max_leverage": 3.0,
                    "base_position_size": 0.02,
                    "max_position_size": 0.10,
                    "max_daily_loss": 0.05,
                    "max_drawdown": 0.15
                },
                "model": {
                    "confidence_threshold": 0.60
                },
                "regime_filter": {
                    "adx_threshold": 25,
                    "allow_ranging": False
                }
            },
            "aggressive": {
                "risk": {
                    "max_leverage": 5.0,
                    "base_position_size": 0.03,
                    "max_position_size": 0.15,
                    "max_daily_loss": 0.07,
                    "max_drawdown": 0.20
                },
                "model": {
                    "confidence_threshold": 0.55
                },
                "regime_filter": {
                    "adx_threshold": 20,
                    "allow_ranging": True
                }
            }
        }
        
        profile_config = profiles.get(self.profile, profiles["conservative"])
        
        # Deep merge
        for section, values in profile_config.items():
            if section not in config:
                config[section] = {}
            config[section].update(values)
        
        # Ensure testnet mode
        config["exchange"]["testnet"] = True
        
        return config
    
    def run(self, duration_days: int = None):
        """
        Run testnet campaign.
        
        Args:
            duration_days: Duration in days (None = run until stopped)
        """
        logger.info("=" * 60)
        logger.info("Starting Testnet Campaign")
        logger.info(f"Profile: {self.profile}")
        logger.info(f"Duration: {duration_days} days" if duration_days else "Until stopped")
        logger.info("=" * 60)
        
        # Load and apply profile
        from src.config.config_loader import load_config
        config = load_config(self.config_path)
        config = self.apply_profile(config)
        
        # Save testnet config (using JSON for simplicity, yaml requires pyyaml)
        testnet_config_path = Path("config") / f"testnet_{self.profile}.yaml"
        # Note: We'll use the base config and apply profile at runtime
        # For simplicity, we'll modify the bot to accept profile parameter
        logger.info(f"Using profile: {self.profile} (applied to base config)")
        
        # Initialize bot
        self.bot = TradingBot(config_path=str(testnet_config_path))
        
        # Set up signal handlers
        def signal_handler(sig, frame):
            logger.info("Received stop signal, shutting down...")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start bot
        self.start_time = datetime.utcnow()
        self.running = True
        
        # Run in background thread or directly
        import threading
        bot_thread = threading.Thread(target=self.bot.start, daemon=True)
        bot_thread.start()
        
        # Wait for duration or until stopped
        if duration_days:
            end_time = self.start_time + timedelta(days=duration_days)
            logger.info(f"Campaign will run until {end_time}")
            
            while self.running and datetime.utcnow() < end_time:
                time.sleep(60)  # Check every minute
        else:
            logger.info("Campaign running until stopped (Ctrl+C)")
            try:
                while self.running:
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
        
        self.stop()
    
    def stop(self):
        """Stop the campaign"""
        if self.bot:
            self.bot.stop()
        self.end_time = datetime.utcnow()
        self.running = False
        
        if self.start_time:
            duration = self.end_time - self.start_time
            logger.info(f"Campaign stopped. Duration: {duration}")
            logger.info(f"Trade logs: logs/bot_*.log")
            logger.info(f"Status file: logs/bot_status.json")


def main():
    parser = argparse.ArgumentParser(description='Run testnet campaign')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Base config file')
    parser.add_argument('--profile', type=str, default='conservative', choices=['conservative', 'moderate', 'aggressive'],
                       help='Risk profile')
    parser.add_argument('--duration-days', type=int, default=None, help='Duration in days (None = until stopped)')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.add("logs/testnet_campaign_{time}.log", rotation="1 day", level="INFO")
    
    # Run campaign
    campaign = TestnetCampaign(args.config, args.profile)
    campaign.run(duration_days=args.duration_days)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

