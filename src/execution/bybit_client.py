"""Bybit API client for order execution"""

from typing import Dict, Optional, List
from pybit.unified_trading import HTTP
from loguru import logger


class BybitClient:
    """Client for Bybit API operations"""
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True
    ):
        """
        Initialize Bybit client.
        
        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            testnet: Use testnet
        """
        self.testnet = testnet
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )
        logger.info(f"Initialized BybitClient (testnet={testnet})")
    
    def get_account_balance(self) -> Dict:
        """
        Get account balance.
        
        Returns:
            Dictionary with account balance information
        """
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
        
        except Exception as e:
            logger.error(f"Exception getting balance: {e}")
            return {}
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open positions.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of position dictionaries
        """
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
                if float(pos.get('size', 0)) != 0:  # Only non-zero positions
                    positions.append({
                        'symbol': pos['symbol'],
                        'side': pos['side'],  # 'Buy' or 'Sell'
                        'size': float(pos['size']),
                        'entry_price': float(pos['avgPrice']),
                        'mark_price': float(pos['markPrice']),
                        'leverage': float(pos.get('leverage', 1)),
                        'unrealized_pnl': float(pos.get('unrealisedPnl', 0)),
                        'liquidation_price': float(pos.get('liqPrice', 0))
                    })
            
            return positions
        
        except Exception as e:
            logger.error(f"Exception getting positions: {e}")
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
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'side': side,
                'orderType': order_type,
                'qty': str(qty),
                'reduceOnly': reduce_only
            }
            
            if order_type == 'Limit' and price:
                params['price'] = str(price)
            
            if stop_loss:
                params['stopLoss'] = str(stop_loss)
            
            if take_profit:
                params['takeProfit'] = str(take_profit)
            
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
        
        except Exception as e:
            logger.error(f"Exception placing order: {e}")
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
        
        except Exception as e:
            logger.error(f"Exception canceling order: {e}")
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open orders (including conditional stop-loss/take-profit orders).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open order dictionaries
        """
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
        
        except Exception as e:
            logger.error(f"Exception getting open orders: {e}")
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

