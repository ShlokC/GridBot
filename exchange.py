import ccxt
import os
import time
import pandas as pd
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('exchange')

class ExchangeClient:
    def __init__(self, exchange='binance', api_key=None, api_secret=None):
        self.exchange_id = exchange
        self.api_key = api_key or os.getenv('BINANCE_API_KEY')
        self.api_secret = api_secret or os.getenv('BINANCE_SECRET_KEY')
        self.exchange = self._create_exchange()
    
    def _create_exchange(self):
        return ccxt.binanceusdm({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
            'timeout': 30000
        })
    
    def fetch_active_symbols(self):
        """Fetch active trading symbols sorted by price gain in last 1hr using 5min rolling candles."""
        try:
            # First get ticker data to pre-filter markets
            ticker_data = self.exchange.fetch_tickers()
            markets = self.exchange.load_markets()
            
            # Filter markets that are USDT-settled swaps, excluding BTC and ETH
            active_markets = [
                symbol for symbol, market in markets.items()
                if market.get('settle') == 'USDT' and market.get('swap') and 'BTC' not in symbol and 'ETH' not in symbol
            ]
            
            # Pre-filter by some minimal volume to avoid processing very illiquid markets
            active_markets_with_volume = [
                symbol for symbol in active_markets 
                if symbol in ticker_data and ticker_data[symbol].get('quoteVolume', 0) > 50000  # Minimum $50K volume
            ]
            
            # Dictionary to store price change metrics
            price_changes = {}
            
            # Get the current time for accurate calculation
            now = int(time.time() * 1000)  # Current time in milliseconds
            one_hour_ago = now - (2* 60 * 60 * 1000)  # two hour ago in milliseconds
            
            # Limit processing to top 100 by volume initially to avoid excessive API calls
            pre_filtered_symbols = sorted(
                active_markets_with_volume,
                key=lambda x: ticker_data[x].get('quoteVolume', 0),
                reverse=True
            )[:100]  # Pre-limit to top 100 by volume
            
            logger.info(f"Calculating 2hr rolling price gains for {len(pre_filtered_symbols)} markets")
            
            # For each market, calculate price change
            for symbol in pre_filtered_symbols:
                try:
                    # Add slight delay to avoid rate limits
                    time.sleep(0.1)
                    
                    # Fetch 5-minute candles for the last hour (plus buffer)
                    ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='5m', since=one_hour_ago, limit=20)
                    
                    if not ohlcv or len(ohlcv) < 6:  # Need enough candles for meaningful calculation
                        continue
                    
                    # Convert to DataFrame for easier manipulation
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Ensure we have data from the last hour
                    df = df[df['timestamp'] >= one_hour_ago]
                    
                    if len(df) < 6:  # Double-check we have enough data after filtering
                        continue
                    
                    # Calculate rolling price with 5-minute candles
                    df['rolling_close'] = df['close'].rolling(window=3).mean()
                    df = df.dropna()  # Remove NaN values at the beginning
                    
                    if len(df) < 3:  # Need enough data after dropping NaNs
                        continue
                    
                    # Calculate percentage change in price from first to last of the hour
                    first_price = df['close'].iloc[0]
                    last_price = df['close'].iloc[-1]
                    
                    if first_price <= 0:  # Avoid division by zero
                        continue
                        
                    price_change_pct = ((last_price - first_price) / first_price) * 100
                    
                    # Store the result
                    price_changes[symbol] = price_change_pct
                    
                except Exception as e:
                    logger.debug(f"Error calculating price change for {symbol}: {e}")
                    continue
            
            # Sort symbols by price change percentage (highest first)
            sorted_symbols = sorted(
                price_changes.keys(),
                key=lambda x: price_changes[x],
                reverse=True
            )
            
            # Take top 50
            top_symbols = sorted_symbols[:50]
            
            # Log the top symbols with their price change percentage
            for i, symbol in enumerate(top_symbols[:10]):  # Log just top 10 for brevity
                logger.info(f"{i+1}. {symbol}: 2hr Price Change: {price_changes[symbol]:.2f}%")
            
            return top_symbols
        
        except Exception as e:
            logger.exception(f"Error fetching active symbols: {e}")
            return []
    
    def get_balance(self):
        """Fetch account balance."""
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            logger.exception(f"Error fetching balance: {e}")
            return {}
    
    def create_order(self, symbol, order_type, side, amount, price=None):
        """Create a new order."""
        try:
            return self.exchange.create_order(symbol, order_type, side, amount, price)
        except Exception as e:
            logger.exception(f"Error creating order: {e}")
            return None
    
    def cancel_order(self, order_id, symbol):
        """Cancel an existing order."""
        try:
            return self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.exception(f"Error canceling order: {e}")
            return None
    
    def fetch_ticker(self, symbol):
        """Fetch current ticker for a symbol."""
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.exception(f"Error fetching ticker for {symbol}: {e}")
            return None
    
    def fetch_ohlcv(self, symbol, timeframe='5m', since=None, limit=None):
        """Fetch OHLCV data for a symbol."""
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        except Exception as e:
            logger.exception(f"Error fetching OHLCV for {symbol}: {e}")
            return []
    
    def fetch_order_status(self, order_id, symbol):
        """Fetch the status of an order."""
        try:
            return self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.exception(f"Error fetching order status for {order_id}: {e}")
            return None
