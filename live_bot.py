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
from datetime import datetime
from typing import Optional
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
            testnet=exchange_config.get('testnet', True)
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
                queue_data['queued_at'][symbol] = datetime.utcnow().isoformat()
            
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
        
        logger.info(f"New candle for {symbol}: {timestamp} | Close: {df['close'].iloc[0]}")
        
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
        self._process_signal(symbol)
    
    def _process_signal(self, symbol: str):
        """Process trading signal for a symbol"""
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
        
        if symbol not in self.candle_data:
            return
        
        df = self.candle_data[symbol]
        
        if len(df) < 50:  # Need enough history
            return
        
        try:
            # Calculate features
            df_with_features = self.feature_calc.calculate_indicators(df)
            
            # Generate primary signal
            primary_signal = self.primary_signal_gen.generate_signal(df_with_features)
            
            # Log signal generation for visibility
            if primary_signal['direction'] == 'NEUTRAL':
                # Log occasionally to show the bot is evaluating signals
                import random
                if random.random() < 0.05:  # 5% chance to log NEUTRAL signals (reduce spam)
                    logger.debug(f"[{symbol}] Signal evaluation: NEUTRAL (no trend signal detected)")
                return
            
            # Log non-neutral signals (these are candidates for trading)
            logger.info(
                f"[{symbol}] ✓ Primary signal generated: {primary_signal['direction']} "
                f"(strength: {primary_signal.get('strength', 'N/A')}) - Evaluating filters..."
            )
            
            # Regime filter check
            regime_allowed, regime_reason, regime_multiplier = self.regime_filter.should_allow_trade(
                df_with_features,
                primary_signal['direction']
            )
            
            if not regime_allowed:
                logger.info(f"Signal filtered by regime: {regime_reason}")
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
                    logger.info(f"Symbol {symbol} not selected by portfolio selector. Skipping.")
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
                logger.warning(f"Trading paused by performance guard: {guard_reason}")
                # Send alert
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
            
            # Log signal evaluation
            logger.info(
                f"[{symbol}] Signal evaluation: {primary_signal['direction']} | "
                f"Confidence: {confidence:.3f} | "
                f"Threshold: {adjusted_threshold:.3f} (base: {base_threshold:.3f} + adj: {confidence_adjustment:.3f}) | "
                f"Regime: {regime_reason if 'regime_reason' in locals() else 'OK'}"
            )
            
            # Log signal to trade logger
            self.trade_logger.log_signal(
                symbol=symbol,
                direction=primary_signal['direction'],
                confidence=confidence,
                features=meta_features
            )
            
            # Check confidence threshold
            if confidence < adjusted_threshold:
                logger.info(
                    f"[{symbol}] Signal filtered: confidence {confidence:.3f} < threshold {adjusted_threshold:.3f} "
                    f"(needs {adjusted_threshold - confidence:.3f} more confidence)"
                )
                return
            
            # Log that signal passed all filters and will attempt trade
            logger.info(
                f"[{symbol}] ✓ Signal passed all filters! Attempting trade: {primary_signal['direction']} "
                f"@ {df_with_features['close'].iloc[-1]:.2f} (confidence: {confidence:.3f})"
            )
            
            # Get volatility for position sizing (before execute_trade)
            current_volatility = None
            if 'volatility' in df_with_features.columns:
                current_volatility = df_with_features['volatility'].iloc[-1]
            
            # Execute trade
            self._execute_trade(
                symbol=symbol,
                direction=primary_signal['direction'],
                confidence=confidence,
                current_price=df_with_features['close'].iloc[-1],
                current_volatility=current_volatility,
                regime_multiplier=regime_multiplier
            )
        
        except Exception as e:
            logger.error(f"Error processing signal for {symbol}: {e}")
            self.trade_logger.log_error("SIGNAL_PROCESSING", str(e))
    
    def _execute_trade(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        current_price: float,
        current_volatility: Optional[float] = None,
        regime_multiplier: float = 1.0
    ):
        """Execute a trade"""
        try:
            # Get account balance
            balance = self.bybit_client.get_account_balance()
            if not balance:
                logger.error("Could not get account balance")
                return
            
            equity = balance['total_equity']
            
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
            
            # Check risk limits (use final position size)
            is_allowed, reason = self.risk_manager.check_risk_limits(
                equity=equity,
                open_positions=open_positions,
                symbol=symbol,
                proposed_size=final_position_size
            )
            
            if not is_allowed:
                logger.warning(f"Trade not allowed: {reason}")
                return
            
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
                self.health_monitor.update_trade(datetime.utcnow())
                
                # Track position
                self.positions[symbol] = {
                    'entry_price': current_price,
                    'side': side,
                    'qty': final_position_size,
                    'entry_time': datetime.utcnow(),
                    'stop_loss': stop_loss,
                    'take_profit': take_profit
                }
        
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            self.trade_logger.log_error("TRADE_EXECUTION", str(e))
    
    def _monitor_positions(self):
        """
        Monitor open positions and check exit conditions.
        Also reconciles with exchange state to handle positions closed externally.
        """
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
                    exit_time=datetime.utcnow()
                )
                
                # Update risk manager and performance guard
                self.risk_manager.update_daily_pnl(pnl)
                self.performance_guard.record_trade(pnl, pnl > 0)
                
                # Update health monitor
                self.health_monitor.update_trade(datetime.utcnow())
                
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
        
        stream = LiveDataStream(
            symbols=symbols,
            interval="60",  # 1 hour
            testnet=self.config['exchange'].get('testnet', True),
            callback=on_candle
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
        logger.info("Signals are only processed when candles CLOSE. Open candle updates are received but not processed.")
        
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
                    logger.info(
                        f"Health check: status={health_status.get('health_status', 'UNKNOWN')}, "
                        f"positions={len(positions_dict)}, "
                        f"regime={regime_info.get('regime', 'UNKNOWN') if regime_info else 'N/A'}, "
                        f"guard={guard_info.get('status', 'UNKNOWN') if guard_info else 'N/A'}"
                    )
                    
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

