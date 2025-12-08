"""Bybit API client for order execution"""

import time
from typing import Dict, Optional, List
from pybit.unified_trading import HTTP
from loguru import logger


class BybitClient:
    """Client for Bybit API operations"""
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize Bybit client.
        
        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            testnet: Use testnet
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum retries for failed API requests (default: 3)
        """
        self.testnet = testnet
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )
        logger.info(f"Initialized BybitClient (testnet={testnet}, timeout={timeout}s, max_retries={max_retries})")
    
    def get_account_balance(self) -> Dict:
        """
        Get account balance.
        
        Returns:
            Dictionary with account balance information
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.get_wallet_balance(
                    accountType="UNIFIED"
                )
                
                if response['retCode'] != 0:
                    logger.error(f"Error getting balance: {response.get('retMsg', 'Unknown error')}")
                    return {}
                
                result = response['result']
                if 'list' in result and len(result['list']) > 0:
                    account = result['list'][0]
                    total_equity = float(account.get('totalEquity', 0))
                    available_balance = float(account.get('totalAvailableBalance', 0))
                    
                    return {
                        'total_equity': total_equity,
                        'available_balance': available_balance,
                        'currency': 'USDT'
                    }
                
                return {}
            
            except (TimeoutError, ConnectionError, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s
                    logger.warning(f"Error getting balance (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Exception getting balance after {self.max_retries} attempts: {e}")
                    return {}
        
        return {}
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open positions.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of position dictionaries
        """
        for attempt in range(self.max_retries):
            try:
                # Bybit API requires settleCoin for linear perpetuals
                # Pass parameters directly as keyword arguments
                if symbol:
                    response = self.session.get_positions(
                        category="linear",
                        symbol=symbol,
                        settleCoin="USDT"
                    )
                else:
                    response = self.session.get_positions(
                        category="linear",
                        settleCoin="USDT"
                    )
                
                if response['retCode'] != 0:
                    logger.error(f"Error getting positions: {response.get('retMsg', 'Unknown error')}")
                    return []
                
                positions = []
                for pos in response['result'].get('list', []):
                    # Safely convert size, handling empty strings
                    size_str = pos.get('size', '0')
                    if size_str == '' or size_str is None:
                        continue
                    size = float(size_str)
                    if size != 0:  # Only non-zero positions
                        # Safely convert other fields, using 0 as default for empty strings
                        positions.append({
                            'symbol': pos['symbol'],
                            'side': pos['side'],  # 'Buy' or 'Sell'
                            'size': size,
                            'entry_price': float(pos.get('avgPrice', 0) or 0),
                            'mark_price': float(pos.get('markPrice', 0) or 0),
                            'leverage': float(pos.get('leverage', 1) or 1),
                            'unrealized_pnl': float(pos.get('unrealisedPnl', 0) or 0),
                            'liquidation_price': float(pos.get('liqPrice', 0) or 0)
                        })
                
                return positions
            
            except (TimeoutError, ConnectionError, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s
                    logger.warning(f"Error getting positions (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Exception getting positions after {self.max_retries} attempts: {e}")
                    return []
        
        return []
    
    def place_order(
        self,
        symbol: str,
        side: str,  # 'Buy' or 'Sell'
        order_type: str,  # 'Market' or 'Limit'
        qty: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Place an order.
        
        Args:
            symbol: Trading symbol
            side: 'Buy' or 'Sell'
            order_type: 'Market' or 'Limit'
            qty: Order quantity
            price: Limit price (required for Limit orders)
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            reduce_only: Reduce only flag
            
        Returns:
            Order response dictionary or None if error
        """
        for attempt in range(self.max_retries):
            try:
                # Round quantity to appropriate precision for Bybit
                # Bybit requires quantities to match the lot size filter (qtyStep) for each symbol
                # Try to get instrument info for lot size filter
                rounded_qty = qty
                min_qty = 0.001
                
                try:
                    instrument_info = self.session.get_instruments_info(
                        category="linear",
                        symbol=symbol
                    )
                    if instrument_info.get('retCode') == 0:
                        result = instrument_info.get('result', {})
                        if 'list' in result and len(result['list']) > 0:
                            lot_size_filter = result['list'][0].get('lotSizeFilter', {})
                            qty_step = float(lot_size_filter.get('qtyStep', '0.001'))
                            min_qty = float(lot_size_filter.get('minOrderQty', '0.001'))
                            min_notional = float(lot_size_filter.get('minNotionalValue', '5.0'))
                            
                            # Round to the nearest multiple of qty_step
                            rounded_qty = round(qty / qty_step) * qty_step
                            # Ensure it's at least minOrderQty
                            if rounded_qty < min_qty:
                                rounded_qty = min_qty
                            
                            logger.debug(f"Using lot size step {qty_step} for {symbol}, minNotional={min_notional}, rounded {qty:.6f} -> {rounded_qty:.6f}")
                        else:
                            # Fallback: round to 3 decimals
                            rounded_qty = round(qty, 3)
                    else:
                        # Fallback: round to 3 decimals
                        rounded_qty = round(qty, 3)
                except Exception as e:
                    # Fallback: round to 3 decimals if we can't get instrument info
                    logger.debug(f"Could not get instrument info for {symbol}: {e}, using default rounding to 3 decimals")
                    rounded_qty = round(qty, 3)
                
                # Ensure minimum order size
                if rounded_qty < min_qty:
                    logger.error(f"Quantity {rounded_qty} is below minimum order size ({min_qty})")
                    return None
                
                # Format quantity string to remove unnecessary decimals
                # Convert to string and remove trailing zeros
                qty_str = f"{rounded_qty:.10f}".rstrip('0').rstrip('.')
                
                params = {
                    'category': 'linear',
                    'symbol': symbol,
                    'side': side,
                    'orderType': order_type,
                    'qty': qty_str,  # Use formatted quantity string
                    'reduceOnly': reduce_only
                }
                
                if order_type == 'Limit' and price:
                    params['price'] = str(price)
                
                if stop_loss:
                    # Round stop loss to reasonable precision
                    params['stopLoss'] = str(round(stop_loss, 8))
                
                if take_profit:
                    # Round take profit to reasonable precision
                    params['takeProfit'] = str(round(take_profit, 8))
                
                response = self.session.place_order(**params)
                
                if response['retCode'] != 0:
                    logger.error(f"Error placing order: {response.get('retMsg', 'Unknown error')}")
                    return None
                
                order_id = response['result'].get('orderId', '')
                logger.info(f"Placed {side} order for {qty} {symbol}: {order_id}")
                
                return {
                    'order_id': order_id,
                    'symbol': symbol,
                    'side': side,
                    'qty': qty,
                    'status': 'New'
                }
            
            except (TimeoutError, ConnectionError, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s
                    logger.warning(f"Error placing order (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Exception placing order after {self.max_retries} attempts: {e}")
                    return None
        
        return None
    
    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None
    ) -> bool:
        """
        Cancel an order.
        
        Args:
            symbol: Trading symbol
            order_id: Optional order ID (if None, cancels all open orders for symbol)
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                params = {
                    'category': 'linear',
                    'symbol': symbol
                }
                
                if order_id:
                    params['orderId'] = order_id
                
                response = self.session.cancel_order(**params)
                
                if response['retCode'] != 0:
                    logger.error(f"Error canceling order: {response.get('retMsg', 'Unknown error')}")
                    return False
                
                logger.info(f"Canceled order for {symbol}")
                return True
            
            except (TimeoutError, ConnectionError, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s
                    logger.warning(f"Error canceling order (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Exception canceling order after {self.max_retries} attempts: {e}")
                    return False
        
        return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open orders (including conditional stop-loss/take-profit orders).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open order dictionaries
        """
        for attempt in range(self.max_retries):
            try:
                params = {
                    'category': 'linear',
                    'settleCoin': 'USDT'
                }
                if symbol:
                    params['symbol'] = symbol
                
                response = self.session.get_open_orders(**params)
                
                if response['retCode'] != 0:
                    logger.error(f"Error getting open orders: {response.get('retMsg', 'Unknown error')}")
                    return []
                
                orders = []
                for order in response['result'].get('list', []):
                    orders.append({
                        'order_id': order.get('orderId', ''),
                        'symbol': order.get('symbol', ''),
                        'side': order.get('side', ''),
                        'order_type': order.get('orderType', ''),
                        'qty': float(order.get('qty', 0)),
                        'price': float(order.get('price', 0)) if order.get('price') else None,
                        'stop_loss': float(order.get('stopLoss', 0)) if order.get('stopLoss') else None,
                        'take_profit': float(order.get('takeProfit', 0)) if order.get('takeProfit') else None,
                        'trigger_price': float(order.get('triggerPrice', 0)) if order.get('triggerPrice') else None,
                        'order_status': order.get('orderStatus', '')
                    })
                
                return orders
            
            except (TimeoutError, ConnectionError, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s
                    logger.warning(f"Error getting open orders (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Exception getting open orders after {self.max_retries} attempts: {e}")
                    return []
        
        return []
    
    def set_leverage(
        self,
        symbol: str,
        leverage: int
    ) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage value (1-200)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.session.set_leverage(
                category='linear',
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            
            if response['retCode'] != 0:
                error_msg = response.get('retMsg', 'Unknown error')
                # Log as debug to reduce noise (permission errors are common)
                logger.debug(f"Could not set leverage for {symbol}: {error_msg}")
                return False
            
            logger.debug(f"Set leverage to {leverage}x for {symbol}")
            return True
        
        except Exception as e:
            # Log as debug to reduce noise
            logger.debug(f"Exception setting leverage for {symbol}: {e}")
            return False

