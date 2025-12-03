"""Evaluation and backtesting utilities"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from loguru import logger


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """
    Calculate Sharpe ratio.
    
    Args:
        returns: Series of returns
        risk_free_rate: Risk-free rate (annualized)
        
    Returns:
        Sharpe ratio (annualized)
    """
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    
    # Annualize
    periods_per_year = 365  # Daily returns
    if len(returns) > 0:
        # Estimate frequency from data
        avg_period = (returns.index[-1] - returns.index[0]).days / len(returns) if len(returns) > 1 else 1
        periods_per_year = 365 / avg_period
    
    excess_returns = returns.mean() - (risk_free_rate / periods_per_year)
    sharpe = (excess_returns / returns.std()) * np.sqrt(periods_per_year)
    
    return float(sharpe)


def calculate_profit_factor(gross_profit: float, gross_loss: float) -> float:
    """
    Calculate profit factor.
    
    Args:
        gross_profit: Sum of all profitable trades
        gross_loss: Sum of all losing trades (absolute value)
        
    Returns:
        Profit factor (gross_profit / gross_loss)
    """
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    return float(gross_profit / abs(gross_loss))


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate maximum drawdown.
    
    Args:
        equity_curve: Series of account equity over time
        
    Returns:
        Maximum drawdown (as fraction, e.g., 0.15 for 15%)
    """
    if len(equity_curve) == 0:
        return 0.0
    
    # Calculate running maximum
    running_max = equity_curve.expanding().max()
    
    # Calculate drawdown
    drawdown = (equity_curve - running_max) / running_max
    
    return float(abs(drawdown.min()))


def calculate_metrics(
    trades: pd.DataFrame,
    initial_equity: float = 10000.0
) -> Dict[str, float]:
    """
    Calculate trading performance metrics.
    
    Args:
        trades: DataFrame with columns: 'pnl', 'entry_time', 'exit_time'
        initial_equity: Starting equity
        
    Returns:
        Dictionary of performance metrics
    """
    if len(trades) == 0:
        return {
            'total_return': 0.0,
            'sharpe_ratio': 0.0,
            'profit_factor': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'total_trades': 0
        }
    
    # Calculate equity curve
    trades_sorted = trades.sort_values('exit_time')
    equity = initial_equity
    equity_curve = [equity]
    returns = []
    
    for _, trade in trades_sorted.iterrows():
        equity += trade['pnl']
        equity_curve.append(equity)
        returns.append(trade['pnl'] / (equity - trade['pnl']))  # Return on capital
    
    equity_series = pd.Series(equity_curve)
    returns_series = pd.Series(returns)
    
    # Calculate metrics
    total_return = (equity - initial_equity) / initial_equity
    sharpe = calculate_sharpe_ratio(returns_series)
    max_dd = calculate_max_drawdown(equity_series)
    
    # Win rate
    winning_trades = trades[trades['pnl'] > 0]
    losing_trades = trades[trades['pnl'] < 0]
    win_rate = len(winning_trades) / len(trades) if len(trades) > 0 else 0.0
    
    # Profit factor
    gross_profit = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0.0
    gross_loss = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0.0
    profit_factor = calculate_profit_factor(gross_profit, gross_loss)
    
    # Average win/loss
    avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0.0
    avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0.0
    
    return {
        'total_return': float(total_return),
        'sharpe_ratio': sharpe,
        'profit_factor': profit_factor,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'avg_win': float(avg_win),
        'avg_loss': float(avg_loss),
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades)
    }


def walk_forward_validation(
    data: pd.DataFrame,
    train_func,
    test_func,
    train_window_days: int = 180,
    test_window_days: int = 30,
    step_days: int = 30,
    min_train_days: int = 90
) -> List[Dict[str, float]]:
    """
    Perform walk-forward validation.
    
    Args:
        data: DataFrame with datetime index and required columns
        train_func: Function to train model: train_func(train_data) -> model
        test_func: Function to test model: test_func(model, test_data) -> metrics_dict
        train_window_days: Training window size in days
        test_window_days: Test window size in days
        step_days: Step size for rolling forward
        min_train_days: Minimum training data required
        
    Returns:
        List of metrics dictionaries, one per fold
    """
    if 'timestamp' not in data.columns:
        if isinstance(data.index, pd.DatetimeIndex):
            data = data.reset_index()
            data['timestamp'] = data.index
        else:
            raise ValueError("Data must have timestamp column or DatetimeIndex")
    
    data = data.sort_values('timestamp').reset_index(drop=True)
    start_date = data['timestamp'].min()
    end_date = data['timestamp'].max()
    
    results = []
    current_date = start_date
    
    fold = 0
    while current_date < end_date:
        train_start = current_date
        train_end = train_start + timedelta(days=train_window_days)
        test_start = train_end
        test_end = test_start + timedelta(days=test_window_days)
        
        # Check if we have enough data
        if (train_end - start_date).days < min_train_days:
            current_date += timedelta(days=step_days)
            continue
        
        if test_end > end_date:
            break
        
        # Extract train and test data
        train_data = data[
            (data['timestamp'] >= train_start) & 
            (data['timestamp'] < train_end)
        ].copy()
        
        test_data = data[
            (data['timestamp'] >= test_start) & 
            (data['timestamp'] < test_end)
        ].copy()
        
        if len(train_data) == 0 or len(test_data) == 0:
            current_date += timedelta(days=step_days)
            continue
        
        try:
            # Train model
            logger.info(f"Fold {fold}: Training on {train_start.date()} to {train_end.date()}")
            model = train_func(train_data)
            
            # Test model
            logger.info(f"Fold {fold}: Testing on {test_start.date()} to {test_end.date()}")
            metrics = test_func(model, test_data)
            
            metrics['fold'] = fold
            metrics['train_start'] = train_start
            metrics['train_end'] = train_end
            metrics['test_start'] = test_start
            metrics['test_end'] = test_end
            
            results.append(metrics)
            
        except Exception as e:
            logger.error(f"Error in fold {fold}: {e}")
        
        # Roll forward
        current_date += timedelta(days=step_days)
        fold += 1
    
    logger.info(f"Walk-forward validation completed: {len(results)} folds")
    return results


def aggregate_walk_forward_results(results: List[Dict[str, float]]) -> Dict[str, any]:
    """
    Aggregate walk-forward validation results.
    
    Args:
        results: List of metrics dictionaries from walk-forward validation
        
    Returns:
        Dictionary with aggregate statistics
    """
    if not results:
        return {}
    
    # Extract numeric metrics
    metrics_to_aggregate = [
        'sharpe_ratio', 'profit_factor', 'max_drawdown', 'win_rate',
        'total_return', 'avg_win', 'avg_loss'
    ]
    
    aggregated = {}
    
    for metric in metrics_to_aggregate:
        values = [r.get(metric, 0.0) for r in results if metric in r]
        if values:
            aggregated[f'{metric}_mean'] = float(np.mean(values))
            aggregated[f'{metric}_std'] = float(np.std(values))
            aggregated[f'{metric}_min'] = float(np.min(values))
            aggregated[f'{metric}_max'] = float(np.max(values))
            aggregated[f'{metric}_median'] = float(np.median(values))
    
    # Total trades
    total_trades = sum(r.get('total_trades', 0) for r in results)
    aggregated['total_trades'] = total_trades
    aggregated['num_folds'] = len(results)
    
    return aggregated

