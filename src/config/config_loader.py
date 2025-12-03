"""Configuration loader for the trading bot"""

import os
import sys
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
    # Calculate project root first (where config_loader.py is: src/config/config_loader.py)
    # So project_root = src/config/config_loader.py -> parent -> parent -> parent = repo root
    project_root = Path(__file__).parent.parent.parent
    
    # Load environment variables - try multiple locations
    # First try project root (most likely location), then current directory, then home
    env_loaded = False
    env_paths = [
        project_root / ".env",  # Project root (most likely)
        Path(".env"),  # Current directory
        Path.home() / ".env",  # Home directory (fallback)
    ]
    
    for env_path in env_paths:
        if env_path.exists():
            # Use override=True to ensure env vars from .env take precedence
            load_dotenv(dotenv_path=env_path, override=True)
            env_loaded = True
            # Debug: verify keys are loaded (only log if DEBUG env var is set)
            if os.getenv('DEBUG'):
                api_key = os.getenv('BYBIT_API_KEY', 'NOT_FOUND')
                api_secret = os.getenv('BYBIT_API_SECRET', 'NOT_FOUND')
                print(f"DEBUG: Loaded .env from {env_path}", file=sys.stderr)
                print(f"DEBUG: BYBIT_API_KEY={'SET' if api_key != 'NOT_FOUND' else 'NOT_FOUND'}", file=sys.stderr)
                print(f"DEBUG: BYBIT_API_SECRET={'SET' if api_secret != 'NOT_FOUND' else 'NOT_FOUND'}", file=sys.stderr)
            break
    
    # If no .env file found, still try load_dotenv() which searches automatically
    if not env_loaded:
        load_dotenv(override=True)
    
    # Get absolute path to config file
    config_file = Path(config_path)
    if not config_file.is_absolute():
        # Assume config is relative to project root
        config_file = project_root / config_path
    
    # Load YAML config
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Replace environment variable placeholders
    config = _replace_env_vars(config)
    
    # Replace API keys from environment
    if 'exchange' in config:
        # Get API keys from environment (should be loaded from .env above)
        # Strip whitespace to handle any formatting issues
        env_api_key = os.getenv('BYBIT_API_KEY', '').strip()
        env_api_secret = os.getenv('BYBIT_API_SECRET', '').strip()
        
        # Use environment variables if available, otherwise use config file values
        config['exchange']['api_key'] = env_api_key if env_api_key else config['exchange'].get('api_key', '')
        config['exchange']['api_secret'] = env_api_secret if env_api_secret else config['exchange'].get('api_secret', '')
        
        # Debug output if DEBUG env var is set
        if os.getenv('DEBUG'):
            print(f"DEBUG: Final API key in config: {'SET (length=' + str(len(config['exchange']['api_key'])) + ')' if config['exchange']['api_key'] else 'EMPTY'}", file=sys.stderr)
            print(f"DEBUG: Final API secret in config: {'SET (length=' + str(len(config['exchange']['api_secret'])) + ')' if config['exchange']['api_secret'] else 'EMPTY'}", file=sys.stderr)
        
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

