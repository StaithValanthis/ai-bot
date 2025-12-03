#!/usr/bin/env python3
"""
Show bot status in human-friendly format.

Reads bot_status.json and displays key information.

Usage:
    python scripts/show_status.py
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def format_status(status_file: str = "logs/bot_status.json"):
    """
    Format and display bot status.
    
    Args:
        status_file: Path to status JSON file
    """
    status_path = Path(status_file)
    
    if not status_path.exists():
        print(f"❌ Status file not found: {status_file}")
        print("   Bot may not be running or health checks not enabled.")
        return 1
    
    try:
        with open(status_path, 'r') as f:
            status = json.load(f)
    except Exception as e:
        print(f"❌ Error reading status file: {e}")
        return 1
    
    # Display status
    print("=" * 60)
    print("Bot Status")
    print("=" * 60)
    
    # Basic info
    timestamp = status.get('timestamp', 'Unknown')
    print(f"Last Update: {timestamp}")
    print(f"Bot Running: {'✅ YES' if status.get('bot_running', False) else '❌ NO'}")
    print()
    
    # Health status
    health_status = status.get('health_status', 'UNKNOWN')
    health_icon = {
        'HEALTHY': '✅',
        'DEGRADED': '⚠️',
        'UNHEALTHY': '❌',
        'DISABLED': '⚪'
    }.get(health_status, '❓')
    print(f"Health Status: {health_icon} {health_status}")
    print()
    
    # Issues
    issues = status.get('issues', [])
    if issues:
        print("⚠️ Issues:")
        for issue in issues:
            print(f"   - {issue}")
        print()
    
    # Warnings
    warnings = status.get('warnings', [])
    if warnings:
        print("⚠️ Warnings:")
        for warning in warnings:
            print(f"   - {warning}")
        print()
    
    # Metrics
    metrics = status.get('metrics', {})
    if metrics:
        print("Metrics:")
        
        # Performance guard
        pg_status = metrics.get('performance_guard_status', {})
        if pg_status:
            pg_state = pg_status.get('status', 'UNKNOWN')
            pg_icon = {
                'NORMAL': '✅',
                'REDUCED': '⚠️',
                'PAUSED': '❌'
            }.get(pg_state, '❓')
            print(f"   Performance Guard: {pg_icon} {pg_state}")
        
        # Regime
        regime = metrics.get('current_regime', 'UNKNOWN')
        print(f"   Current Regime: {regime}")
        
        # Open positions
        open_positions = status.get('open_positions_count', 0)
        print(f"   Open Positions: {open_positions}")
        
        # Last trade
        last_trade = status.get('last_trade_time', 'N/A')
        print(f"   Last Trade: {last_trade}")
        
        # API errors
        api_errors = status.get('api_error_count', 0)
        if api_errors > 0:
            print(f"   API Errors: ⚠️ {api_errors}")
        else:
            print(f"   API Errors: ✅ 0")
        
        print()
    
    # Portfolio status (if enabled)
    portfolio_status = status.get('portfolio_status', {})
    if portfolio_status and portfolio_status.get('enabled', False):
        print("Portfolio:")
        selected = portfolio_status.get('selected_symbols', [])
        print(f"   Selected Symbols: {', '.join(selected) if selected else 'None'}")
        print()
    
    # Summary
    if health_status == 'HEALTHY' and not issues:
        print("✅ Bot is healthy and running normally.")
    elif health_status == 'DEGRADED':
        print("⚠️ Bot is running but has some issues. Review warnings above.")
    elif health_status == 'UNHEALTHY':
        print("❌ Bot has critical issues. Review issues above and take action.")
    else:
        print("ℹ️ Status unknown or bot not running.")
    
    print("=" * 60)
    
    return 0


def main():
    parser = argparse.ArgumentParser(description='Show bot status')
    parser.add_argument('--status-file', type=str, default='logs/bot_status.json',
                       help='Path to status JSON file')
    
    args = parser.parse_args()
    
    return format_status(args.status_file)


if __name__ == "__main__":
    sys.exit(main())

