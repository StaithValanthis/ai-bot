#!/usr/bin/env python3
"""
Training script for meta-model.

Usage:
    python train_model.py --symbol BTCUSDT --days 730
    
Model Architecture:
    - Single-symbol mode (default): Trains on one symbol, saves shared model
    - Multi-symbol mode: Trains on multiple symbols with symbol encoding, saves shared model
    
    The trained model is shared across all symbols during live trading.
    In multi-symbol mode, symbol identity is encoded as features (one-hot or index).
    The model learns both common patterns and symbol-specific nuances.
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

# Verify we can import src - clear cache first to avoid stale imports
import importlib
# Clear any cached src modules
modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('src')]
for m in modules_to_remove:
    del sys.modules[m]

try:
    # Import src package normally - Python should find it via sys.path
    import src
    if not hasattr(src, '__path__'):
        raise ImportError("src is not a package")
    
    # Verify src.data submodule directory exists (Python 3.3+ can import packages without __init__.py)
    data_dir = os.path.join(_src_path, 'data')
    if not os.path.isdir(data_dir):
        raise ImportError(f"src/data directory not found at {data_dir}")
    
    # Import the submodule - this should work if src is in sys.path
    # Python 3.3+ supports namespace packages, so __init__.py is optional
    import src.data
except ImportError as e:
    print(f"ERROR: Cannot import src module. Path setup may have failed.", file=sys.stderr)
    print(f"  Script dir: {_script_dir}", file=sys.stderr)
    print(f"  CWD: {os.getcwd()}", file=sys.stderr)
    print(f"  sys.path[0:3]: {sys.path[:3]}", file=sys.stderr)
    print(f"  src path exists: {os.path.isdir(_src_path)}", file=sys.stderr)
    print(f"  src/__init__.py exists: {os.path.isfile(_src_init)}", file=sys.stderr)
    data_init = os.path.join(_src_path, 'data', '__init__.py')
    print(f"  src/data/__init__.py exists: {os.path.isfile(data_init)}", file=sys.stderr)
    if os.path.isdir(_src_path):
        try:
            print(f"  Contents of src/: {os.listdir(_src_path)}", file=sys.stderr)
        except:
            pass
    print(f"  Error: {e}", file=sys.stderr)
    print(f"  Try: Ensure you're running from the repo root and src/ directory exists", file=sys.stderr)
    sys.exit(1)

from src.config.config_loader import load_config
from src.data.historical_data import HistoricalDataCollector
from src.models.train import ModelTrainer
from src.exchange.universe import UniverseManager
from datetime import timedelta


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
    
    # Determine training mode and symbol(s) to train
    training_mode = config.get('model', {}).get('training_mode', 'single_symbol')
    
    if args.symbol:
        # Explicit symbol provided via CLI
        symbols = [args.symbol]
        logger.info(f"Training for explicit symbol: {symbols[0]}")
        # CLI override: use single-symbol mode if explicit symbol provided
        training_mode = 'single_symbol'
    else:
        # Use universe manager or fallback to config
        universe_manager = UniverseManager(config)
        symbols = universe_manager.get_symbols()
        if not symbols:
            # Fallback to config symbols
            symbols = config.get('trading', {}).get('symbols', ['BTCUSDT'])
        logger.info(f"Training for {len(symbols)} symbol(s) from universe/config: {symbols}")
    
    # Handle multi-symbol vs single-symbol training
    if training_mode == 'multi_symbol':
        # Multi-symbol training: use all symbols
        if len(symbols) == 1:
            logger.warning("Multi-symbol mode enabled but only one symbol available. Falling back to single-symbol mode.")
            training_mode = 'single_symbol'
        else:
            # Limit to reasonable number for training (configurable)
            max_training_symbols = config.get('model', {}).get('max_training_symbols', 10)
            if len(symbols) > max_training_symbols:
                logger.info(f"Limiting training to top {max_training_symbols} symbols (have {len(symbols)})")
                symbols = symbols[:max_training_symbols]
            logger.info(f"Multi-symbol training mode: using {len(symbols)} symbols")
    else:
        # Single-symbol training: use first symbol only (backward compatible)
        if len(symbols) > 1:
            logger.warning(f"Single-symbol mode: multiple symbols provided ({len(symbols)}), training only for first: {symbols[0]}")
            logger.info("To enable multi-symbol training, set model.training_mode: 'multi_symbol' in config")
        symbols = [symbols[0]]
    
    symbol = symbols[0] if training_mode == 'single_symbol' else None
    
    # Initialize data collector
    data_collector = HistoricalDataCollector(
        api_key=config['exchange'].get('api_key'),
        api_secret=config['exchange'].get('api_secret'),
        testnet=config['exchange'].get('testnet', True)
    )
    
    # Initialize trainer
    trainer = ModelTrainer(config)
    
    # Prepare training data based on mode
    labeling_config = config.get('labeling', {})
    execution_config = config.get('execution', {})
    
    # Get history policy from config
    model_config = config.get('model', {})
    target_history_days = model_config.get('target_history_days', 730)
    min_history_days = model_config.get('min_history_days_to_train', 90)
    min_coverage_pct = model_config.get('min_history_coverage_pct', 0.95)
    block_short_history = model_config.get('block_short_history_symbols', True)
    
    # Use target_history_days as the request, but allow less if that's all that's available
    requested_days = min(args.days, target_history_days)
    logger.info(f"History policy: target={target_history_days} days, minimum={min_history_days} days, coverage={min_coverage_pct*100}%")
    
    if training_mode == 'multi_symbol':
        # Multi-symbol training: download data for all symbols
        logger.info(f"Downloading up to {requested_days} days of historical data for {len(symbols)} symbols")
        symbol_dataframes = {}
        symbol_history_info = {}  # Track history metrics per symbol
        
        for sym in symbols:
            logger.info(f"Downloading data for {sym}...")
            df = data_collector.download_and_save(
                symbol=sym,
                days=requested_days,
                interval="60",  # 1 hour
                data_path=config['data']['historical_data_path']
            )
            
            if df.empty:
                logger.warning(f"No data downloaded for {sym}, skipping")
                continue
            
            # Calculate history metrics
            history_metrics = HistoricalDataCollector.calculate_history_metrics(df, expected_interval_minutes=60)
            symbol_history_info[sym] = history_metrics
            
            available_days = history_metrics['available_days']
            coverage_pct = history_metrics['coverage_pct']
            
            logger.info(f"Downloaded {len(df)} candles for {sym}: {available_days} days available, {coverage_pct*100:.1f}% coverage")
            
            # Check if symbol meets minimum requirements
            if block_short_history and available_days < min_history_days:
                logger.warning(f"Symbol {sym} has only {available_days} days of history (< {min_history_days} minimum). Skipping.")
                continue
            
            if coverage_pct < min_coverage_pct:
                logger.warning(f"Symbol {sym} has {coverage_pct*100:.1f}% coverage (< {min_coverage_pct*100}% required). Skipping.")
                continue
            
            # Use actual available days (capped at target)
            actual_days_used = min(available_days, target_history_days)
            if available_days > target_history_days:
                # Use most recent target_history_days
                df = df.sort_values('timestamp').tail(int(target_history_days * 24)).reset_index(drop=True)
                logger.info(f"Using most recent {target_history_days} days for {sym} (had {available_days} days available)")
            
            symbol_dataframes[sym] = df
            logger.info(f"Using {len(df)} candles for {sym} ({actual_days_used} days)")
        
        if not symbol_dataframes:
            logger.error("No symbols met history requirements. Exiting.")
            logger.error(f"Required: >= {min_history_days} days, >= {min_coverage_pct*100}% coverage")
            return 1
        
        # Prepare multi-symbol training data
        logger.info("Preparing multi-symbol training data...")
        features_df, labels, symbol_encoding_map = trainer.prepare_multi_symbol_data(
            symbol_dataframes=symbol_dataframes,
            hold_periods=4,
            profit_threshold=0.005,
            fee_rate=0.0005,
            use_triple_barrier=labeling_config.get('use_triple_barrier', True),
            profit_barrier=labeling_config.get('profit_barrier', 0.02),
            loss_barrier=labeling_config.get('loss_barrier', 0.01),
            time_barrier_hours=labeling_config.get('time_barrier_hours', 24),
            base_slippage=execution_config.get('base_slippage', 0.0001),
            include_funding=execution_config.get('include_funding', True),
            funding_rate=execution_config.get('default_funding_rate', 0.0001)
        )
        
        # Store symbol encoding map in trainer for later use (e.g., saving to config)
        trainer.symbol_encoding_map = symbol_encoding_map
        
        # Store model coverage metadata with actual history used per symbol
        trainer.trained_symbols = list(symbol_dataframes.keys())
        # Calculate actual days used (may be less than target if symbol is newer)
        actual_days_used = {}
        for sym, df in symbol_dataframes.items():
            metrics = symbol_history_info.get(sym, {})
            actual_days = min(metrics.get('available_days', 0), target_history_days)
            actual_days_used[sym] = actual_days
        
        # Use minimum days across all symbols (conservative)
        min_actual_days = min(actual_days_used.values()) if actual_days_used else target_history_days
        trainer.training_days = min_actual_days
        trainer.symbol_history_days = actual_days_used  # Per-symbol history
        
        # Get latest timestamp from all dataframes
        max_timestamp = max(df['timestamp'].max() for df in symbol_dataframes.values())
        trainer.training_end_timestamp = max_timestamp
        trainer.min_history_days_per_symbol = min_history_days
        
    else:
        # Single-symbol training (backward compatible)
        requested_days = min(args.days, target_history_days)
        logger.info(f"Downloading up to {requested_days} days of historical data for {symbol}")
        df = data_collector.download_and_save(
            symbol=symbol,
            days=requested_days,
            interval="60",  # 1 hour
            data_path=config['data']['historical_data_path']
        )
        
        if df.empty:
            logger.error("No data downloaded. Exiting.")
            return 1
        
        # Calculate history metrics
        history_metrics = HistoricalDataCollector.calculate_history_metrics(df, expected_interval_minutes=60)
        available_days = history_metrics['available_days']
        coverage_pct = history_metrics['coverage_pct']
        
        logger.info(f"Downloaded {len(df)} candles: {available_days} days available, {coverage_pct*100:.1f}% coverage")
        
        # Check if symbol meets minimum requirements
        if block_short_history and available_days < min_history_days:
            logger.error(f"Symbol {symbol} has only {available_days} days of history (< {min_history_days} minimum). Cannot train.")
            logger.error("Symbol will remain blocked until it accumulates sufficient history.")
            return 1
        
        if coverage_pct < min_coverage_pct:
            logger.error(f"Symbol {symbol} has {coverage_pct*100:.1f}% coverage (< {min_coverage_pct*100}% required). Cannot train.")
            return 1
        
        # Use actual available days (capped at target)
        actual_days_used = min(available_days, target_history_days)
        if available_days > target_history_days:
            # Use most recent target_history_days
            df = df.sort_values('timestamp').tail(int(target_history_days * 24)).reset_index(drop=True)
            logger.info(f"Using most recent {target_history_days} days (had {available_days} days available)")
        
        logger.info(f"Using {len(df)} candles ({actual_days_used} days)")
        logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        # Prepare single-symbol training data
        logger.info("Preparing training data...")
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
        
        # Store model coverage metadata for single-symbol training
        trainer.trained_symbols = [symbol]
        trainer.training_days = actual_days_used
        trainer.symbol_history_days = {symbol: actual_days_used}
        trainer.training_end_timestamp = df['timestamp'].max()
        trainer.min_history_days_per_symbol = min_history_days
    
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

