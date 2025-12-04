#!/usr/bin/env python3
"""
Process the new symbol training queue.

This script reads symbols from data/new_symbol_training_queue.json and trains them.
"""

import sys
import json
import subprocess
from pathlib import Path
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.config_loader import load_config


def main():
    """Process training queue"""
    queue_path = Path("data/new_symbol_training_queue.json")
    
    if not queue_path.exists():
        logger.info("No training queue found. Nothing to process.")
        return 0
    
    # Load queue
    try:
        with open(queue_path, 'r') as f:
            queue = json.load(f)
    except Exception as e:
        logger.error(f"Could not load training queue: {e}")
        return 1
    
    queued_symbols = queue.get('queued_symbols', [])
    
    if not queued_symbols:
        logger.info("Training queue is empty. Nothing to process.")
        return 0
    
    logger.info(f"Found {len(queued_symbols)} symbol(s) in training queue: {queued_symbols}")
    
    # Load config to get training settings
    config = load_config()
    target_history_days = config.get('model', {}).get('target_history_days', 730)
    training_mode = config.get('model', {}).get('training_mode', 'single_symbol')
    
    # Process each symbol
    results = {}
    for symbol in queued_symbols:
        logger.info(f"=" * 60)
        logger.info(f"Training {symbol}...")
        logger.info(f"=" * 60)
        
        try:
            # Run train_model.py for this symbol
            cmd = [
                sys.executable,
                'train_model.py',
                '--symbol', symbol,
                '--days', str(target_history_days),
                '--config', 'config/config.yaml'
            ]
            
            result = subprocess.run(cmd, capture_output=False, text=True)
            
            if result.returncode == 0:
                logger.info(f"✓ {symbol} trained successfully")
                results[symbol] = "SUCCESS"
            else:
                logger.error(f"✗ {symbol} training failed (exit code: {result.returncode})")
                results[symbol] = "FAILED"
        
        except Exception as e:
            logger.error(f"✗ Error training {symbol}: {e}")
            results[symbol] = "ERROR"
    
    # Summary
    logger.info("=" * 60)
    logger.info("Training Queue Processing Summary")
    logger.info("=" * 60)
    for symbol, status in results.items():
        logger.info(f"{symbol}: {status}")
    
    # Remove successfully trained symbols from queue
    successful_symbols = [s for s, status in results.items() if status == "SUCCESS"]
    if successful_symbols:
        remaining_symbols = [s for s in queued_symbols if s not in successful_symbols]
        queue['queued_symbols'] = remaining_symbols
        
        # Remove from queued_at as well
        for symbol in successful_symbols:
            queue['queued_at'].pop(symbol, None)
        
        try:
            with open(queue_path, 'w') as f:
                json.dump(queue, f, indent=2)
            logger.info(f"Removed {len(successful_symbols)} successfully trained symbol(s) from queue")
            logger.info(f"Remaining in queue: {remaining_symbols}")
        except Exception as e:
            logger.warning(f"Could not update queue file: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

