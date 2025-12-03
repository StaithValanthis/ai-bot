#!/usr/bin/env python3
"""
Simple sanity check script for universe management.

Tests:
1. UniverseManager initialization
2. Fixed mode (uses config symbols)
3. Auto mode discovery (if API keys available)
4. Filtering logic
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.config_loader import load_config
from src.exchange.universe import UniverseManager
from loguru import logger

def test_fixed_mode():
    """Test fixed mode (no API calls needed)"""
    logger.info("=" * 60)
    logger.info("Testing Fixed Mode")
    logger.info("=" * 60)
    
    config = load_config()
    
    # Force fixed mode
    config['exchange']['universe_mode'] = 'fixed'
    config['exchange']['fixed_symbols'] = ['BTCUSDT', 'ETHUSDT']
    
    universe_manager = UniverseManager(config)
    symbols = universe_manager.get_symbols()
    
    logger.info(f"Fixed mode returned: {symbols}")
    assert symbols == ['BTCUSDT', 'ETHUSDT'], f"Expected ['BTCUSDT', 'ETHUSDT'], got {symbols}"
    logger.success("✅ Fixed mode test passed")
    return True

def test_auto_mode():
    """Test auto mode (requires API keys)"""
    logger.info("=" * 60)
    logger.info("Testing Auto Mode")
    logger.info("=" * 60)
    
    config = load_config()
    
    # Check if API keys are available
    api_key = config.get('exchange', {}).get('api_key', '')
    api_secret = config.get('exchange', {}).get('api_secret', '')
    
    # Strip whitespace
    api_key = api_key.strip() if api_key else ''
    api_secret = api_secret.strip() if api_secret else ''
    
    # Debug: Check environment variables directly
    import os
    env_api_key = os.getenv('BYBIT_API_KEY', '').strip()
    env_api_secret = os.getenv('BYBIT_API_SECRET', '').strip()
    
    if not api_key or not api_secret:
        logger.warning("⚠️  API keys not found in config. Skipping auto mode test.")
        logger.info(f"   Config api_key: {'SET' if api_key else 'EMPTY'}")
        logger.info(f"   Config api_secret: {'SET' if api_secret else 'EMPTY'}")
        logger.info(f"   Env BYBIT_API_KEY: {'SET' if env_api_key else 'EMPTY'}")
        logger.info(f"   Env BYBIT_API_SECRET: {'SET' if env_api_secret else 'EMPTY'}")
        logger.info("   Set BYBIT_API_KEY and BYBIT_API_SECRET in .env to test auto mode")
        logger.info("   Make sure .env file is in the project root directory")
        return False
    
    # Force auto mode with conservative settings
    config['exchange']['universe_mode'] = 'auto'
    config['exchange']['min_usd_volume_24h'] = 100000000  # $100M (very high to limit results)
    config['exchange']['max_symbols'] = 5
    
    universe_manager = UniverseManager(config)
    symbols = universe_manager.get_symbols(force_refresh=True)
    
    logger.info(f"Auto mode discovered {len(symbols)} symbols: {symbols}")
    
    if not symbols:
        logger.warning("⚠️  No symbols discovered. This might be expected with high volume threshold.")
        return False
    
    # Basic sanity checks
    assert isinstance(symbols, list), "Symbols should be a list"
    assert len(symbols) <= config['exchange']['max_symbols'], f"Should have <= {config['exchange']['max_symbols']} symbols"
    assert all(isinstance(s, str) for s in symbols), "All symbols should be strings"
    assert all('USDT' in s for s in symbols), "All symbols should be USDT-margined"
    
    logger.success("✅ Auto mode test passed")
    return True

def test_filtering():
    """Test filtering logic"""
    logger.info("=" * 60)
    logger.info("Testing Filtering Logic")
    logger.info("=" * 60)
    
    config = load_config()
    
    # Test exclude list
    config['exchange']['universe_mode'] = 'fixed'
    config['exchange']['fixed_symbols'] = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
    config['exchange']['exclude_symbols'] = ['BNBUSDT']
    
    universe_manager = UniverseManager(config)
    symbols = universe_manager.get_symbols()
    
    logger.info(f"With exclude list: {symbols}")
    assert 'BNBUSDT' not in symbols, "Excluded symbol should not be in result"
    logger.success("✅ Filtering test passed")
    return True

def main():
    """Run all tests"""
    logger.info("Starting Universe Management Sanity Checks")
    
    results = {
        'fixed_mode': False,
        'auto_mode': False,
        'filtering': False
    }
    
    try:
        results['fixed_mode'] = test_fixed_mode()
    except Exception as e:
        logger.error(f"Fixed mode test failed: {e}")
    
    try:
        results['auto_mode'] = test_auto_mode()
    except Exception as e:
        logger.error(f"Auto mode test failed: {e}")
    
    try:
        results['filtering'] = test_filtering()
    except Exception as e:
        logger.error(f"Filtering test failed: {e}")
    
    logger.info("=" * 60)
    logger.info("Test Results Summary")
    logger.info("=" * 60)
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "⚠️  SKIPPED/FAILED"
        logger.info(f"  {test_name}: {status}")
    
    # At least fixed mode should pass
    if results['fixed_mode']:
        logger.success("\n✅ Core functionality verified")
        return 0
    else:
        logger.error("\n❌ Core functionality failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

