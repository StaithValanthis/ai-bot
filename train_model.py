#!/usr/bin/env python3
"""
Training script for meta-model.

Usage:
    python train_model.py --symbol BTCUSDT --days 730
"""

import argparse
import sys
import os
from pathlib import Path
from loguru import logger

# Add src to path - ensure absolute path regardless of CWD
# Get absolute path of script directory
_script_file = os.path.abspath(__file__)
_script_dir = os.path.dirname(_script_file)

# Verify src module exists before adding to path
_src_path = os.path.join(_script_dir, "src")
_src_init = os.path.join(_src_path, "__init__.py")

if not os.path.isdir(_src_path) or not os.path.isfile(_src_init):
    # Fallback: try current working directory
    _cwd = os.getcwd()
    _cwd_src = os.path.join(_cwd, "src")
    _cwd_src_init = os.path.join(_cwd_src, "__init__.py")
    
    if os.path.isdir(_cwd_src) and os.path.isfile(_cwd_src_init):
        if _cwd not in sys.path:
            sys.path.insert(0, _cwd)
        _script_dir = _cwd  # Use CWD as script dir
        _src_path = _cwd_src
    else:
        print(f"ERROR: Could not find src module.", file=sys.stderr)
        print(f"  Script directory: {_script_dir}", file=sys.stderr)
        print(f"  Expected src at: {_src_path}", file=sys.stderr)
        print(f"  Current working directory: {_cwd}", file=sys.stderr)
        print(f"  Expected src at CWD: {_cwd_src}", file=sys.stderr)
        print(f"  sys.path: {sys.path[:3]}", file=sys.stderr)
        sys.exit(1)

# Add script directory to path if not already there
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# Verify we can import src
try:
    import src
    if not hasattr(src, '__path__'):
        raise ImportError("src is not a package")
except ImportError as e:
    print(f"ERROR: Cannot import src module. Path setup may have failed.", file=sys.stderr)
    print(f"  Script dir: {_script_dir}", file=sys.stderr)
    print(f"  sys.path[0]: {sys.path[0] if sys.path else 'empty'}", file=sys.stderr)
    print(f"  Error: {e}", file=sys.stderr)
    sys.exit(1)

from src.config.config_loader import load_config
from src.data.historical_data import HistoricalDataCollector
from src.models.train import ModelTrainer
from src.exchange.universe import UniverseManager


def main():
    parser = argparse.ArgumentParser(description='Train meta-model for trading bot')
    parser.add_argument('--symbol', type=str, default=None, help='Trading symbol (if not provided, uses universe or config)')
    parser.add_argument('--days', type=int, default=730, help='Number of days of history')
    parser.add_argument('--version', type=str, default='1.0', help='Model version')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file path')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.add("logs/training_{time}.log", rotation="1 day", level="INFO")
    
    logger.info("=" * 60)
    logger.info("Starting model training")
    logger.info("=" * 60)
    
    # Load config
    config = load_config(args.config)
    logger.info(f"Loaded configuration from {args.config}")
    
    # Determine symbol(s) to train
    if args.symbol:
        # Explicit symbol provided via CLI
        symbols = [args.symbol]
        logger.info(f"Training for explicit symbol: {symbols[0]}")
    else:
        # Use universe manager or fallback to config
        universe_manager = UniverseManager(config)
        symbols = universe_manager.get_symbols()
        if not symbols:
            # Fallback to config symbols
            symbols = config.get('trading', {}).get('symbols', ['BTCUSDT'])
        logger.info(f"Training for {len(symbols)} symbol(s) from universe/config: {symbols}")
    
    # Train model for each symbol (or first symbol if multiple)
    if len(symbols) > 1:
        logger.warning(f"Multiple symbols provided ({len(symbols)}), training only for first: {symbols[0]}")
        logger.info("For multi-symbol training, run train_model.py separately for each symbol")
        symbols = [symbols[0]]
    
    symbol = symbols[0]
    
    # Initialize data collector
    data_collector = HistoricalDataCollector(
        api_key=config['exchange'].get('api_key'),
        api_secret=config['exchange'].get('api_secret'),
        testnet=config['exchange'].get('testnet', True)
    )
    
    # Download historical data
    logger.info(f"Downloading {args.days} days of historical data for {symbol}")
    df = data_collector.download_and_save(
        symbol=symbol,
        days=args.days,
        interval="60",  # 1 hour
        data_path=config['data']['historical_data_path']
    )
    
    if df.empty:
        logger.error("No data downloaded. Exiting.")
        return 1
    
    logger.info(f"Downloaded {len(df)} candles")
    logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Initialize trainer
    trainer = ModelTrainer(config)
    
    # Prepare training data
    logger.info("Preparing training data...")
    labeling_config = config.get('labeling', {})
    execution_config = config.get('execution', {})
    
    features_df, labels = trainer.prepare_data(
        df=df,
        symbol=symbol,
        hold_periods=4,  # Fallback for time barrier
        profit_threshold=0.005,  # Fallback threshold
        fee_rate=0.0005,  # 0.05% per trade
        use_triple_barrier=labeling_config.get('use_triple_barrier', True),
        profit_barrier=labeling_config.get('profit_barrier', 0.02),
        loss_barrier=labeling_config.get('loss_barrier', 0.01),
        time_barrier_hours=labeling_config.get('time_barrier_hours', 24),
        base_slippage=execution_config.get('base_slippage', 0.0001),
        include_funding=execution_config.get('include_funding', True),
        funding_rate=execution_config.get('default_funding_rate', 0.0001)
    )
    
    if features_df.empty:
        logger.error("No training samples generated. Exiting.")
        return 1
    
    # Train model
    logger.info("Training model...")
    use_ensemble = config.get('model', {}).get('use_ensemble', True)
    model, scaler, metrics = trainer.train_model(
        features_df=features_df,
        labels=labels,
        test_size=0.2,
        validation_size=0.2,
        use_ensemble=use_ensemble
    )
    
    # Save model
    logger.info("Saving model...")
    trainer.save_model(
        model=model,
        scaler=scaler,
        metrics=metrics,
        features_df=features_df,
        version=args.version
    )
    
    logger.info("=" * 60)
    logger.info("Training completed successfully!")
    logger.info(f"Model version: {args.version}")
    logger.info(f"Performance metrics: {metrics}")
    logger.info("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

