"""Live data streaming from Bybit WebSocket"""

import json
import time
import threading
from queue import Queue
from typing import Optional, Callable
from datetime import datetime
from pybit.unified_trading import WebSocket
from loguru import logger
import pandas as pd


class LiveDataStream:
    """Stream live market data from Bybit WebSocket"""
    
    def __init__(
        self,
        symbols: list,
        interval: str = "60",  # 60 = 1 hour
        testnet: bool = True,
        callback: Optional[Callable] = None
    ):
        """
        Initialize live data stream.
        
        Args:
            symbols: List of trading symbols to subscribe to
            interval: Kline interval ("60" = 1h, "240" = 4h)
            testnet: Use testnet WebSocket
            callback: Callback function for new candles (receives DataFrame)
        """
        self.symbols = symbols
        self.interval = interval
        self.testnet = testnet
        self.callback = callback
        self.ws = None
        self.running = False
        self.candle_buffer = {}  # Store latest candle per symbol
        
        # Determine WebSocket URL
        if testnet:
            self.ws_url = "wss://stream-testnet.bybit.com/v5/public/linear"
        else:
            self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        
        logger.info(f"Initialized LiveDataStream for {symbols} (testnet={testnet})")
    
    def _handle_message(self, message: dict):
        """Handle incoming WebSocket message"""
        try:
            # Log first message to verify connection is working
            if not hasattr(self, '_first_message_logged'):
                logger.info(f"WebSocket connection active - received first message: {message.get('topic', 'unknown')}")
                self._first_message_logged = True
            
            topic = message.get('topic', '')
            
            # Handle ping/pong messages (pybit may send these)
            if 'ping' in topic.lower() or message.get('op') == 'ping':
                logger.debug("Received ping message")
                return
            
            if 'kline' in topic:
                data = message.get('data', [])
                if not data:
                    logger.debug(f"Received kline message with empty data: {message}")
                    return
                
                # Handle both list and dict formats
                if isinstance(data, list):
                    if len(data) == 0:
                        return
                    kline = data[0]
                else:
                    kline = data
                
                # Extract symbol from kline data or topic
                # Topic format: "kline.{interval}.{symbol}" or symbol might be in kline dict
                symbol = kline.get('symbol')
                if not symbol:
                    # Try to extract from topic: "kline.60.BTCUSDT"
                    topic_parts = topic.split('.')
                    if len(topic_parts) >= 3:
                        symbol = topic_parts[-1]  # Last part is symbol
                
                if not symbol:
                    logger.warning(f"Could not extract symbol from message: topic={topic}, data_keys={list(kline.keys()) if isinstance(kline, dict) else 'not_dict'}")
                    return
                
                # Convert to DataFrame format
                candle = {
                    'timestamp': pd.to_datetime(int(kline['start']), unit='ms'),
                    'open': float(kline['open']),
                    'high': float(kline['high']),
                    'low': float(kline['low']),
                    'close': float(kline['close']),
                    'volume': float(kline['volume']),
                    'turnover': float(kline.get('turnover', 0)),
                    'symbol': symbol,
                    'timeframe': self.interval,
                    'is_closed': kline.get('confirm', False)  # True when candle closes
                }
                
                # Update buffer
                self.candle_buffer[symbol] = candle
                
                # Log all closed candles (for debugging - can reduce later)
                if candle['is_closed']:
                    logger.info(f"Closed candle for {symbol}: {candle['close']:.2f} @ {candle['timestamp']}")
                    if self.callback:
                        df = pd.DataFrame([candle])
                        self.callback(df)
                else:
                    # Log open candle updates occasionally (every 10th update per symbol)
                    if not hasattr(self, '_open_candle_count'):
                        self._open_candle_count = {}
                    self._open_candle_count[symbol] = self._open_candle_count.get(symbol, 0) + 1
                    if self._open_candle_count[symbol] % 10 == 0:
                        logger.debug(f"Open candle update for {symbol}: {candle['close']:.2f}")
        
        except KeyError as e:
            # Log more details about the message structure for debugging
            logger.error(
                f"KeyError handling WebSocket message: {e}. "
                f"Topic: {message.get('topic', 'N/A')}, "
                f"Data type: {type(message.get('data'))}, "
                f"Data keys: {list(message.get('data', [{}])[0].keys()) if message.get('data') and isinstance(message.get('data'), list) and len(message.get('data')) > 0 else 'N/A'}"
            )
        except Exception as e:
            logger.error(
                f"Error handling WebSocket message: {e}. "
                f"Message type: {type(message)}, "
                f"Message keys: {list(message.keys()) if isinstance(message, dict) else 'N/A'}, "
                f"Full message: {message}"
            )
    
    def start(self):
        """Start WebSocket connection and subscribe to streams"""
        try:
            # Create WebSocket instance
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type="linear"
            )
            
            # Subscribe to kline streams
            # For pybit WebSocket, we need to subscribe to each symbol with interval
            subscribed_count = 0
            for symbol in self.symbols:
                try:
                    self.ws.kline_stream(
                        callback=self._handle_message,
                        symbol=symbol,
                        interval=self.interval  # Required parameter
                    )
                    subscribed_count += 1
                    logger.debug(f"Subscribed to {symbol} kline stream")
                except Exception as e:
                    logger.error(f"Failed to subscribe to {symbol}: {e}")
            
            if subscribed_count == 0:
                logger.error("Failed to subscribe to any symbols!")
                self.running = False
                return
            
            self.running = True
            logger.info(f"Started WebSocket stream for {subscribed_count}/{len(self.symbols)} symbols")
            
            # Log a warning if not all symbols were subscribed
            if subscribed_count < len(self.symbols):
                logger.warning(f"Only subscribed to {subscribed_count} out of {len(self.symbols)} symbols")
            
        except Exception as e:
            logger.error(f"Error starting WebSocket: {e}", exc_info=True)
            self.running = False
    
    def stop(self):
        """Stop WebSocket connection"""
        if self.ws:
            try:
                self.ws.exit()
            except:
                pass
        
        self.running = False
        logger.info("Stopped WebSocket stream")
    
    def get_latest_candle(self, symbol: str) -> Optional[dict]:
        """Get the latest candle for a symbol"""
        return self.candle_buffer.get(symbol)
    
    def is_running(self) -> bool:
        """Check if stream is running"""
        return self.running

