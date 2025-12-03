#!/usr/bin/env python3
"""
Analyze testnet campaign results.

Reads trade logs and generates summary reports.

Usage:
    python scripts/analyse_testnet_results.py --log-dir logs --output testnet_summary.md
"""

import argparse
import sys
import re
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.evaluation import calculate_metrics


def parse_trade_logs(log_dir: str) -> pd.DataFrame:
    """
    Parse trade logs to extract trade data.
    
    Args:
        log_dir: Directory containing log files
        
    Returns:
        DataFrame with trade data
    """
    log_path = Path(log_dir)
    trades = []
    
    # First, try to parse JSONL trade files (preferred)
    trade_log_dir = log_path / "trades"
    if trade_log_dir.exists():
        jsonl_files = list(trade_log_dir.glob("trades_*.jsonl"))
        for jsonl_file in jsonl_files:
            logger.info(f"Parsing {jsonl_file}")
            with open(jsonl_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        if event.get('event') == 'TRADE_CLOSED':
                            trades.append({
                                'timestamp': pd.to_datetime(event.get('exit_time', event.get('timestamp'))),
                                'symbol': event.get('symbol'),
                                'side': event.get('side'),
                                'entry_price': event.get('entry_price'),
                                'exit_price': event.get('exit_price'),
                                'qty': event.get('qty'),
                                'pnl': event.get('pnl'),
                                'pnl_pct': event.get('pnl_pct', 0),
                                'duration_hours': event.get('duration_hours', 0),
                                'is_win': event.get('pnl', 0) > 0,
                                'reason': 'UNKNOWN'  # Not in JSONL, would need to parse from log
                            })
                    except json.JSONDecodeError:
                        continue
    
    # Fallback: parse from log files if JSONL not found
    if not trades:
        log_files = list(log_path.glob("bot_*.log"))
        if not log_files:
            logger.warning(f"No trade log files found in {log_dir}")
            return pd.DataFrame()
        
        for log_file in log_files:
            logger.info(f"Parsing {log_file}")
            with open(log_file, 'r') as f:
                for line in f:
                    # Look for trade closure patterns
                    match = re.search(r'Closed position (\w+): (\w+) \| PnL: ([\d.-]+)', line)
                    if match:
                        symbol = match.group(1)
                        reason = match.group(2)
                        pnl = float(match.group(3))
                        
                        # Try to extract timestamp
                        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                        if timestamp_match:
                            timestamp = pd.to_datetime(timestamp_match.group(1))
                        else:
                            timestamp = datetime.utcnow()
                        
                        trades.append({
                            'timestamp': timestamp,
                            'symbol': symbol,
                            'reason': reason,
                            'pnl': pnl,
                            'is_win': pnl > 0
                        })
    
    if not trades:
        logger.warning("No trades found in logs")
        return pd.DataFrame()
    
    trades_df = pd.DataFrame(trades)
    trades_df = trades_df.sort_values('timestamp').reset_index(drop=True)
    
    logger.info(f"Parsed {len(trades_df)} trades")
    return trades_df


def calculate_daily_stats(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate daily statistics.
    
    Args:
        trades_df: DataFrame with trades
        
    Returns:
        DataFrame with daily stats
    """
    if trades_df.empty:
        return pd.DataFrame()
    
    trades_df['date'] = pd.to_datetime(trades_df['timestamp']).dt.date
    daily = trades_df.groupby('date').agg({
        'pnl': ['sum', 'count'],
        'is_win': 'sum'
    }).reset_index()
    
    daily.columns = ['date', 'daily_pnl', 'trade_count', 'win_count']
    daily['win_rate'] = daily['win_count'] / daily['trade_count']
    daily['cumulative_pnl'] = daily['daily_pnl'].cumsum()
    
    return daily


def generate_summary(trades_df: pd.DataFrame, output_path: str):
    """
    Generate summary report.
    
    Args:
        trades_df: DataFrame with trades
        output_path: Path to save summary
    """
    if trades_df.empty:
        logger.warning("No trades to summarize")
        return
    
    # Calculate metrics
    initial_equity = 10000.0  # Default for testnet
    metrics = calculate_metrics(trades_df, initial_equity)
    
    # Daily stats
    daily_stats = calculate_daily_stats(trades_df)
    
    # Generate report
    report_lines = [
        "# Testnet Campaign Summary",
        "",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        "",
        "## Overview",
        "",
        f"- **Total Trades:** {len(trades_df)}",
        f"- **Campaign Duration:** {trades_df['timestamp'].min()} to {trades_df['timestamp'].max()}",
        f"- **Symbols Traded:** {', '.join(trades_df['symbol'].unique())}",
        "",
        "## Performance Metrics",
        "",
        f"- **Total Return:** {metrics['total_return']:.2%}",
        f"- **Sharpe Ratio:** {metrics['sharpe_ratio']:.2f}",
        f"- **Profit Factor:** {metrics['profit_factor']:.2f}",
        f"- **Max Drawdown:** {metrics['max_drawdown']:.2%}",
        f"- **Win Rate:** {metrics['win_rate']:.2%}",
        f"- **Average Win:** {metrics['avg_win']:.2f} USDT",
        f"- **Average Loss:** {metrics['avg_loss']:.2f} USDT",
        "",
        "## Trade Breakdown",
        "",
        f"- **Winning Trades:** {metrics['winning_trades']}",
        f"- **Losing Trades:** {metrics['losing_trades']}",
        ""
    ]
    
    # Exit reasons
    if 'reason' in trades_df.columns:
        report_lines.extend([
            "## Exit Reasons",
            ""
        ])
        exit_reasons = trades_df['reason'].value_counts()
        for reason, count in exit_reasons.items():
            report_lines.append(f"- **{reason}:** {count} trades")
        report_lines.append("")
    
    # Daily performance
    if not daily_stats.empty:
        report_lines.extend([
            "## Daily Performance",
            "",
            "| Date | Daily PnL | Trades | Win Rate | Cumulative PnL |",
            "|------|-----------|--------|----------|-----------------|"
        ])
        for _, row in daily_stats.iterrows():
            report_lines.append(
                f"| {row['date']} | {row['daily_pnl']:.2f} | {row['trade_count']} | "
                f"{row['win_rate']:.2%} | {row['cumulative_pnl']:.2f} |"
            )
        report_lines.append("")
    
    # Recommendations
    report_lines.extend([
        "## Assessment",
        "",
        "### Good Enough Indicators:",
        "- Sharpe ratio > 0.8",
        "- Profit factor > 1.2",
        "- Win rate > 45%",
        "- Max drawdown < 15%",
        "- Consistent daily performance",
        "",
        "### Bad Indicators:",
        "- Sharpe ratio < 0.5",
        "- Profit factor < 1.0",
        "- Win rate < 40%",
        "- Max drawdown > 20%",
        "- High volatility in daily PnL",
        "",
        "### Decision:",
        "- **Proceed to Live:** If metrics are consistently good for 2+ weeks",
        "- **Extend Testnet:** If metrics are mixed or borderline",
        "- **Review Config:** If metrics are consistently poor",
        "",
        "---",
        "",
        "**Note:** Testnet results may differ from live trading due to:",
        "- Different liquidity",
        "- Different slippage",
        "- Different market conditions",
        "- Testnet-specific limitations"
    ])
    
    # Write report
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        f.write('\n'.join(report_lines))
    
    logger.info(f"Summary saved to {output_file}")
    
    # Also save CSV
    csv_path = output_file.parent / "testnet_trades.csv"
    trades_df.to_csv(csv_path, index=False)
    logger.info(f"Trade data saved to {csv_path}")
    
    if not daily_stats.empty:
        daily_csv_path = output_file.parent / "testnet_daily_stats.csv"
        daily_stats.to_csv(daily_csv_path, index=False)
        logger.info(f"Daily stats saved to {daily_csv_path}")


def main():
    parser = argparse.ArgumentParser(description='Analyze testnet results')
    parser.add_argument('--log-dir', type=str, default='logs', help='Directory with log files')
    parser.add_argument('--output', type=str, default='logs/testnet_summary.md', help='Output summary file')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.add("logs/analyse_testnet_{time}.log", rotation="1 day", level="INFO")
    
    logger.info("=" * 60)
    logger.info("Analyzing Testnet Results")
    logger.info("=" * 60)
    
    # Parse logs
    trades_df = parse_trade_logs(args.log_dir)
    
    if trades_df.empty:
        logger.error("No trades found. Cannot generate summary.")
        return 1
    
    # Generate summary
    generate_summary(trades_df, args.output)
    
    logger.info("Analysis complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

