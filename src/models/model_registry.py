"""
Model Registry - Discovery and Selection

This module provides functionality to discover available trained models
and select the best one based on configuration requirements.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger


def list_available_models(models_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Scan models directory for available model artifacts.
    
    Discovers:
    - meta_model_v*.joblib (model files)
    - feature_scaler_v*.joblib (scaler files)
    - model_config_v*.json (config/metadata files)
    
    Groups them by version and returns metadata.
    
    Args:
        models_dir: Path to models directory (default: project_root/models)
        
    Returns:
        List of model dictionaries, each containing:
        - version: Version string (e.g., "1.0")
        - model_path: Path to model file
        - scaler_path: Path to scaler file
        - config_path: Path to config file
        - metadata: Dictionary with training_mode, symbol_encoding_type, trained_symbols, etc.
        - exists: Whether all required files exist
    """
    if models_dir is None:
        # Default to project_root/models
        project_root = Path(__file__).parent.parent.parent
        models_dir = project_root / "models"
    
    if not models_dir.exists():
        logger.debug(f"Models directory does not exist: {models_dir}")
        return []
    
    models_dir.mkdir(exist_ok=True)
    
    # Find all model files
    model_files = list(models_dir.glob("meta_model_v*.joblib"))
    scaler_files = list(models_dir.glob("feature_scaler_v*.joblib"))
    config_files = list(models_dir.glob("model_config_v*.json"))
    
    # Extract versions and group by version
    version_pattern = re.compile(r'v(\d+\.\d+)')
    models_by_version = {}
    
    # Process model files
    for model_file in model_files:
        match = version_pattern.search(model_file.name)
        if match:
            version = match.group(1)
            if version not in models_by_version:
                models_by_version[version] = {
                    'version': version,
                    'model_path': None,
                    'scaler_path': None,
                    'config_path': None,
                    'metadata': {},
                    'exists': False
                }
            models_by_version[version]['model_path'] = model_file
    
    # Process scaler files
    for scaler_file in scaler_files:
        match = version_pattern.search(scaler_file.name)
        if match:
            version = match.group(1)
            if version not in models_by_version:
                models_by_version[version] = {
                    'version': version,
                    'model_path': None,
                    'scaler_path': None,
                    'config_path': None,
                    'metadata': {},
                    'exists': False
                }
            models_by_version[version]['scaler_path'] = scaler_file
    
    # Process config files and load metadata
    for config_file in config_files:
        match = version_pattern.search(config_file.name)
        if match:
            version = match.group(1)
            if version not in models_by_version:
                models_by_version[version] = {
                    'version': version,
                    'model_path': None,
                    'scaler_path': None,
                    'config_path': None,
                    'metadata': {},
                    'exists': False
                }
            models_by_version[version]['config_path'] = config_file
            
            # Load metadata from config file
            try:
                with open(config_file, 'r') as f:
                    metadata = json.load(f)
                models_by_version[version]['metadata'] = metadata
            except Exception as e:
                logger.warning(f"Could not load metadata from {config_file}: {e}")
    
    # Check if all required files exist for each version
    models = []
    for version, model_info in models_by_version.items():
        model_info['exists'] = (
            model_info['model_path'] is not None and
            model_info['model_path'].exists() and
            model_info['scaler_path'] is not None and
            model_info['scaler_path'].exists() and
            model_info['config_path'] is not None and
            model_info['config_path'].exists()
        )
        models.append(model_info)
    
    # Sort by version (newest first)
    models.sort(key=lambda x: _version_key(x['version']), reverse=True)
    
    logger.debug(f"Discovered {len(models)} model version(s) in {models_dir}")
    return models


def _version_key(version_str: str) -> tuple:
    """Convert version string to tuple for sorting (e.g., '1.0' -> (1, 0))"""
    try:
        parts = version_str.split('.')
        return tuple(int(p) for p in parts)
    except:
        return (0, 0)


def select_best_model(
    config: Dict[str, Any],
    models: Optional[List[Dict[str, Any]]] = None,
    models_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Select the best model that matches current configuration requirements.
    
    Selection criteria (in order):
    1. Model must exist (all files present)
    2. training_mode must match (single_symbol vs multi_symbol)
    3. symbol_encoding_type must match (if multi_symbol mode)
    4. Prefer models with more trained_symbols coverage
    5. Prefer newer training_end_timestamp
    6. Prefer higher version number
    
    Args:
        config: Current configuration dictionary
        models: Optional pre-discovered models list (if None, will discover)
        models_dir: Optional models directory path
        
    Returns:
        Best matching model dictionary, or None if no compatible model found
    """
    if models is None:
        models = list_available_models(models_dir)
    
    if not models:
        logger.debug("No models available for selection")
        return None
    
    # Get config requirements
    model_config = config.get('model', {})
    required_training_mode = model_config.get('training_mode', 'single_symbol')
    required_symbol_encoding = model_config.get('symbol_encoding', 'one_hot')
    
    # Filter to compatible models
    compatible_models = []
    
    for model in models:
        if not model['exists']:
            logger.debug(f"Model v{model['version']} is incomplete (missing files), skipping")
            continue
        
        metadata = model.get('metadata', {})
        model_training_mode = metadata.get('training_mode', 'single_symbol')
        model_symbol_encoding = metadata.get('symbol_encoding_type', 'one_hot')
        
        # Check training_mode match
        if model_training_mode != required_training_mode:
            logger.debug(
                f"Model v{model['version']} training_mode mismatch: "
                f"{model_training_mode} != {required_training_mode}"
            )
            continue
        
        # Check symbol_encoding match (only relevant for multi_symbol)
        if required_training_mode == 'multi_symbol':
            if model_symbol_encoding != required_symbol_encoding:
                logger.debug(
                    f"Model v{model['version']} symbol_encoding mismatch: "
                    f"{model_symbol_encoding} != {required_symbol_encoding}"
                )
                continue
        
        compatible_models.append(model)
    
    if not compatible_models:
        logger.debug("No compatible models found")
        return None
    
    # Score and rank compatible models
    # Higher score = better match
    scored_models = []
    
    for model in compatible_models:
        metadata = model.get('metadata', {})
        score = 0
        
        # Prefer models with more trained symbols
        trained_symbols = metadata.get('trained_symbols', [])
        score += len(trained_symbols) * 10
        
        # Prefer newer training_end_timestamp
        training_end = metadata.get('training_end_timestamp')
        if training_end:
            try:
                # Parse ISO timestamp
                if isinstance(training_end, str):
                    end_dt = datetime.fromisoformat(training_end.replace('Z', '+00:00'))
                else:
                    end_dt = training_end
                # Score based on days since training (more recent = higher score)
                days_ago = (datetime.now(end_dt.tzinfo if hasattr(end_dt, 'tzinfo') else None) - end_dt).days
                score += max(0, 365 - days_ago)  # Up to 365 points for recency
            except Exception as e:
                logger.debug(f"Could not parse training_end_timestamp: {e}")
        
        # Prefer higher version number
        version_key = _version_key(model['version'])
        score += version_key[0] * 100 + version_key[1]  # Major * 100 + minor
        
        scored_models.append((score, model))
    
    # Sort by score (highest first)
    scored_models.sort(key=lambda x: x[0], reverse=True)
    
    best_model = scored_models[0][1]
    logger.info(
        f"Selected model v{best_model['version']} "
        f"(training_mode={best_model['metadata'].get('training_mode')}, "
        f"symbols={len(best_model['metadata'].get('trained_symbols', []))}, "
        f"score={scored_models[0][0]})"
    )
    
    return best_model


def get_model_info(model: Dict[str, Any]) -> str:
    """
    Get a human-readable summary of a model.
    
    Args:
        model: Model dictionary from list_available_models or select_best_model
        
    Returns:
        Formatted string with model information
    """
    metadata = model.get('metadata', {})
    trained_symbols = metadata.get('trained_symbols', [])
    training_end = metadata.get('training_end_timestamp', 'Unknown')
    
    info_lines = [
        f"Version: {model['version']}",
        f"Training Mode: {metadata.get('training_mode', 'unknown')}",
        f"Symbol Encoding: {metadata.get('symbol_encoding_type', 'unknown')}",
        f"Trained Symbols: {len(trained_symbols)} ({', '.join(sorted(trained_symbols)[:5])}{'...' if len(trained_symbols) > 5 else ''})",
        f"Training Days: {metadata.get('training_days', 'unknown')}",
        f"Training End: {training_end}",
        f"Files Exist: {model['exists']}",
    ]
    
    if metadata.get('performance'):
        perf = metadata['performance']
        # Format performance metrics, handling both numeric and string values
        def format_metric(value, default='N/A'):
            if value == default or value is None:
                return default
            try:
                return f"{float(value):.3f}"
            except (ValueError, TypeError):
                return str(value)
        
        precision = format_metric(perf.get('precision'), 'N/A')
        recall = format_metric(perf.get('recall'), 'N/A')
        f1 = format_metric(perf.get('f1'), 'N/A')
        auc = format_metric(perf.get('auc'), 'N/A')
        
        info_lines.append(f"Performance: Precision={precision}, "
                         f"Recall={recall}, "
                         f"F1={f1}, "
                         f"AUC={auc}")
    
    return "\n".join(info_lines)

