#!/usr/bin/env python3
"""
Training script for meta-model.

Usage:
    python train_model.py --symbol BTCUSDT --days 730
"""

import argparse
import sys
from pathlib import Path
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config.config_loader import load_config
from src.data.historical_data import HistoricalDataCollector
from src.models.train import ModelTrainer


def main():
    parser = argparse.ArgumentParser(description='Train meta-model for trading bot')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol')
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
    
    # Initialize data collector
    data_collector = HistoricalDataCollector(
        api_key=config['exchange'].get('api_key'),
        api_secret=config['exchange'].get('api_secret'),
        testnet=config['exchange'].get('testnet', True)
    )
    
    # Download historical data
    logger.info(f"Downloading {args.days} days of historical data for {args.symbol}")
    df = data_collector.download_and_save(
        symbol=args.symbol,
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
        symbol=args.symbol,
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

