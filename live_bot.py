#!/usr/bin/env python3
"""
Live trading bot.

Usage:
    python live_bot.py --symbol BTCUSDT
"""

import argparse
import sys
import time
import signal
# Removed: threading and subprocess imports (no longer needed - training is external)
from pathlib import Path
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import bisect
from loguru import logger
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config.config_loader import load_config, get_model_paths
from src.data.live_data import LiveDataStream
from src.data.historical_data import HistoricalDataCollector
from src.signals.features import FeatureCalculator
from src.signals.primary_signal import PrimarySignalGenerator
from src.signals.meta_predictor import MetaPredictor
from src.signals.regime_filter import RegimeFilter
from src.execution.bybit_client import BybitClient
from src.risk.risk_manager import RiskManager
from src.risk.performance_guard import PerformanceGuard
from src.monitoring.trade_logger import TradeLogger
from src.monitoring.health import HealthMonitor
from src.monitoring.alerts import AlertManager
from src.portfolio.selector import PortfolioSelector
from src.exchange.universe import UniverseManager


class TradingBot:
    """Main trading bot class"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize trading bot"""
        self.config = load_config(config_path)
        self.running = False
        
        # Initialize universe manager
        self.universe_manager = UniverseManager(self.config)
        
        # Get trading symbols from universe (or fallback to config)
        self.trading_symbols = self.universe_manager.get_symbols()
        logger.info(f"Trading symbols: {self.trading_symbols}")
        
        # Initialize components
        self.feature_calc = FeatureCalculator(self.config)
        self.primary_signal_gen = PrimarySignalGenerator(self.config)
        self.regime_filter = RegimeFilter(self.config)
        self.risk_manager = RiskManager(self.config)
        self.performance_guard = PerformanceGuard(self.config)
        self.trade_logger = TradeLogger(self.config)
        self.health_monitor = HealthMonitor(self.config)
        self.alert_manager = AlertManager(self.config)
        self.portfolio_selector = PortfolioSelector(self.config)
        
        # Load model
        # NOTE: One MetaPredictor instance is created and reused for ALL symbols.
        # If model was trained in multi-symbol mode, it includes symbol encoding.
        # If model was trained in single-symbol mode, no symbol encoding is used.
        # The model does not know which symbol it's predicting for unless symbol encoding is present.
        model_paths = get_model_paths(self.config)
        self.meta_predictor = MetaPredictor(
            model_path=str(model_paths['model']),
            scaler_path=str(model_paths['scaler']),
            config_path=str(model_paths['config'])
        )
        
        # Log model coverage on startup
        trained_count = len(self.meta_predictor.trained_symbols)
        if trained_count > 0:
            logger.info(f"Model covers {trained_count} trained symbol(s): {sorted(self.meta_predictor.trained_symbols)[:10]}{'...' if trained_count > 10 else ''}")
        else:
            logger.warning("Model has no trained_symbols metadata - this may be an older model or training hasn't completed yet")
        
        # Initialize Bybit client
        exchange_config = self.config['exchange']
        self.bybit_client = BybitClient(
            api_key=exchange_config['api_key'],
            api_secret=exchange_config['api_secret'],
            testnet=exchange_config.get('testnet', True),
            timeout=exchange_config.get('api_timeout', 30),
            max_retries=exchange_config.get('api_max_retries', 3)
        )
        
        # Set leverage for all trading symbols (non-blocking)
        # Note: This may fail if API key doesn't have leverage-setting permissions
        # The bot will continue to operate - leverage may already be set on account
        leverage = int(self.config['risk']['max_leverage'])
        leverage_set_count = 0
        leverage_failed_count = 0
        
        for symbol in self.trading_symbols:
            if self.bybit_client.set_leverage(symbol, leverage):
                leverage_set_count += 1
            else:
                leverage_failed_count += 1
        
        if leverage_set_count > 0:
            logger.info(f"Set leverage {leverage}x for {leverage_set_count} symbol(s)")
        if leverage_failed_count > 0:
            logger.warning(
                f"Could not set leverage for {leverage_failed_count} symbol(s). "
                f"This may be due to API key permissions. "
                f"Bot will continue - ensure leverage is set manually on Bybit if needed."
            )
        
        # Data storage
        self.candle_data = {}  # Store candles per symbol
        self.positions = {}  # Track open positions
        self.symbol_confidence_cache = {}  # Cache recent model confidence per symbol
        self.symbol_last_trade_time = {}  # Track last trade time per symbol for cooldown
        self.processed_candle_timestamps = {}  # Track processed candle timestamps per symbol (for deduplication)
        self.last_preview_timestamp = {}  # Track last preview timestamp per symbol (to avoid repeated previews)
        self.signal_queue = []  # Queue of signals waiting to be executed (ranked by confidence)
        
        # Symbol state tracking (simplified - no training in trading bot)
        self.tradable_symbols = set()  # Symbols that can be traded (trained + meet requirements)
        self.blocked_symbols = set()  # Symbols blocked from trading (untrained or insufficient history)
        self.training_queue_path = Path("data/new_symbol_training_queue.json")
        self.training_queue_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Classify symbols into states (TRAINED, UNTRAINED_TRAINABLE, UNTRAINED_SHORT_HISTORY)
        # This does NOT trigger training - training is done by external scripts
        self._classify_symbol_states()
        
        logger.info("Trading bot initialized")
    
    def _load_historical_context(self, symbol: str, days: int = 30):
        """Load historical candles for context"""
        collector = HistoricalDataCollector(
            api_key=self.config['exchange'].get('api_key'),
            api_secret=self.config['exchange'].get('api_secret'),
            testnet=self.config['exchange'].get('testnet', True)
        )
        
        df = collector.load_candles(
            symbol=symbol,
            timeframe="60",
            data_path=self.config['data']['historical_data_path']
        )
        
        if df.empty:
            # Download if not available
            df = collector.download_and_save(
                symbol=symbol,
                days=days,
                interval="60",
                data_path=self.config['data']['historical_data_path']
            )
        
        return df
    
    def _load_existing_positions(self):
        """
        Load existing positions from Bybit and populate self.positions.
        Called on startup to re-attach to positions opened before restart.
        
        This method:
        - Fetches all open positions from Bybit
        - Attempts to retrieve stop-loss/take-profit from exchange orders
        - Falls back to config defaults if orders not found
        - Populates self.positions for monitoring
        """
        try:
            logger.info("Loading existing positions from Bybit...")
            open_positions = self.bybit_client.get_positions()
            
            if not open_positions:
                logger.info("No existing positions found")
                return
            
            logger.info(f"Found {len(open_positions)} existing position(s)")
            
            # Get all open orders to check for stop-loss/take-profit
            open_orders = self.bybit_client.get_open_orders()
            orders_by_symbol = {}
            for order in open_orders:
                symbol = order['symbol']
                if symbol not in orders_by_symbol:
                    orders_by_symbol[symbol] = []
                orders_by_symbol[symbol].append(order)
            
            for pos in open_positions:
                symbol = pos['symbol']
                entry_price = pos['entry_price']  # From exchange
                side = pos['side']
                qty = pos['size']
                
                # Try to get stop-loss/take-profit from exchange orders
                stop_loss = None
                take_profit = None
                
                if symbol in orders_by_symbol:
                    for order in orders_by_symbol[symbol]:
                        # Check for conditional stop-loss/take-profit orders
                        if order.get('stop_loss'):
                            stop_loss = order['stop_loss']
                        if order.get('take_profit'):
                            take_profit = order['take_profit']
                
                # Fallback to config defaults if not found in orders
                if stop_loss is None or take_profit is None:
                    stop_loss_pct = self.config['risk']['stop_loss_pct']
                    take_profit_pct = self.config['risk']['take_profit_pct']
                    
                    if side == 'Buy':  # Long position
                        if stop_loss is None:
                            stop_loss = entry_price * (1 - stop_loss_pct)
                        if take_profit is None:
                            take_profit = entry_price * (1 + take_profit_pct)
                    else:  # Short position
                        if stop_loss is None:
                            stop_loss = entry_price * (1 + stop_loss_pct)
                        if take_profit is None:
                            take_profit = entry_price * (1 - take_profit_pct)
                    
                    logger.warning(
                        f"Position {symbol}: Stop-loss/take-profit not found in exchange orders, "
                        f"using config defaults (SL: {stop_loss:.2f}, TP: {take_profit:.2f})"
                    )
                
                # Populate self.positions
                self.positions[symbol] = {
                    'entry_price': entry_price,
                    'side': side,
                    'qty': qty,
                    'entry_time': None,  # Lost on restart, but not critical for monitoring
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'loaded_from_exchange': True  # Flag to indicate re-attached position
                }
                
                logger.info(
                    f"Re-attached to position: {symbol} {side} {qty:.6f} @ {entry_price:.2f} "
                    f"(SL: {stop_loss:.2f}, TP: {take_profit:.2f})"
                )
            
            logger.info(f"Successfully loaded {len(self.positions)} position(s) for monitoring")
        
        except Exception as e:
            logger.error(f"Error loading existing positions: {e}", exc_info=True)
            # Don't fail startup, but log error clearly
            logger.warning("Bot will continue, but existing positions may not be monitored until manually managed")
    
    def _classify_symbol_states(self):
        """
        Classify symbols into states: TRAINED, UNTRAINED_TRAINABLE, UNTRAINED_SHORT_HISTORY.
        
        This method does NOT trigger training or reload models.
        Training is handled by external scripts (train_model.py, scheduled_retrain.py).
        
        States:
        - TRAINED: In trained_symbols + meets history requirements → TRADABLE
        - UNTRAINED_TRAINABLE: Not trained but has ≥ min_history_days → Queued for external training
        - UNTRAINED_SHORT_HISTORY: Has < min_history_days → Permanently blocked (no training)
        """
        model_config = self.config.get('model', {})
        block_untrained = model_config.get('block_untrained_symbols', True)
        block_short_history = model_config.get('block_short_history_symbols', True)
        auto_train = model_config.get('auto_train_new_symbols', True)
        min_history_days = model_config.get('min_history_days_to_train', 90)
        min_coverage_pct = model_config.get('min_history_coverage_pct', 0.95)
        
        if not block_untrained and not block_short_history:
            logger.info("Blocking untrained/short-history symbols is disabled - all symbols tradable")
            self.tradable_symbols = set(self.trading_symbols)
            self.blocked_symbols = set()
            return
        
        # Get trained symbols from already-loaded model (NO RELOAD)
        trained_symbols = set(self.meta_predictor.trained_symbols)
        universe_symbols = set(self.trading_symbols)
        
        # Initialize state sets
        self.tradable_symbols = set()
        self.blocked_symbols = set()
        symbols_to_queue = set()
        symbols_blocked_short_history = set()
        
        # Classify each symbol
        for symbol in universe_symbols:
            if symbol in trained_symbols:
                # Check if trained symbol meets history requirements
                # Access symbol_history_days from config (may not exist for older models)
                symbol_history_days_dict = self.meta_predictor.config.get('symbol_history_days', {})
                symbol_history_days = symbol_history_days_dict.get(symbol, 0) if isinstance(symbol_history_days_dict, dict) else 0
                min_required = self.meta_predictor.min_history_days_per_symbol or min_history_days
                
                if symbol_history_days >= min_required or symbol_history_days == 0:  # 0 means not tracked (older model)
                    # TRAINED state → TRADABLE
                    self.tradable_symbols.add(symbol)
                    logger.debug(f"Symbol {symbol}: TRAINED → TRADABLE")
                else:
                    # Trained but insufficient history (shouldn't happen, but handle gracefully)
                    logger.warning(f"Symbol {symbol}: Trained but history ({symbol_history_days} days) < minimum ({min_required} days). Blocking.")
                    self.blocked_symbols.add(symbol)
            else:
                # UNTRAINED - check history requirements
                # Load historical data to check history (only if needed)
                from src.data.historical_data import HistoricalDataCollector
                data_collector = HistoricalDataCollector(
                    api_key=self.config['exchange'].get('api_key'),
                    api_secret=self.config['exchange'].get('api_secret'),
                    testnet=self.config['exchange'].get('testnet', True)
                )
                
                df = data_collector.load_candles(
                    symbol=symbol,
                    timeframe="60",
                    data_path=self.config['data']['historical_data_path']
                )
                
                if df.empty:
                    # No data - assume insufficient for now, will be checked during training
                    if auto_train:
                        symbols_to_queue.add(symbol)
                        logger.info(f"Symbol {symbol}: UNTRAINED (no data) → Queued for training")
                    else:
                        self.blocked_symbols.add(symbol)
                        logger.info(f"Symbol {symbol}: UNTRAINED (no data) → Blocked (auto_train disabled)")
                    continue
                
                # Calculate history metrics
                history_metrics = HistoricalDataCollector.calculate_history_metrics(df, expected_interval_minutes=60)
                available_days = history_metrics['available_days']
                coverage_pct = history_metrics['coverage_pct']
                
                # Check minimum history requirement
                if block_short_history and available_days < min_history_days:
                    # UNTRAINED_SHORT_HISTORY → Permanently blocked
                    self.blocked_symbols.add(symbol)
                    symbols_blocked_short_history.add(symbol)
                    logger.info(
                        f"Symbol {symbol}: UNTRAINED_SHORT_HISTORY ({available_days:.1f} days < {min_history_days} minimum) → "
                        f"Permanently blocked. Run training manually after more history accumulates."
                    )
                    continue
                
                # Check coverage requirement
                if coverage_pct < min_coverage_pct:
                    # UNTRAINED_LOW_COVERAGE → Permanently blocked
                    self.blocked_symbols.add(symbol)
                    logger.info(
                        f"Symbol {symbol}: UNTRAINED_LOW_COVERAGE ({coverage_pct*100:.1f}% < {min_coverage_pct*100}% required) → "
                        f"Permanently blocked. Run training manually after data coverage improves."
                    )
                    continue
                
                # UNTRAINED_TRAINABLE → Queue for external training
                if auto_train:
                    symbols_to_queue.add(symbol)
                    logger.info(
                        f"Symbol {symbol}: UNTRAINED_TRAINABLE ({available_days:.1f} days, {coverage_pct*100:.1f}% coverage) → "
                        f"Queued for external training"
                    )
                else:
                    self.blocked_symbols.add(symbol)
                    logger.info(f"Symbol {symbol}: UNTRAINED_TRAINABLE → Blocked (auto_train disabled)")
        
        # Write to training queue file (for external training scripts)
        if symbols_to_queue:
            self._write_to_training_queue(symbols_to_queue)
        
        # Log summary
        logger.info("=" * 60)
        logger.info("Symbol Classification Summary")
        logger.info("=" * 60)
        logger.info(f"TRADABLE: {len(self.tradable_symbols)} symbol(s) - {sorted(self.tradable_symbols)}")
        logger.info(f"BLOCKED: {len(self.blocked_symbols)} symbol(s) - {sorted(self.blocked_symbols)}")
        if symbols_to_queue:
            logger.info(f"QUEUED FOR TRAINING: {len(symbols_to_queue)} symbol(s) - {sorted(symbols_to_queue)}")
        if symbols_blocked_short_history:
            logger.info(f"  - {len(symbols_blocked_short_history)} blocked due to insufficient history")
        logger.info("=" * 60)
        logger.info("NOTE: Training is handled by external scripts (train_model.py, scheduled_retrain.py)")
        logger.info("      The trading bot will continue trading TRADABLE symbols only.")
        logger.info("=" * 60)
    
    def _write_to_training_queue(self, symbols: set):
        """
        Write symbols to training queue file for external training scripts.
        
        Args:
            symbols: Set of symbols to queue for training
        """
        queue_path = self.training_queue_path
        
        # Load existing queue
        queue_data = {"queued_symbols": [], "queued_at": {}}
        if queue_path.exists():
            try:
                with open(queue_path, 'r') as f:
                    queue_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read training queue: {e}")
        
        # Add new symbols (avoid duplicates)
        existing_symbols = set(queue_data.get('queued_symbols', []))
        new_symbols = symbols - existing_symbols
        
        if new_symbols:
            queue_data['queued_symbols'] = list(existing_symbols | symbols)
            for symbol in new_symbols:
                queue_data['queued_at'][symbol] = datetime.now(timezone.utc).isoformat()
            
            try:
                with open(queue_path, 'w') as f:
                    json.dump(queue_data, f, indent=2)
                logger.info(f"Added {len(new_symbols)} symbol(s) to training queue: {sorted(new_symbols)}")
            except Exception as e:
                logger.error(f"Could not write training queue: {e}")
    
    def is_symbol_tradable(self, symbol: str) -> bool:
        """
        Check if a symbol is tradable (trained and meets requirements).
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            True if symbol is tradable, False otherwise
        """
        return symbol in self.tradable_symbols
    
    def _refresh_symbol_states(self):
        """
        Re-classify symbols after universe refresh or model update.
        This is called when the universe changes or when we want to check if
        newly trained symbols can now be traded.
        
        NOTE: This does NOT reload the model. Model should be reloaded externally
        (e.g., on process restart) or via explicit signal.
        """
        logger.info("Refreshing symbol states...")
        self._classify_symbol_states()
    
    def _on_new_candle(self, df: pd.DataFrame):
        """Handle new candle from WebSocket"""
        if df.empty:
            return
        
        symbol = df['symbol'].iloc[0]
        timestamp = df['timestamp'].iloc[0]
        
        # Deduplication: Skip if we've already processed this candle timestamp
        if symbol not in self.processed_candle_timestamps:
            self.processed_candle_timestamps[symbol] = set()
        
        # Convert timestamp to a comparable format (use the start of the candle as the key)
        if isinstance(timestamp, pd.Timestamp):
            timestamp_key = timestamp.floor('h')  # Floor to hour for hourly candles
        else:
            timestamp_key = pd.to_datetime(timestamp).floor('h')
        
        # Check if we've already processed this candle
        if timestamp_key in self.processed_candle_timestamps[symbol]:
            logger.debug(f"[{symbol}] Skipping duplicate candle: {timestamp_key}")
            return
        
        # Mark this candle as processed
        self.processed_candle_timestamps[symbol].add(timestamp_key)
        
        # Keep only last 100 processed timestamps to limit memory
        if len(self.processed_candle_timestamps[symbol]) > 100:
            # Remove oldest timestamps (keep most recent 100)
            sorted_timestamps = sorted(self.processed_candle_timestamps[symbol])
            self.processed_candle_timestamps[symbol] = set(sorted_timestamps[-100:])
        
        # Update candle data
        if symbol not in self.candle_data:
            # Load historical context
            self.candle_data[symbol] = self._load_historical_context(symbol)
        
        # Append new candle
        self.candle_data[symbol] = pd.concat([
            self.candle_data[symbol],
            df
        ], ignore_index=True)
        
        # Keep only last 500 candles
        self.candle_data[symbol] = self.candle_data[symbol].tail(500).reset_index(drop=True)
        
        # Update health monitor
        if 'timestamp' in df.columns and len(df) > 0:
            try:
                last_timestamp = pd.to_datetime(df['timestamp'].iloc[-1])
                self.health_monitor.update_candle(symbol, last_timestamp)
            except:
                pass
        
        # Process signal (callback is only called for closed candles by WebSocket handler)
        # The WebSocket handler in live_data.py only calls callback when is_closed=True
        # So by the time we get here, the candle should be closed
        # Log only when processing signal (reduces log spam)
        logger.info(f"[{symbol}] Closed candle received: {timestamp} | Close: {df['close'].iloc[0]:.2f} - Processing signal...")
        self._process_signal(symbol, is_preview=False)
    
    def _preview_signal(self, df: pd.DataFrame):
        """Preview potential trade based on open candle (does not execute trades)"""
        if df.empty:
            return
        
        symbol = df['symbol'].iloc[0]
        timestamp = df['timestamp'].iloc[0]
        
        # Only preview tradable symbols
        if not self.is_symbol_tradable(symbol):
            return
        
        # Deduplication: Skip if we've previewed this candle recently (within last 2 minutes)
        # This prevents showing the same preview repeatedly for the same open candle
        # Note: WebSocket already throttles previews (every 10 updates), but this adds extra protection
        if symbol in self.last_preview_timestamp:
            last_preview = self.last_preview_timestamp[symbol]
            if isinstance(timestamp, pd.Timestamp):
                timestamp_dt = timestamp
            else:
                timestamp_dt = pd.to_datetime(timestamp)
            
            time_diff = (timestamp_dt - last_preview).total_seconds()
            if time_diff < 120:  # 2 minutes
                return  # Skip preview if shown recently
        
        # Update last preview timestamp
        if isinstance(timestamp, pd.Timestamp):
            self.last_preview_timestamp[symbol] = timestamp
        else:
            self.last_preview_timestamp[symbol] = pd.to_datetime(timestamp)
        
        # Need to build a temporary DataFrame with the open candle for evaluation
        # Use existing candle data if available, or create minimal context
        if symbol not in self.candle_data:
            # Load historical context for preview
            self.candle_data[symbol] = self._load_historical_context(symbol)
        
        # Create a temporary DataFrame with the open candle appended
        temp_df = pd.concat([
            self.candle_data[symbol],
            df
        ], ignore_index=True).tail(500).reset_index(drop=True)
        
        if len(temp_df) < 50:  # Need enough history
            return
        
        # Evaluate signal (preview mode - no trading)
        self._process_signal(symbol, is_preview=True, preview_df=temp_df, preview_timestamp=timestamp)
    
    def _process_signal(self, symbol: str, is_preview: bool = False, preview_df: Optional[pd.DataFrame] = None, preview_timestamp: Optional[datetime] = None):
        """
        Process trading signal for a symbol.
        
        Args:
            symbol: Trading symbol
            is_preview: If True, only evaluate and log (no trading)
            preview_df: Optional DataFrame to use for preview (instead of self.candle_data)
            preview_timestamp: Optional timestamp for preview logging
        """
        # Check if symbol is tradable (simplified check)
        if not self.is_symbol_tradable(symbol):
            # Log occasionally to avoid spam
            import random
            if random.random() < 0.01:  # 1% chance
                if symbol in self.blocked_symbols:
                    logger.debug(f"Symbol {symbol} is blocked (untrained or insufficient history)")
                else:
                    logger.debug(f"Symbol {symbol} is not in tradable set")
            return
        
        # Use preview_df if provided, otherwise use cached candle data
        if preview_df is not None:
            df = preview_df
        else:
            if symbol not in self.candle_data:
                return
            df = self.candle_data[symbol]
        
        if len(df) < 50:  # Need enough history
            return
        
        preview_prefix = "👁️  PREVIEW: " if is_preview else ""
        
        try:
            # Calculate features
            df_with_features = self.feature_calc.calculate_indicators(df)
            
            # Generate primary signal
            primary_signal = self.primary_signal_gen.generate_signal(df_with_features)
            
            # Always log non-neutral signals as potential trades (symbol + direction)
            if primary_signal['direction'] == 'NEUTRAL':
                # Log occasionally to show the bot is evaluating signals (only for real trades, not previews)
                if not is_preview:
                    import random
                    if random.random() < 0.05:  # 5% chance to log NEUTRAL signals (reduce spam)
                        logger.debug(f"[{symbol}] Signal evaluation: NEUTRAL (no trend signal detected)")
                return
            
            # For preview mode: only log if trade passes all filters (silent evaluation)
            # For real trades: log potential trade and filter results
            current_price = df_with_features['close'].iloc[-1]
            
            if not is_preview:
                # Log potential trade (always show symbol + direction when candle closes)
                logger.info(
                    f"[{symbol}] 🔍 Potential trade: {primary_signal['direction']} @ {current_price:.2f} "
                    f"(strength: {primary_signal.get('strength', 'N/A')}) - Evaluating filters..."
                )
            
            # Regime filter check
            regime_allowed, regime_reason, regime_multiplier = self.regime_filter.should_allow_trade(
                df_with_features,
                primary_signal['direction']
            )
            
            if not regime_allowed:
                if not is_preview:
                    logger.info(f"[{symbol}] ❌ Filtered by regime filter: {regime_reason}")
                return
            
            # Build meta-features (include symbol encoding for multi-symbol models)
            # Get symbol encoding map from model config if available
            symbol_encoding_map = self.meta_predictor.config.get('symbol_encoding_map', {})
            
            # Build features with symbol encoding if model was trained with it
            meta_features = self.feature_calc.build_meta_features(
                df_with_features,
                primary_signal,
                symbol=symbol,
                symbol_encoding=symbol_encoding_map if symbol_encoding_map else None
            )
            
            # Predict profitability
            confidence = self.meta_predictor.predict(meta_features)
            
            # Cache confidence for portfolio selector
            self.symbol_confidence_cache[symbol] = confidence
            
            # Portfolio selector check (if enabled)
            if self.portfolio_selector.enabled:
                # Check if rebalancing needed (do this once, not per symbol)
                if self.portfolio_selector.should_rebalance():
                    logger.info("Portfolio rebalancing triggered")
                    # Rebalance: select symbols based on current data
                    symbol_data = {}
                    for sym in self.trading_symbols:
                        if sym in self.candle_data and len(self.candle_data[sym]) >= 50:
                            df_with_features_sym = self.feature_calc.calculate_indicators(self.candle_data[sym])
                            symbol_data[sym] = df_with_features_sym
                    
                    selected = self.portfolio_selector.select_symbols(
                        symbol_data=symbol_data,
                        symbol_confidence=self.symbol_confidence_cache
                    )
                    logger.info(f"Portfolio rebalanced. Selected symbols: {selected}")
                
                # Check if this symbol is selected
                if not self.portfolio_selector.is_symbol_selected(symbol):
                    if not is_preview:
                        logger.info(f"[{symbol}] ❌ Filtered by portfolio selector (not selected)")
                    return
            
            # Performance guard check
            current_equity = None
            balance = self.bybit_client.get_account_balance()
            if balance:
                current_equity = balance['total_equity']
                self.performance_guard.update_equity(current_equity)
            
            guard_status, guard_metrics = self.performance_guard.check_status(current_equity)
            guard_allowed, guard_reason = self.performance_guard.should_allow_trade()
            
            if not guard_allowed:
                if not is_preview:
                    logger.warning(f"[{symbol}] ❌ Filtered by performance guard: {guard_reason}")
                    # Send alert (only for real trades, not previews)
                    self.alert_manager.notify_event(
                        event_type="PERFORMANCE_GUARD_PAUSED",
                        message=f"Trading paused: {guard_reason}",
                        context={
                            'status': guard_status,
                            'metrics': guard_metrics
                        },
                        severity="WARNING"
                    )
                return
            
            # Adjust confidence threshold based on performance guard
            base_threshold = self.config['model']['confidence_threshold']
            confidence_adjustment = self.performance_guard.get_confidence_adjustment()
            adjusted_threshold = base_threshold + confidence_adjustment
            
            # Log confidence evaluation (only for real trades, not previews)
            if not is_preview:
                logger.info(
                    f"[{symbol}] 📊 Confidence: {confidence:.3f} | "
                    f"Threshold: {adjusted_threshold:.3f} "
                    f"(base: {base_threshold:.3f} + adj: {confidence_adjustment:+.3f})"
                )
            
            # Log signal to trade logger (only for real trades, not previews)
            if not is_preview:
                self.trade_logger.log_signal(
                    symbol=symbol,
                    direction=primary_signal['direction'],
                    confidence=confidence,
                    features=meta_features
                )
            
            # Check confidence threshold
            if confidence < adjusted_threshold:
                if not is_preview:
                    logger.info(
                        f"[{symbol}] ❌ Filtered by confidence: {confidence:.3f} < {adjusted_threshold:.3f} "
                        f"(needs {adjusted_threshold - confidence:.3f} more)"
                    )
                return
            
            # Log that signal passed all filters
            if is_preview:
                # Only log in preview mode if trade passes all filters
                time_info = f" @ {preview_timestamp}" if preview_timestamp else ""
                logger.info(
                    f"👁️  PREVIEW: [{symbol}] ✅ WOULD EXECUTE TRADE: {primary_signal['direction']} "
                    f"@ {df_with_features['close'].iloc[-1]:.2f}{time_info} "
                    f"(confidence: {confidence:.3f}, strength: {primary_signal.get('strength', 'N/A')})"
                )
                return  # Don't execute trades in preview mode
            
            # Log that signal passed all filters
            logger.info(
                f"[{symbol}] ✅ PASSED ALL FILTERS! Queueing trade: {primary_signal['direction']} "
                f"@ {df_with_features['close'].iloc[-1]:.2f} (confidence: {confidence:.3f})"
            )
            
            # Get volatility for position sizing (before execute_trade)
            current_volatility = None
            if 'volatility' in df_with_features.columns:
                current_volatility = df_with_features['volatility'].iloc[-1]
            
            # Add to signal queue (ranked by confidence)
            signal_entry = {
                'symbol': symbol,
                'direction': primary_signal['direction'],
                'confidence': confidence,
                'current_price': df_with_features['close'].iloc[-1],
                'current_volatility': current_volatility,
                'regime_multiplier': regime_multiplier,
                'timestamp': datetime.now(timezone.utc),
                'strength': primary_signal.get('strength', 0.0)
            }
            
            # Insert in sorted order (highest confidence first)
            # Sort by confidence descending, then by strength descending
            queue_scores = [(-s['confidence'], -s.get('strength', 0)) for s in self.signal_queue]
            new_score = (-confidence, -primary_signal.get('strength', 0))
            insert_pos = bisect.bisect_left(queue_scores, new_score)
            self.signal_queue.insert(insert_pos, signal_entry)
            
            logger.debug(f"[{symbol}] Added to signal queue (position {insert_pos + 1}/{len(self.signal_queue)}, confidence: {confidence:.3f})")
            
            # Process queue (try to execute highest confidence signals first)
            self._process_signal_queue()
        
        except Exception as e:
            logger.error(f"Error processing signal for {symbol}: {e}")
            self.trade_logger.log_error("SIGNAL_PROCESSING", str(e))
    
    def _process_signal_queue(self):
        """Process queued signals, executing highest confidence first"""
        if not self.signal_queue:
            return
        
        # Get current open positions
        open_positions = self.bybit_client.get_positions()
        max_positions = self.config['risk']['max_open_positions']
        available_slots = max_positions - len(open_positions)
        
        if available_slots <= 0:
            # No slots available - remove signals that can't be executed
            logger.debug(f"Signal queue has {len(self.signal_queue)} signals, but {len(open_positions)}/{max_positions} positions are open")
            # Keep queue for when slots become available
            return
        
        # Process up to available_slots signals (highest confidence first)
        executed_count = 0
        remaining_queue = []
        
        for signal in self.signal_queue:
            if executed_count >= available_slots:
                # Keep remaining signals in queue
                remaining_queue.append(signal)
                continue
            
            # Try to execute this signal
            try:
                logger.info(
                    f"[{signal['symbol']}] 🎯 Processing queued signal: {signal['direction']} "
                    f"@ {signal['current_price']:.2f} (confidence: {signal['confidence']:.3f}, "
                    f"queue position: {executed_count + 1})"
                )
                
                # Execute trade
                trade_successful = self._execute_trade(
                    symbol=signal['symbol'],
                    direction=signal['direction'],
                    confidence=signal['confidence'],
                    current_price=signal['current_price'],
                    current_volatility=signal['current_volatility'],
                    regime_multiplier=signal['regime_multiplier']
                )
                
                # Only increment executed_count if trade was actually placed
                if trade_successful:
                    executed_count += 1
                else:
                    # Trade failed - remove from queue (unless it's a temporary issue like max positions)
                    logger.debug(f"[{signal['symbol']}] Trade execution failed, removing from queue")
                    continue
                
                # Check if we still have slots (position might have failed)
                open_positions = self.bybit_client.get_positions()
                available_slots = max_positions - len(open_positions)
                if available_slots <= 0:
                    # No more slots, keep remaining signals
                    remaining_queue.extend(self.signal_queue[executed_count:])
                    break
                    
            except Exception as e:
                logger.error(f"Error executing queued signal for {signal['symbol']}: {e}")
                # Remove failed signal from queue
                continue
        
        # Update queue with remaining signals
        self.signal_queue = remaining_queue
        
        if executed_count > 0:
            logger.info(f"Executed {executed_count} signal(s) from queue. {len(self.signal_queue)} signal(s) remaining in queue")
        
        # Clean up old signals (older than 1 hour)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
        self.signal_queue = [s for s in self.signal_queue if s['timestamp'] > cutoff_time]
    
    def _execute_trade(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        current_price: float,
        current_volatility: Optional[float] = None,
        regime_multiplier: float = 1.0
    ) -> bool:
        """
        Execute a trade
        
        Returns:
            True if trade was successfully placed, False otherwise
        """
        try:
            # Get account balance
            balance = self.bybit_client.get_account_balance()
            if not balance:
                logger.error(f"[{symbol}] Could not get account balance - skipping trade")
                return False
            
            equity = balance.get('total_equity', 0.0)
            if equity <= 0:
                logger.warning(
                    f"[{symbol}] ❌ Cannot execute trade: zero or negative equity "
                    f"Balance response: {balance}. Cannot execute trades with zero balance."
                )
                return False
            
            # Update risk manager
            self.risk_manager.update_account_state(equity)
            
            # Get open positions
            open_positions = self.bybit_client.get_positions()
            
            # Calculate position size (with volatility targeting)
            base_position_size = self.risk_manager.calculate_position_size(
                equity=equity,
                signal_confidence=confidence,
                entry_price=current_price,
                current_volatility=current_volatility
            )
            
            # Apply performance guard and regime multipliers
            guard_multiplier = self.performance_guard.get_size_multiplier()
            position_size_before_portfolio = base_position_size * guard_multiplier * regime_multiplier
            
            # Apply portfolio selector risk limit (if enabled)
            if self.portfolio_selector.enabled:
                max_symbol_risk = self.portfolio_selector.get_symbol_risk_limit(symbol, equity)
                # Convert risk limit to position size (simplified: assume 1:1 for now)
                # In practice, this should account for leverage and stop-loss
                max_position_value = max_symbol_risk
                max_position_size_from_portfolio = max_position_value / current_price if current_price > 0 else position_size_before_portfolio
                final_position_size = min(position_size_before_portfolio, max_position_size_from_portfolio)
            else:
                final_position_size = position_size_before_portfolio
            
            logger.info(f"Position sizing: base={base_position_size:.6f}, guard_mult={guard_multiplier:.2f}, regime_mult={regime_multiplier:.2f}, final={final_position_size:.6f}")
            
            # Validate position size before proceeding
            # Bybit minimum order size is typically 0.001, but we'll use a slightly higher threshold for safety
            min_order_size = 0.001  # Minimum order size for Bybit
            
            # Check for zero or negative position size (with small epsilon for floating point precision)
            if final_position_size <= 0 or abs(final_position_size) < 1e-10:
                logger.warning(
                    f"[{symbol}] ❌ Cannot place order: position size is zero or negative "
                    f"(final_size={final_position_size:.6f}, base={base_position_size:.6f}, "
                    f"equity={equity:.2f}, price={current_price:.2f})"
                )
                return False
            
            # Check if position size is below minimum order size
            if final_position_size < min_order_size:
                logger.warning(
                    f"[{symbol}] ❌ Cannot place order: position size below minimum "
                    f"(final_size={final_position_size:.6f} < min={min_order_size}, "
                    f"base={base_position_size:.6f}, equity={equity:.2f}, price={current_price:.2f})"
                )
                return False
            
            # Check risk limits (use final position size and current price)
            is_allowed, reason = self.risk_manager.check_risk_limits(
                equity=equity,
                open_positions=open_positions,
                symbol=symbol,
                proposed_size=final_position_size,
                entry_price=current_price
            )
            
            if not is_allowed:
                logger.warning(f"[{symbol}] Trade not allowed: {reason}")
                # Remove signal from queue if it's a permanent issue (not max positions)
                if "Max open positions" not in reason:
                    self.signal_queue = [s for s in self.signal_queue if s['symbol'] != symbol]
                return False
            
            # Check position cooldown (24 hours before re-entering same symbol)
            position_cooldown_hours = self.config['risk'].get('position_cooldown_hours', 8)
            if symbol in self.symbol_last_trade_time:
                hours_since_last = (datetime.now(timezone.utc) - self.symbol_last_trade_time[symbol]).total_seconds() / 3600
                if hours_since_last < position_cooldown_hours:
                    logger.info(
                        f"[{symbol}] ❌ Filtered by position cooldown: "
                        f"{hours_since_last:.1f}h since last trade (need {position_cooldown_hours}h)"
                    )
                    return False
            
            # Store original position size before any adjustments
            original_position_size = final_position_size
            
            # Get instrument info to check minimum notional and lot size
            # Increase size if needed to meet exchange minimum (after risk check passes)
            try:
                instrument_info = self.bybit_client.session.get_instruments_info(
                    category="linear",
                    symbol=symbol
                )
                if instrument_info.get('retCode') == 0:
                    result = instrument_info.get('result', {})
                    if 'list' in result and len(result['list']) > 0:
                        lot_size_filter = result['list'][0].get('lotSizeFilter', {})
                        min_notional = float(lot_size_filter.get('minNotionalValue', '5.0'))
                        qty_step = float(lot_size_filter.get('qtyStep', '0.001'))
                        min_order_qty = float(lot_size_filter.get('minOrderQty', '0.001'))
                        
                        # Check if position value meets minimum notional
                        position_value = final_position_size * current_price
                        if position_value < min_notional:
                            # Increase quantity to meet minimum
                            min_qty_needed = min_notional / current_price
                            # Round up to next qty_step
                            increased_size = (int(min_qty_needed / qty_step) + 1) * qty_step
                            
                            # Check if increased size still passes risk limits
                            is_allowed_increased, reason_increased = self.risk_manager.check_risk_limits(
                                equity=equity,
                                open_positions=open_positions,
                                symbol=symbol,
                                proposed_size=increased_size,
                                entry_price=current_price
                            )
                            
                            if is_allowed_increased or "exceeds limit" in reason_increased:
                                # Allow it if original passed and we're only increasing for exchange minimum
                                final_position_size = increased_size
                                logger.info(
                                    f"[{symbol}] ⚠️  Position size increased to meet minimum notional: "
                                    f"{original_position_size:.6f} -> {final_position_size:.6f} "
                                    f"(${position_value:.2f} -> ${final_position_size * current_price:.2f})"
                                )
                            else:
                                logger.warning(
                                    f"[{symbol}] ❌ Cannot increase size to meet minimum: {reason_increased}"
                                )
                                return False
                        
                        # Ensure it meets minimum order quantity
                        if final_position_size < min_order_qty:
                            final_position_size = min_order_qty
                            logger.info(f"[{symbol}] ⚠️  Position size adjusted to minimum order qty: {min_order_qty}")
            except Exception as e:
                logger.debug(f"[{symbol}] Could not check instrument info: {e}, using defaults")
                # Final check: ensure position value meets minimum notional (fallback)
                final_position_value = final_position_size * current_price
                if final_position_value < 5.0:  # Bybit's typical minimum
                    logger.warning(
                        f"[{symbol}] ❌ Cannot place order: position value ${final_position_value:.2f} "
                        f"below minimum notional $5.00 (size={final_position_size:.6f}, price={current_price:.2f})"
                    )
                    return False
            
            # Determine order side
            side = 'Buy' if direction == 'LONG' else 'Sell'
            
            # Calculate stop loss and take profit
            stop_loss_pct = self.config['risk']['stop_loss_pct']
            take_profit_pct = self.config['risk']['take_profit_pct']
            
            if direction == 'LONG':
                stop_loss = current_price * (1 - stop_loss_pct)
                take_profit = current_price * (1 + take_profit_pct)
            else:  # SHORT
                stop_loss = current_price * (1 + stop_loss_pct)
                take_profit = current_price * (1 - take_profit_pct)
            
            # Place order (use final position size)
            order = self.bybit_client.place_order(
                symbol=symbol,
                side=side,
                order_type='Market',
                qty=final_position_size,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if order:
                self.trade_logger.log_order(
                    symbol=symbol,
                    side=side,
                    qty=final_position_size,
                    price=current_price,
                    order_id=order['order_id']
                )
                
                # Update health monitor
                self.health_monitor.update_trade(datetime.now(timezone.utc))
                
                # Track position
                self.positions[symbol] = {
                    'entry_price': current_price,
                    'side': side,
                    'qty': final_position_size,
                    'entry_time': datetime.now(timezone.utc),
                    'stop_loss': stop_loss,
                    'take_profit': take_profit
                }
                
                # Record trade time for cooldown tracking
                self.symbol_last_trade_time[symbol] = datetime.now(timezone.utc)
                
                logger.info(f"[{symbol}] ✅ Trade successfully placed: {side} {final_position_size:.6f} @ {current_price:.2f}")
                return True
            else:
                logger.warning(f"[{symbol}] ❌ Order placement failed: order returned None")
                return False
        
        except Exception as e:
            logger.error(f"[{symbol}] Error executing trade: {e}")
            self.trade_logger.log_error("TRADE_EXECUTION", str(e))
            return False
    
    def _monitor_positions(self):
        """
        Monitor open positions and check exit conditions.
        Also reconciles with exchange state to handle positions closed externally.
        """
        # Process signal queue when monitoring positions (in case slots opened up)
        self._process_signal_queue()
        
        try:
            open_positions = self.bybit_client.get_positions()
            exchange_positions_dict = {pos['symbol']: pos for pos in open_positions}
            
            # Monitor tracked positions
            for symbol, tracked in list(self.positions.items()):
                if symbol in exchange_positions_dict:
                    pos = exchange_positions_dict[symbol]
                    mark_price = pos['mark_price']
                    
                    # Verify position side matches (sanity check)
                    if pos['side'] != tracked['side']:
                        logger.warning(
                            f"Position {symbol} side mismatch: tracked={tracked['side']}, "
                            f"exchange={pos['side']}. Re-syncing..."
                        )
                        # Update tracked side to match exchange
                        tracked['side'] = pos['side']
                    
                    # Check stop loss / take profit
                    if pos['side'] == 'Buy':  # Long position
                        if mark_price <= tracked['stop_loss']:
                            self._close_position(symbol, "STOP_LOSS")
                        elif mark_price >= tracked['take_profit']:
                            self._close_position(symbol, "TAKE_PROFIT")
                    else:  # Short position
                        if mark_price >= tracked['stop_loss']:
                            self._close_position(symbol, "STOP_LOSS")
                        elif mark_price <= tracked['take_profit']:
                            self._close_position(symbol, "TAKE_PROFIT")
                else:
                    # Position closed externally (not by bot)
                    logger.warning(
                        f"Position {symbol} closed externally (not in exchange positions), "
                        f"removing from tracking"
                    )
                    del self.positions[symbol]
            
            # Detect positions on exchange not in self.positions (shouldn't happen after fix, but handle it)
            for symbol, pos in exchange_positions_dict.items():
                if symbol not in self.positions:
                    logger.warning(
                        f"Found untracked position {symbol} on exchange - this should not happen. "
                        f"Attempting to load it now..."
                    )
                    # Try to load it (one-time sync)
                    try:
                        entry_price = pos['entry_price']
                        side = pos['side']
                        qty = pos['size']
                        
                        # Use config defaults for stop-loss/take-profit
                        stop_loss_pct = self.config['risk']['stop_loss_pct']
                        take_profit_pct = self.config['risk']['take_profit_pct']
                        
                        if side == 'Buy':  # Long
                            stop_loss = entry_price * (1 - stop_loss_pct)
                            take_profit = entry_price * (1 + take_profit_pct)
                        else:  # Short
                            stop_loss = entry_price * (1 + stop_loss_pct)
                            take_profit = entry_price * (1 - take_profit_pct)
                        
                        self.positions[symbol] = {
                            'entry_price': entry_price,
                            'side': side,
                            'qty': qty,
                            'entry_time': None,
                            'stop_loss': stop_loss,
                            'take_profit': take_profit,
                            'loaded_from_exchange': True
                        }
                        logger.info(f"Loaded untracked position {symbol} for monitoring")
                    except Exception as e:
                        logger.error(f"Failed to load untracked position {symbol}: {e}")
        
        except Exception as e:
            logger.error(f"Error monitoring positions: {e}", exc_info=True)
    
    def _close_position(self, symbol: str, reason: str):
        """Close a position"""
        try:
            # Get current position
            positions = self.bybit_client.get_positions(symbol=symbol)
            if not positions:
                return
            
            pos = positions[0]
            exit_price = pos['mark_price']
            
            # Place closing order
            close_side = 'Sell' if pos['side'] == 'Buy' else 'Buy'
            
            order = self.bybit_client.place_order(
                symbol=symbol,
                side=close_side,
                order_type='Market',
                qty=pos['size'],
                reduce_only=True
            )
            
            if order and symbol in self.positions:
                tracked = self.positions[symbol]
                
                # Calculate PnL
                if pos['side'] == 'Buy':
                    pnl = (exit_price - tracked['entry_price']) * tracked['qty']
                else:
                    pnl = (tracked['entry_price'] - exit_price) * tracked['qty']
                
                # Log trade
                self.trade_logger.log_trade(
                    symbol=symbol,
                    side=pos['side'],
                    entry_price=tracked['entry_price'],
                    exit_price=exit_price,
                    qty=tracked['qty'],
                    pnl=pnl,
                    entry_time=tracked['entry_time'],
                    exit_time=datetime.now(timezone.utc)
                )
                
                # Update risk manager and performance guard
                self.risk_manager.update_daily_pnl(pnl)
                self.performance_guard.record_trade(pnl, pnl > 0)
                
                # Update health monitor
                self.health_monitor.update_trade(datetime.now(timezone.utc))
                
                # Remove from tracking
                del self.positions[symbol]
                
                logger.info(f"Closed position {symbol}: {reason} | PnL: {pnl:.2f} USDT")
        
        except Exception as e:
            logger.error(f"Error closing position: {e}")
    
    def start(self):
        """Start the trading bot"""
        logger.info("=" * 60)
        logger.info("Starting trading bot")
        logger.info("=" * 60)
        
        # Load existing positions from exchange (re-attach after restart)
        self._load_existing_positions()
        
        # Refresh universe if in auto mode (to get latest symbols)
        if self.config['exchange'].get('universe_mode') == 'auto':
            logger.info("Auto universe mode: refreshing symbol list...")
            self.trading_symbols = self.universe_manager.get_symbols(force_refresh=True)
            logger.info(f"Universe refreshed: {len(self.trading_symbols)} symbols")
            
            # Re-classify symbols after universe refresh (no model reload, no training)
            self._refresh_symbol_states()
        
        # Initialize data streams
        symbols = self.trading_symbols
        
        def on_candle(df):
            self._on_new_candle(df)
        
        def on_preview(df):
            self._preview_signal(df)
        
        # Preview throttle: show preview every N open candle updates (default: 10 = roughly every 30-60 seconds)
        preview_throttle = self.config.get('operations', {}).get('preview_throttle', 10)
        
        stream = LiveDataStream(
            symbols=symbols,
            interval="60",  # 1 hour
            testnet=self.config['exchange'].get('testnet', True),
            callback=on_candle,
            preview_callback=on_preview,
            preview_throttle=preview_throttle
        )
        
        # Start WebSocket
        stream.start()
        self.stream = stream  # Store reference for monitoring
        self.running = True
        
        # Store start time for data reception monitoring
        self.start_time = time.time()
        
        logger.info(f"Bot running. Monitoring {len(symbols)} symbols: {symbols[:10]}{'...' if len(symbols) > 10 else ''}")
        logger.info("Press Ctrl+C to stop")
        logger.info("IMPORTANT: Hourly candles only close at the top of each hour (e.g., 09:00, 10:00, 11:00)")
        logger.info("Trades execute when candles CLOSE. Preview signals shown for open candles (👁️ PREVIEW prefix).")
        
        # Initialize portfolio selector (if enabled)
        if self.portfolio_selector.enabled:
            logger.info("Portfolio selector enabled - will select symbols on first rebalance")
            # Initial selection will happen on first signal processing
        
        try:
            # Main loop
            health_check_interval = self.config.get('operations', {}).get('health_check_interval_seconds', 300)
            last_health_check = time.time()
            last_heartbeat = time.time()
            heartbeat_interval = 600  # Log heartbeat every 10 minutes
            
            logger.info(f"Main loop started. Health checks every {health_check_interval}s, heartbeat every {heartbeat_interval}s")
            logger.info(f"Tradable symbols: {len(self.tradable_symbols)}, Blocked: {len(self.blocked_symbols)}")
            logger.info(f"Trading will proceed for tradable symbols only. Training is handled by external scripts.")
            
            while self.running:
                time.sleep(60)  # Check every minute
                
                current_time = time.time()
                
                # Periodic heartbeat (every 10 minutes)
                if (current_time - last_heartbeat) >= heartbeat_interval:
                    last_heartbeat = current_time
                    tradable_count = len(self.tradable_symbols)
                    blocked_count = len(self.blocked_symbols)
                    positions_count = len(self.positions)
                    candles_received = sum(1 for s in symbols if s in self.candle_data and len(self.candle_data[s]) > 0)
                    
                    # Check WebSocket status
                    ws_status = "UNKNOWN"
                    if hasattr(self, 'stream') and self.stream:
                        ws_status = "RUNNING" if self.stream.is_running() else "STOPPED"
                    
                    # Count symbols with enough history for signal processing
                    symbols_with_enough_data = sum(
                        1 for s in symbols 
                        if s in self.candle_data and len(self.candle_data[s]) >= 50
                    )
                    
                    # Count recent signals evaluated (from cache)
                    recent_signals = len(self.symbol_confidence_cache)
                    
                    logger.info(
                        f"Bot heartbeat: {tradable_count} tradable symbols, {blocked_count} blocked, "
                        f"{positions_count} open positions, {candles_received} symbols with data, "
                        f"{symbols_with_enough_data} symbols with enough history (≥50 candles), "
                        f"{recent_signals} symbols with recent signal evaluations, "
                        f"WebSocket: {ws_status}"
                    )
                    
                    # Log reminder about hourly candles and signal processing
                    if candles_received > 0 and positions_count == 0 and recent_signals == 0:
                        logger.info(
                            "ℹ️  Note: Hourly candles only close at the top of each hour (e.g., 09:00, 10:00, 11:00). "
                            "Signals are only processed when candles CLOSE. "
                            "Open candle updates are received but signals are not evaluated until candle closes."
                        )
                    
                    # Warn if no data received after 10 minutes
                    elapsed_minutes = (current_time - self.start_time) / 60
                    if candles_received == 0 and elapsed_minutes > 10:
                        logger.warning(
                            f"No candle data received after {elapsed_minutes:.1f} minutes. "
                            f"WebSocket status: {ws_status}. "
                            f"Check WebSocket connection and subscriptions."
                        )
                
                # Monitor positions
                self._monitor_positions()
                
                # Check kill switch
                balance = self.bybit_client.get_account_balance()
                if balance:
                    equity = balance['total_equity']
                    should_kill, reason = self.risk_manager.should_trigger_kill_switch(equity)
                    
                    if should_kill:
                        logger.critical(f"Kill switch triggered: {reason}")
                        # Send critical alert
                        self.alert_manager.notify_event(
                            event_type="KILL_SWITCH",
                            message=f"Kill switch activated: {reason}",
                            context={'equity': equity},
                            severity="CRITICAL"
                        )
                        self.stop()
                        break
                
                # NOTE: Training is handled by external scripts (train_model.py, scheduled_retrain.py)
                # The trading bot does NOT train symbols during runtime.
                # To add new symbols:
                # 1. Run training externally: python train_model.py --symbol SYMBOL
                # 2. Restart the bot to pick up the new model
                # Or use scheduled_retrain.py to process the training queue
                
                # Periodic health check (every N seconds as configured)
                current_time = time.time()
                if hasattr(self, 'health_monitor') and (current_time - last_health_check) >= health_check_interval:
                    last_health_check = current_time
                    open_positions = self.bybit_client.get_positions()
                    positions_dict = {pos['symbol']: pos for pos in open_positions} if open_positions else {}
                    
                    guard_status, guard_metrics = self.performance_guard.check_status(equity if balance else None)
                    guard_info = self.performance_guard.get_status()
                    
                    # Get regime info (from last processed symbol)
                    regime_info = None
                    if self.candle_data:
                        last_symbol = list(self.candle_data.keys())[-1]
                        df_with_features = self.feature_calc.calculate_indicators(self.candle_data[last_symbol])
                        regime_info = self.regime_filter.classify_regime(df_with_features)
                    
                    # Get model info
                    model_info = {
                        'version': self.config.get('model', {}).get('version', 'unknown'),
                        'age_days': None  # Could calculate from model file timestamp
                    }
                    
                    health_status = self.health_monitor.check_health(
                        bot_running=self.running,
                        open_positions=positions_dict,
                        performance_guard_status=guard_info,
                        regime_info=regime_info,
                        model_info=model_info
                    )
                    
                    # Log health check summary
                    issues = health_status.get('issues', [])
                    warnings = health_status.get('warnings', [])
                    health_status_str = health_status.get('health_status', 'UNKNOWN')
                    
                    log_msg = (
                        f"Health check: status={health_status_str}, "
                        f"positions={len(positions_dict)}, "
                        f"regime={regime_info.get('regime', 'UNKNOWN') if regime_info else 'N/A'}, "
                        f"guard={guard_info.get('status', 'UNKNOWN') if guard_info else 'N/A'}"
                    )
                    
                    if issues:
                        log_msg += f", issues={issues}"
                    if warnings:
                        log_msg += f", warnings={warnings}"
                    
                    if health_status_str in ['DEGRADED', 'UNHEALTHY']:
                        logger.warning(log_msg)
                    else:
                        logger.info(log_msg)
                    
                    # Write status file
                    self.health_monitor.write_status_file(health_status)
                    
                    # Alert on health issues (DEGRADED or UNHEALTHY)
                    if health_status['health_status'] in ['DEGRADED', 'UNHEALTHY']:
                        severity = "CRITICAL" if health_status['health_status'] == 'UNHEALTHY' else "WARNING"
                        self.alert_manager.notify_event(
                            event_type="HEALTH_ISSUE",
                            message=f"Bot health {health_status['health_status'].lower()}",
                            context={
                                'health_status': health_status['health_status'],
                                'issues': health_status['issues'],
                                'warnings': health_status['warnings']
                            },
                            severity=severity
                        )
        
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            self.stop()
        
        finally:
            stream.stop()
            logger.info("Trading bot stopped")
            
            # Print summary
            summary = self.trade_logger.get_summary()
            logger.info("=" * 60)
            logger.info("Trading Summary:")
            logger.info(f"Total PnL: {summary['total_pnl']:.2f} USDT")
            logger.info(f"Daily PnL: {summary['daily_pnl']:.2f} USDT")
            logger.info(f"Trades: {summary['trade_count']}")
            logger.info(f"Win Rate: {summary['win_rate']:.1f}%")
            logger.info("=" * 60)
    
    def stop(self):
        """Stop the trading bot"""
        self.running = False


def signal_handler(sig, frame):
    """Handle interrupt signal"""
    logger.info("Interrupt received, shutting down...")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description='Run live trading bot')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file path')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.add("logs/bot_{time}.log", rotation="1 day", level="INFO")
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start bot
    bot = TradingBot(config_path=args.config)
    bot.start()


if __name__ == "__main__":
    main()
