"""Configuration loader for the trading bot"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file and environment variables.
    
    Args:
        config_path: Path to the configuration YAML file
        
    Returns:
        Dictionary containing configuration values
    """
    # Load environment variables
    load_dotenv()
    
    # Get absolute path to config file
    config_file = Path(config_path)
    if not config_file.is_absolute():
        # Assume config is relative to project root
        project_root = Path(__file__).parent.parent.parent
        config_file = project_root / config_path
    
    # Load YAML config
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Replace environment variable placeholders
    config = _replace_env_vars(config)
    
    # Replace API keys from environment
    if 'exchange' in config:
        config['exchange']['api_key'] = os.getenv(
            'BYBIT_API_KEY', 
            config['exchange'].get('api_key', '')
        )
        config['exchange']['api_secret'] = os.getenv(
            'BYBIT_API_SECRET',
            config['exchange'].get('api_secret', '')
        )
        
        # Support BYBIT_TESTNET environment variable
        testnet_env = os.getenv('BYBIT_TESTNET')
        if testnet_env is not None:
            config['exchange']['testnet'] = testnet_env.lower() in ('true', '1', 'yes')
    
    # Support DEFAULT_PROFILE environment variable (for scripts)
    default_profile = os.getenv('DEFAULT_PROFILE')
    if default_profile and 'profile' in default_profile:
        # Note: Profile selection is handled at runtime, not in config loader
        # This env var is available for scripts that need it
        pass
    
    # Support DISCORD_WEBHOOK_URL environment variable
    discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
    if discord_webhook and 'operations' in config:
        if 'alerts' not in config['operations']:
            config['operations']['alerts'] = {}
        if not config['operations']['alerts'].get('discord_webhook_url'):
            config['operations']['alerts']['discord_webhook_url'] = discord_webhook
    
    return config


def _replace_env_vars(obj: Any) -> Any:
    """Recursively replace environment variable placeholders in config."""
    if isinstance(obj, dict):
        return {k: _replace_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_env_vars(item) for item in obj]
    elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        # Extract environment variable name
        env_var = obj[2:-1]
        return os.getenv(env_var, obj)
    else:
        return obj


def get_model_paths(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Get model file paths from config.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Dictionary with model paths
    """
    model_config = config.get('model', {})
    project_root = Path(__file__).parent.parent.parent
    
    return {
        'model': project_root / model_config.get('path', 'models/meta_model_v1.0.joblib'),
        'scaler': project_root / model_config.get('scaler_path', 'models/feature_scaler_v1.0.joblib'),
        'config': project_root / model_config.get('config_path', 'models/model_config_v1.0.json'),
    }

