#!/usr/bin/env python3
"""
List available models and show which one would be selected.

Usage:
    python scripts/list_models.py [--config config/config.yaml]
"""

import sys
import os
from pathlib import Path

# Add project root to path
_script_file = os.path.abspath(__file__)
_script_dir = os.path.dirname(_script_file)
_project_root = os.path.dirname(_script_dir)

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.config.config_loader import load_config
from src.models.model_registry import list_available_models, select_best_model, get_model_info
from loguru import logger
import argparse


def main():
    parser = argparse.ArgumentParser(description='List available models and show selection')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file path')
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Discover all models
    print("=" * 60)
    print("MODEL DISCOVERY")
    print("=" * 60)
    models = list_available_models()
    
    if not models:
        print("\nNo models found in models/ directory")
        return 0
    
    print(f"\nFound {len(models)} model version(s):\n")
    
    # Show all models
    for i, model in enumerate(models, 1):
        print(f"{i}. Model v{model['version']}")
        print(f"   Files exist: {model['exists']}")
        if model['exists']:
            metadata = model.get('metadata', {})
            print(f"   Training Mode: {metadata.get('training_mode', 'unknown')}")
            print(f"   Symbol Encoding: {metadata.get('symbol_encoding_type', 'unknown')}")
            trained_symbols = metadata.get('trained_symbols', [])
            print(f"   Trained Symbols: {len(trained_symbols)}")
            if trained_symbols:
                symbols_str = ', '.join(sorted(trained_symbols)[:10])
                if len(trained_symbols) > 10:
                    symbols_str += f" ... (+{len(trained_symbols) - 10} more)"
                print(f"      {symbols_str}")
            print(f"   Training Days: {metadata.get('training_days', 'unknown')}")
            print(f"   Training End: {metadata.get('training_end_timestamp', 'unknown')}")
        else:
            missing = []
            if not model.get('model_path') or not model['model_path'].exists():
                missing.append('model')
            if not model.get('scaler_path') or not model['scaler_path'].exists():
                missing.append('scaler')
            if not model.get('config_path') or not model['config_path'].exists():
                missing.append('config')
            print(f"   Missing files: {', '.join(missing)}")
        print()
    
    # Show which model would be selected
    print("=" * 60)
    print("MODEL SELECTION (for current config)")
    print("=" * 60)
    
    required_mode = config.get('model', {}).get('training_mode', 'single_symbol')
    required_encoding = config.get('model', {}).get('symbol_encoding', 'one_hot')
    
    print(f"\nConfig requirements:")
    print(f"  Training Mode: {required_mode}")
    print(f"  Symbol Encoding: {required_encoding}")
    print()
    
    selected = select_best_model(config, models)
    
    if selected:
        print("Selected model:")
        print("-" * 60)
        print(get_model_info(selected))
        print("-" * 60)
    else:
        print("No compatible model found for current config")
        print("Training will be required")
    
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

