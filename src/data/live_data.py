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
            topic = message.get('topic', '')
            
            if 'kline' in topic:
                data = message.get('data', [])
                if data:
                    kline = data[0]
                    symbol = kline['symbol']
                    
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
                    
                    # Call callback if candle is closed
                    if candle['is_closed'] and self.callback:
                        df = pd.DataFrame([candle])
                        self.callback(df)
                        logger.debug(f"New closed candle for {symbol}: {candle['close']}")
        
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    def start(self):
        """Start WebSocket connection and subscribe to streams"""
        try:
            # Create WebSocket instance
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type="linear"
            )
            
            # Subscribe to kline streams
            topics = [f"kline.{self.interval}.{symbol}" for symbol in self.symbols]
            
            self.ws.kline_stream(
                callback=self._handle_message,
                symbol=self.symbols[0] if len(self.symbols) == 1 else None
            )
            
            # Subscribe to additional symbols if needed
            for symbol in self.symbols[1:]:
                self.ws.kline_stream(
                    callback=self._handle_message,
                    symbol=symbol
                )
            
            self.running = True
            logger.info(f"Started WebSocket stream for {self.symbols}")
            
        except Exception as e:
            logger.error(f"Error starting WebSocket: {e}")
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

