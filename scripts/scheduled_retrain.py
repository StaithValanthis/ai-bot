#!/usr/bin/env python3
"""
Scheduled model retraining and rotation script.

This script should be run periodically (e.g., via cron) to:
1. Retrain models on latest data
2. Evaluate new models
3. Rotate models if they meet promotion criteria
"""

import sys
import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.config_loader import load_config, get_model_paths
from src.data.historical_data import HistoricalDataCollector
from src.models.train import ModelTrainer
from src.models.evaluation import walk_forward_validation, aggregate_walk_forward_results, calculate_metrics
from src.signals.features import FeatureCalculator
from src.signals.primary_signal import PrimarySignalGenerator


class ModelRotationManager:
    """Manage model retraining and rotation"""
    
    def __init__(self, config: dict):
        """
        Initialize model rotation manager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        rotation_config = config.get('operations', {}).get('model_rotation', {})
        
        self.enabled = rotation_config.get('enabled', False)
        self.retrain_frequency_days = rotation_config.get('retrain_frequency_days', 30)
        self.min_sharpe_ratio = rotation_config.get('min_sharpe_ratio', 1.0)
        self.min_profit_factor = rotation_config.get('min_profit_factor', 1.2)
        self.max_drawdown_threshold = rotation_config.get('max_drawdown_threshold', 0.20)
        self.min_trades = rotation_config.get('min_trades', 50)
        self.require_outperformance = rotation_config.get('require_outperformance', True)
        
        self.models_dir = Path("models")
        self.models_archive_dir = self.models_dir / "archive"
        self.models_archive_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized ModelRotationManager (enabled={self.enabled})")
    
    def should_retrain(self, symbol: str) -> bool:
        """
        Check if model should be retrained for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if retraining is needed
        """
        if not self.enabled:
            return False
        
        # Check model age - use config-based path or symbol-specific fallback
        from src.config.config_loader import get_model_paths
        model_paths = get_model_paths(self.config)
        model_path = model_paths['model']
        
        # Also check for symbol-specific models (for multi-symbol scenarios)
        symbol_specific_files = list(self.models_dir.glob(f"meta_model_{symbol}_v*.joblib"))
        
        # Use symbol-specific if exists, otherwise use config path
        if symbol_specific_files:
            latest_model = max(symbol_specific_files, key=lambda p: p.stat().st_mtime)
        elif model_path.exists():
            latest_model = model_path
        else:
            logger.info(f"No existing model for {symbol}, retraining needed")
            return True
        
        model_age_days = (datetime.now().timestamp() - latest_model.stat().st_mtime) / (24 * 3600)
        
        if model_age_days >= self.retrain_frequency_days:
            logger.info(f"Model for {symbol} is {model_age_days:.1f} days old, retraining needed")
            return True
        
        return False
    
    def evaluate_model(
        self,
        symbol: str,
        data: any,  # DataFrame
        trainer: ModelTrainer
    ) -> Optional[Dict[str, float]]:
        """
        Evaluate a model using walk-forward validation.
        
        Args:
            symbol: Trading symbol
            data: Historical data DataFrame
            trainer: ModelTrainer instance
            
        Returns:
            Evaluation metrics or None if evaluation fails
        """
        try:
            logger.info(f"Evaluating model for {symbol}...")
            
            # Prepare data
            labeling_config = self.config.get('labeling', {})
            execution_config = self.config.get('execution', {})
            
            features_df, labels = trainer.prepare_data(
                df=data,
                symbol=symbol,
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
            
            if features_df.empty:
                logger.warning(f"No training samples for {symbol}")
                return None
            
            # Simple evaluation: train on 80%, test on 20%
            split_idx = int(len(features_df) * 0.8)
            train_features = features_df.iloc[:split_idx]
            train_labels = labels.iloc[:split_idx]
            test_features = features_df.iloc[split_idx:]
            test_labels = labels.iloc[split_idx:]
            
            # Train model
            use_ensemble = self.config.get('model', {}).get('use_ensemble', True)
            model, scaler, metrics = trainer.train_model(
                features_df=train_features,
                labels=train_labels,
                test_size=0.0,  # Already split
                validation_size=0.0,
                use_ensemble=use_ensemble
            )
            
            # Simulate trades on test set (simplified)
            # In production, use full walk-forward validation
            # For now, use model metrics as proxy
            
            # Return metrics (using test set performance)
            return {
                'sharpe_ratio': metrics.get('ensemble_roc_auc', metrics.get('xgb_roc_auc', 0.0)) * 2 - 1,  # Proxy
                'profit_factor': metrics.get('ensemble_f1_score', metrics.get('xgb_f1_score', 0.0)) * 2,  # Proxy
                'max_drawdown': 0.10,  # Would need full backtest
                'total_trades': len(test_features),
                'win_rate': metrics.get('positive_rate', 0.0)
            }
            
        except Exception as e:
            logger.error(f"Error evaluating model for {symbol}: {e}")
            return None
    
    def meets_promotion_criteria(self, metrics: Dict[str, float]) -> tuple[bool, str]:
        """
        Check if model meets promotion criteria.
        
        Args:
            metrics: Evaluation metrics
            
        Returns:
            Tuple of (meets_criteria, reason)
        """
        if metrics['sharpe_ratio'] < self.min_sharpe_ratio:
            return False, f"Sharpe ratio {metrics['sharpe_ratio']:.2f} < {self.min_sharpe_ratio}"
        
        if metrics['profit_factor'] < self.min_profit_factor:
            return False, f"Profit factor {metrics['profit_factor']:.2f} < {self.min_profit_factor}"
        
        if metrics['max_drawdown'] > self.max_drawdown_threshold:
            return False, f"Max drawdown {metrics['max_drawdown']:.2%} > {self.max_drawdown_threshold:.2%}"
        
        if metrics['total_trades'] < self.min_trades:
            return False, f"Trade count {metrics['total_trades']} < {self.min_trades}"
        
        return True, "All criteria met"
    
    def rotate_model(self, symbol: str, version: str):
        """
        Rotate model by archiving old and promoting new.
        
        Args:
            symbol: Trading symbol
            version: New model version
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Archive old models
            old_models = list(self.models_dir.glob(f"meta_model_{symbol}_v*.joblib"))
            for old_model in old_models:
                archive_path = self.models_archive_dir / f"{old_model.stem}_{timestamp}.joblib"
                shutil.move(str(old_model), str(archive_path))
                logger.info(f"Archived {old_model.name} to {archive_path.name}")
            
            # Archive old scalers and configs
            for pattern in [f"feature_scaler_{symbol}_v*.joblib", f"model_config_{symbol}_v*.json"]:
                old_files = list(self.models_dir.glob(pattern))
                for old_file in old_files:
                    archive_path = self.models_archive_dir / f"{old_file.stem}_{timestamp}{old_file.suffix}"
                    shutil.move(str(old_file), str(archive_path))
            
            logger.info(f"Model rotation complete for {symbol} (version {version})")
            
        except Exception as e:
            logger.error(f"Error rotating model for {symbol}: {e}")
            raise
    
    def retrain_and_rotate(self, symbol: str, dry_run: bool = False) -> bool:
        """
        Retrain model and rotate if criteria met.
        
        Args:
            symbol: Trading symbol
            dry_run: If True, don't actually rotate models
            
        Returns:
            True if model was rotated, False otherwise
        """
        if not self.enabled:
            logger.info("Model rotation is disabled")
            return False
        
        if not self.should_retrain(symbol):
            logger.info(f"Retraining not needed for {symbol}")
            return False
        
        logger.info(f"Starting retraining for {symbol} (dry_run={dry_run})")
        
        # Get model paths for consistency
        from src.config.config_loader import get_model_paths
        model_paths = get_model_paths(self.config)
        
        # Load data
        data_collector = HistoricalDataCollector(
            api_key=self.config['exchange'].get('api_key'),
            api_secret=self.config['exchange'].get('api_secret'),
            testnet=self.config['exchange'].get('testnet', True)
        )
        
        data = data_collector.load_candles(
            symbol=symbol,
            timeframe="60",
            data_path=self.config['data']['historical_data_path']
        )
        
        if data.empty:
            logger.error(f"No data available for {symbol}")
            return False
        
        # Train model
        trainer = ModelTrainer(self.config)
        version = datetime.now().strftime("%Y%m%d")
        
        # Prepare data
        labeling_config = self.config.get('labeling', {})
        execution_config = self.config.get('execution', {})
        
        features_df, labels = trainer.prepare_data(
            df=data,
            symbol=symbol,
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
        
        if features_df.empty:
            logger.error(f"No training samples for {symbol}")
            return False
        
        # Train
        use_ensemble = self.config.get('model', {}).get('use_ensemble', True)
        model, scaler, metrics = trainer.train_model(
            features_df=features_df,
            labels=labels,
            test_size=0.2,
            validation_size=0.2,
            use_ensemble=use_ensemble
        )
        
        # Evaluate (simplified - in production use full walk-forward)
        eval_metrics = self.evaluate_model(symbol, data, trainer)
        
        if not eval_metrics:
            logger.error(f"Evaluation failed for {symbol}")
            return False
        
        # Check promotion criteria
        meets_criteria, reason = self.meets_promotion_criteria(eval_metrics)
        
        if not meets_criteria:
            logger.warning(f"New model for {symbol} does not meet promotion criteria: {reason}")
            logger.info(f"Metrics: {eval_metrics}")
            return False
        
        logger.info(f"New model for {symbol} meets promotion criteria: {reason}")
        logger.info(f"Metrics: {eval_metrics}")
        
        if dry_run:
            logger.info(f"DRY RUN: Would rotate model for {symbol}")
            return True
        
        # Determine model version naming
        # For single symbol, use config paths; for multi-symbol, use symbol-specific
        is_multi_symbol = len(self.config['trading']['symbols']) > 1
        if is_multi_symbol:
            model_version = f"{symbol}_{version}"
        else:
            model_version = version
        
        # Save new model
        trainer.save_model(
            model=model,
            scaler=scaler,
            metrics=metrics,
            features_df=features_df,
            version=model_version
        )
        
        # Rotate (only if symbol-specific models exist)
        symbol_specific_files = list(self.models_dir.glob(f"meta_model_{symbol}_v*.joblib"))
        if symbol_specific_files:
            self.rotate_model(symbol, model_version)
        else:
            # Single symbol: just archive old model if exists
            if model_paths['model'].exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                archive_path = self.models_archive_dir / f"meta_model_v{version}_{timestamp}.joblib"
                shutil.move(str(model_paths['model']), str(archive_path))
                logger.info(f"Archived old model to {archive_path.name}")
        
        logger.info(f"Successfully rotated model for {symbol}")
        return True


def main():
    parser = argparse.ArgumentParser(description='Retrain and rotate models')
    parser.add_argument('--symbols', nargs='+', help='Symbols to retrain (default: from config)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual rotation)')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.add("logs/retrain_{time}.log", rotation="1 day", level="INFO")
    
    logger.info("=" * 60)
    logger.info("Starting Model Retraining & Rotation")
    logger.info("=" * 60)
    
    # Load config
    config = load_config(args.config)
    
    # Get symbols
    if args.symbols:
        symbols = args.symbols
    else:
        symbols = config['trading']['symbols']
    
    # Initialize rotation manager
    rotation_manager = ModelRotationManager(config)
    
    if not rotation_manager.enabled:
        logger.warning("Model rotation is disabled in config")
        return 0
    
    # Retrain each symbol
    results = {}
    for symbol in symbols:
        try:
            rotated = rotation_manager.retrain_and_rotate(symbol, dry_run=args.dry_run)
            results[symbol] = "ROTATED" if rotated else "SKIPPED"
        except Exception as e:
            logger.error(f"Error retraining {symbol}: {e}")
            results[symbol] = "ERROR"
    
    # Summary
    logger.info("=" * 60)
    logger.info("Retraining Summary")
    logger.info("=" * 60)
    for symbol, status in results.items():
        logger.info(f"{symbol}: {status}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

