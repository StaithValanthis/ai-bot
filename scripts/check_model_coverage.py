#!/usr/bin/env python3
"""
Diagnostic script to check model coverage against current universe.

Usage:
    python scripts/check_model_coverage.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
_script_file = Path(__file__).resolve()
_project_root = _script_file.parent.parent
sys.path.insert(0, str(_project_root))

from src.config.config_loader import load_config, get_model_paths
from src.exchange.universe import UniverseManager
from src.signals.meta_predictor import MetaPredictor
from loguru import logger

def main():
    """Check model coverage"""
    logger.info("=" * 60)
    logger.info("Model Coverage Report")
    logger.info("=" * 60)
    
    # Load config
    config = load_config()
    
    # Get universe symbols
    universe_manager = UniverseManager(config)
    universe_symbols = set(universe_manager.get_symbols())
    
    logger.info(f"Universe symbols ({len(universe_symbols)}): {sorted(universe_symbols)}")
    
    # Load model
    try:
        model_paths = get_model_paths(config)
        meta_predictor = MetaPredictor(
            model_path=str(model_paths['model']),
            scaler_path=str(model_paths['scaler']),
            config_path=str(model_paths['config'])
        )
        
        # Get trained symbols
        trained_symbols = set(meta_predictor.trained_symbols)
        training_mode = meta_predictor.training_mode
        training_days = meta_predictor.training_days
        
        logger.info(f"\nModel Information:")
        logger.info(f"  Training mode: {training_mode}")
        logger.info(f"  Training days: {training_days}")
        logger.info(f"  Trained symbols ({len(trained_symbols)}): {sorted(trained_symbols)}")
        
        # Compare
        untrained_symbols = universe_symbols - trained_symbols
        covered_symbols = universe_symbols & trained_symbols
        
        logger.info(f"\nCoverage Analysis:")
        logger.info(f"  Covered: {len(covered_symbols)} symbol(s)")
        logger.info(f"  Untrained: {len(untrained_symbols)} symbol(s)")
        
        if untrained_symbols:
            logger.warning(f"  Untrained symbols: {sorted(untrained_symbols)}")
            
            # Check training queue
            queue_path = Path("data/new_symbol_training_queue.json")
            if queue_path.exists():
                try:
                    with open(queue_path, 'r') as f:
                        queue_data = json.load(f)
                    queued_symbols = set(queue_data.get('queued_symbols', []))
                    logger.info(f"\nTraining Queue:")
                    logger.info(f"  Queued symbols: {sorted(queued_symbols)}")
                    
                    not_queued = untrained_symbols - queued_symbols
                    if not_queued:
                        logger.warning(f"  Not yet queued: {sorted(not_queued)}")
                except Exception as e:
                    logger.error(f"Could not read training queue: {e}")
            else:
                logger.info(f"\nTraining Queue: No queue file found (untrained symbols not yet queued)")
        else:
            logger.success("✅ All universe symbols are covered by the model!")
        
        # Check config settings
        model_config = config.get('model', {})
        auto_train = model_config.get('auto_train_new_symbols', True)
        block_untrained = model_config.get('block_untrained_symbols', True)
        block_short_history = model_config.get('block_short_history_symbols', True)
        target_history_days = model_config.get('target_history_days', 730)
        min_history_days = model_config.get('min_history_days_to_train', 90)
        min_coverage_pct = model_config.get('min_history_coverage_pct', 0.95)
        
        logger.info(f"\nConfiguration:")
        logger.info(f"  auto_train_new_symbols: {auto_train}")
        logger.info(f"  block_untrained_symbols: {block_untrained}")
        logger.info(f"  block_short_history_symbols: {block_short_history}")
        logger.info(f"  target_history_days: {target_history_days}")
        logger.info(f"  min_history_days_to_train: {min_history_days}")
        logger.info(f"  min_history_coverage_pct: {min_coverage_pct*100}%")
        
        # Check history for untrained symbols
        if untrained_symbols:
            logger.info(f"\nHistory Check for Untrained Symbols:")
            from src.data.historical_data import HistoricalDataCollector
            data_collector = HistoricalDataCollector(
                api_key=config['exchange'].get('api_key'),
                api_secret=config['exchange'].get('api_secret'),
                testnet=config['exchange'].get('testnet', True)
            )
            
            for symbol in sorted(untrained_symbols):
                df = data_collector.load_candles(
                    symbol=symbol,
                    timeframe="60",
                    data_path=config['data']['historical_data_path']
                )
                
                if df.empty:
                    logger.warning(f"  {symbol}: No data available")
                else:
                    from src.data.historical_data import HistoricalDataCollector
                    metrics = HistoricalDataCollector.calculate_history_metrics(df, expected_interval_minutes=60)
                    available_days = metrics['available_days']
                    coverage_pct = metrics['coverage_pct']
                    
                    if available_days < min_history_days:
                        logger.warning(f"  {symbol}: {available_days} days (< {min_history_days} minimum) - BLOCKED")
                    elif coverage_pct < min_coverage_pct:
                        logger.warning(f"  {symbol}: {coverage_pct*100:.1f}% coverage (< {min_coverage_pct*100}%) - BLOCKED")
                    else:
                        logger.info(f"  {symbol}: {available_days} days, {coverage_pct*100:.1f}% coverage - ELIGIBLE")
        
        if untrained_symbols and not auto_train:
            logger.warning("⚠️  Auto-training is disabled. Untrained symbols will remain blocked.")
        
        logger.info("=" * 60)
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"Model files not found: {e}")
        logger.error("Please train a model first using: python train_model.py")
        return 1
    except Exception as e:
        logger.error(f"Error checking coverage: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

