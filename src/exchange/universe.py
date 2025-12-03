"""Universe discovery and filtering for Bybit trading instruments"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
from loguru import logger


class UniverseManager:
    """
    Discovers and filters tradable symbols from Bybit.
    
    Fetches USDT-margined perpetual futures, applies liquidity/price filters,
    and maintains a cached universe for efficient reuse.
    """
    
    def __init__(self, config: dict):
        """
        Initialize universe manager.
        
        Args:
            config: Configuration dictionary with exchange and universe settings
        """
        exchange_config = config.get('exchange', {})
        self.testnet = exchange_config.get('testnet', True)
        self.api_key = exchange_config.get('api_key')
        self.api_secret = exchange_config.get('api_secret')
        
        # Universe settings
        self.universe_mode = exchange_config.get('universe_mode', 'fixed')  # 'auto' or 'fixed'
        self.fixed_symbols = exchange_config.get('fixed_symbols', [])
        
        # Filter settings
        self.min_usd_volume_24h = exchange_config.get('min_usd_volume_24h', 50000000)  # $50M default
        self.min_price = exchange_config.get('min_price', 0.05)  # $0.05 minimum
        self.max_symbols = exchange_config.get('max_symbols', 30)  # Max symbols to return
        
        # Whitelist/blacklist
        self.include_symbols = set(exchange_config.get('include_symbols', []))
        self.exclude_symbols = set(exchange_config.get('exclude_symbols', []))
        
        # Caching
        self.cache_path = Path("data/universe_cache.json")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.universe_refresh_minutes = exchange_config.get('universe_refresh_minutes', 60)
        
        # Initialize Bybit session
        self.session = HTTP(
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        
        logger.info(
            f"Initialized UniverseManager (mode={self.universe_mode}, "
            f"min_volume=${self.min_usd_volume_24h:,.0f}, max_symbols={self.max_symbols})"
        )
    
    def get_symbols(self, force_refresh: bool = False) -> List[str]:
        """
        Get the filtered list of tradable symbols.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data
            
        Returns:
            List of symbol strings (e.g., ["BTCUSDT", "ETHUSDT", ...])
        """
        # Fixed mode: return fixed symbols or config symbols
        if self.universe_mode == 'fixed':
            if self.fixed_symbols:
                symbols = self.fixed_symbols.copy()
            else:
                # Fallback to config trading.symbols if fixed_symbols not set
                from src.config.config_loader import load_config
                config = load_config()
                symbols = config.get('trading', {}).get('symbols', [])
            
            # Apply whitelist/blacklist even in fixed mode
            if self.include_symbols:
                symbols = list(set(symbols) | self.include_symbols)
            if self.exclude_symbols:
                symbols = [s for s in symbols if s not in self.exclude_symbols]
            
            logger.info(f"Fixed mode: returning {len(symbols)} symbols: {symbols}")
            return symbols
        
        # Auto mode: discover and filter
        cached_universe = self._load_cached_universe()
        
        if cached_universe and not force_refresh:
            cache_age_minutes = (datetime.utcnow() - cached_universe['timestamp']).total_seconds() / 60
            if cache_age_minutes < self.universe_refresh_minutes:
                logger.info(f"Using cached universe (age: {cache_age_minutes:.1f} minutes)")
                return cached_universe['symbols']
        
        # Fetch fresh universe
        logger.info("Fetching fresh universe from Bybit...")
        universe_data = self._discover_universe()
        
        if not universe_data:
            # Fallback to cache if fetch fails
            if cached_universe:
                logger.warning("Universe fetch failed, using stale cache")
                return cached_universe['symbols']
            # Last resort: fallback to fixed symbols
            logger.error("Universe fetch failed and no cache available, falling back to fixed symbols")
            return self.fixed_symbols or ["BTCUSDT", "ETHUSDT"]
        
        # Fetch ticker data for filtering
        candidate_symbols = [inst['symbol'] for inst in universe_data if inst.get('status') == 'Trading']
        ticker_data = self._get_ticker_data(candidate_symbols)
        
        # Filter universe
        filtered_symbols = self._filter_universe(universe_data, ticker_data)
        
        # Cache the result
        self._save_cached_universe(filtered_symbols, universe_data)
        
        return filtered_symbols
    
    def _discover_universe(self) -> Optional[List[Dict]]:
        """
        Discover all USDT-margined perpetual futures from Bybit.
        
        Returns:
            List of symbol dictionaries with metadata, or None on error
        """
        try:
            # Fetch all instruments
            response = self.session.get_instruments_info(
                category="linear"
            )
            
            if response.get('retCode') != 0:
                logger.error(f"Error fetching instruments: {response.get('retMsg', 'Unknown error')}")
                return None
            
            instruments = response.get('result', {}).get('list', [])
            
            # Filter for USDT-margined perpetuals
            usdt_perps = []
            for inst in instruments:
                # Bybit API: quoteCoin indicates margin currency, contractType indicates perpetual
                # For linear perps, quoteCoin='USDT' means USDT-margined
                quote_coin = inst.get('quoteCoin', '')
                contract_type = inst.get('contractType', '')
                
                # Check if USDT-margined perpetual
                # Note: contractType may be 'LinearPerpetual' or just checking category='linear' is sufficient
                if quote_coin == 'USDT':
                    # Additional check: ensure it's a perpetual (not a futures contract)
                    # In Bybit, linear category with USDT quoteCoin = USDT-margined perpetual
                    usdt_perps.append({
                        'symbol': inst.get('symbol'),
                        'baseCoin': inst.get('baseCoin'),
                        'quoteCoin': quote_coin,
                        'status': inst.get('status', 'Unknown'),
                        'minPrice': float(inst.get('minPrice', 0)),
                        'maxPrice': float(inst.get('maxPrice', 0)),
                        'tickSize': float(inst.get('tickSize', 0)),
                        'lotSizeFilter': inst.get('lotSizeFilter', {}),
                    })
            
            logger.info(f"Discovered {len(usdt_perps)} USDT-margined perpetuals")
            return usdt_perps
            
        except Exception as e:
            logger.error(f"Error discovering universe: {e}")
            return None
    
    def _get_ticker_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch ticker data (price, volume) for symbols.
        
        Args:
            symbols: List of symbol strings
            
        Returns:
            Dictionary mapping symbol to ticker data
        """
        ticker_data = {}
        
        try:
            # Fetch tickers (can batch multiple symbols)
            # Bybit API allows fetching all tickers at once if symbol is not specified
            # For large symbol lists, fetch all tickers and filter
            if len(symbols) <= 200:
                # Batch request for specific symbols
                response = self.session.get_tickers(
                    category="linear",
                    symbol=",".join(symbols)
                )
            else:
                # Fetch all tickers and filter
                response = self.session.get_tickers(category="linear")
            
            if response.get('retCode') != 0:
                logger.warning(f"Error fetching tickers: {response.get('retMsg', 'Unknown error')}")
                return ticker_data
            
            tickers = response.get('result', {}).get('list', [])
            
            for ticker in tickers:
                symbol = ticker.get('symbol')
                if symbol and symbol in symbols:  # Only include requested symbols
                    ticker_data[symbol] = {
                        'last_price': float(ticker.get('lastPrice', 0)),
                        'volume_24h': float(ticker.get('volume24h', 0)),
                        'turnover_24h': float(ticker.get('turnover24h', 0)),  # USD volume (24h turnover)
                    }
            
            logger.info(f"Fetched ticker data for {len(ticker_data)} symbols")
            
        except Exception as e:
            logger.error(f"Error fetching ticker data: {e}")
        
        return ticker_data
    
    def _filter_universe(
        self, 
        universe_data: List[Dict],
        ticker_data: Optional[Dict[str, Dict]] = None
    ) -> List[str]:
        """
        Filter universe based on liquidity, price, and other criteria.
        
        Args:
            universe_data: List of instrument dictionaries
            ticker_data: Optional pre-fetched ticker data
            
        Returns:
            Filtered list of symbol strings
        """
        if not universe_data:
            return []
        
        # Extract symbols from universe data
        candidate_symbols = [inst['symbol'] for inst in universe_data if inst.get('status') == 'Trading']
        
        # Fetch ticker data if not provided
        if ticker_data is None:
            # Fetch in batches to avoid rate limits
            ticker_data = {}
            batch_size = 200
            for i in range(0, len(candidate_symbols), batch_size):
                batch = candidate_symbols[i:i+batch_size]
                batch_tickers = self._get_ticker_data(batch)
                ticker_data.update(batch_tickers)
                # Small delay between batches
                if i + batch_size < len(candidate_symbols):
                    time.sleep(0.1)
        
        filtered = []
        filtered_out = {
            'low_volume': [],
            'low_price': [],
            'excluded': [],
            'no_ticker': []
        }
        
        for inst in universe_data:
            symbol = inst.get('symbol')
            if not symbol or inst.get('status') != 'Trading':
                continue
            
            # Check blacklist
            if symbol in self.exclude_symbols:
                filtered_out['excluded'].append(symbol)
                continue
            
            # Get ticker data
            ticker = ticker_data.get(symbol)
            if not ticker:
                filtered_out['no_ticker'].append(symbol)
                continue
            
            # Check volume (use turnover_24h which is in USD)
            volume_usd = ticker.get('turnover_24h', 0)
            if volume_usd < self.min_usd_volume_24h:
                filtered_out['low_volume'].append(symbol)
                continue
            
            # Check price
            last_price = ticker.get('last_price', 0)
            if last_price < self.min_price:
                filtered_out['low_price'].append(symbol)
                continue
            
            # Passed all filters
            filtered.append({
                'symbol': symbol,
                'volume_24h': volume_usd,
                'price': last_price
            })
        
        # Sort by volume (descending)
        filtered.sort(key=lambda x: x['volume_24h'], reverse=True)
        
        # Extract symbols
        filtered_symbols = [item['symbol'] for item in filtered]
        
        # Apply whitelist (add even if below thresholds, but warn)
        for symbol in self.include_symbols:
            if symbol not in filtered_symbols:
                # Check if symbol exists in universe
                if any(inst['symbol'] == symbol for inst in universe_data):
                    filtered_symbols.insert(0, symbol)  # Add to front
                    logger.warning(
                        f"Including {symbol} from whitelist "
                        f"(may be below volume/price thresholds)"
                    )
                else:
                    logger.warning(f"Whitelisted symbol {symbol} not found in universe")
        
        # Clip to max_symbols
        if len(filtered_symbols) > self.max_symbols:
            logger.info(
                f"Clipping universe from {len(filtered_symbols)} to {self.max_symbols} symbols "
                f"(keeping top {self.max_symbols} by volume)"
            )
            filtered_symbols = filtered_symbols[:self.max_symbols]
        
        # Log filtering results
        logger.info(f"Universe filtering complete:")
        logger.info(f"  - Passed filters: {len(filtered_symbols)} symbols")
        logger.info(f"  - Filtered out (low volume): {len(filtered_out['low_volume'])}")
        logger.info(f"  - Filtered out (low price): {len(filtered_out['low_price'])}")
        logger.info(f"  - Filtered out (excluded): {len(filtered_out['excluded'])}")
        logger.info(f"  - Filtered out (no ticker): {len(filtered_out['no_ticker'])}")
        
        if filtered_symbols:
            logger.info(f"  - Top symbols: {filtered_symbols[:10]}")
        
        return filtered_symbols
    
    def _load_cached_universe(self) -> Optional[Dict]:
        """Load cached universe from disk."""
        if not self.cache_path.exists():
            return None
        
        try:
            with open(self.cache_path, 'r') as f:
                cache = json.load(f)
            
            # Convert timestamp string back to datetime
            cache['timestamp'] = datetime.fromisoformat(cache['timestamp'])
            return cache
            
        except Exception as e:
            logger.warning(f"Error loading cached universe: {e}")
            return None
    
    def _save_cached_universe(self, symbols: List[str], universe_data: List[Dict]):
        """Save universe to cache."""
        try:
            cache = {
                'timestamp': datetime.utcnow().isoformat(),
                'symbols': symbols,
                'universe_size': len(universe_data)
            }
            
            with open(self.cache_path, 'w') as f:
                json.dump(cache, f, indent=2)
            
            logger.debug(f"Cached universe to {self.cache_path}")
            
        except Exception as e:
            logger.warning(f"Error saving cached universe: {e}")
    
    def get_symbol_metadata(self, symbol: str) -> Optional[Dict]:
        """
        Get metadata for a specific symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with symbol metadata, or None if not found
        """
        universe_data = self._discover_universe()
        if not universe_data:
            return None
        
        for inst in universe_data:
            if inst.get('symbol') == symbol:
                ticker_data = self._get_ticker_data([symbol])
                return {
                    **inst,
                    'ticker': ticker_data.get(symbol, {})
                }
        
        return None

