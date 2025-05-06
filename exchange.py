import ccxt
import os
import time
import pandas as pd
import numpy as np
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
    
    def check_price_gain(self, df, days=None):
        """
        Check if price has gained more than min_price_gain% within a rolling window.
        This function searches for the maximum gain from any low to any subsequent high
        within the specified period. Optimized for performance.
        
        Args:
            df: DataFrame with OHLC data
            days: Number of days to look back (uses self.lookback_days if None)
                
        Returns:
            Tuple of (has_gained, gain_pct, low_price, high_price, low_idx, high_idx)
        """
        try:
            if days is None:
                days = self.lookback_days

            if df is None or len(df) < 10:  # Need some minimal data
                return False, 0.0, None, None, None, None

            # Calculate candles per day for 5-min timeframe
            candles_per_day = int(24 * 60 / 5)  # 288 candles per day

            # Calculate how many candles to look back
            lookback_candles = candles_per_day * days

            # Limit to available data
            actual_lookback = min(lookback_candles, len(df) - 1)

            # Get recent data to analyze
            recent_data = df.iloc[-actual_lookback:]

            # Extract necessary data as NumPy arrays for faster processing
            lows = recent_data['low'].values
            highs = recent_data['high'].values
            indices = recent_data.index

            n = len(lows)

            # Use NumPy to find the maximum possible gain
            max_gain_pct = 0.0
            best_low_price = None
            best_high_price = None
            best_low_idx = None
            best_high_idx = None

            # For each potential low point
            for i in range(n - 1):
                low_price = lows[i]
                low_idx = indices[i]

                # Skip invalid low prices
                if low_price <= 0:
                    continue

                # Use vectorized operations for all subsequent high prices
                subsequent_highs = highs[i+1:]
                subsequent_indices = indices[i+1:]

                # Calculate gain percentages for all subsequent highs in one operation
                gains = ((subsequent_highs - low_price) / low_price) * 100

                if len(gains) > 0:
                    # Find the maximum gain and its index
                    max_gain_idx = np.argmax(gains)
                    current_max_gain = gains[max_gain_idx]

                    # Update if we found a better gain
                    if current_max_gain > max_gain_pct:
                        max_gain_pct = current_max_gain
                        best_low_price = low_price
                        best_high_price = subsequent_highs[max_gain_idx]
                        best_low_idx = low_idx
                        best_high_idx = subsequent_indices[max_gain_idx]

                        # If we've found a gain that significantly exceeds our criteria, we can stop early
                        if max_gain_pct >= self.min_price_gain * 1.5:
                            break

            # Check if gain exceeds minimum threshold
            has_gained = max_gain_pct >= self.min_price_gain

            # logger.debug(f"{self.symbol}: Maximum gain found: {max_gain_pct:.2f}% "
            #             f"from {best_low_price:.6f} to {best_high_price:.6f}")

            return has_gained, max_gain_pct, best_low_price, best_high_price, best_low_idx, best_high_idx

        except Exception as e:
            logger.info(f"Error while checking price gain for {self.symbol}: {e}")
            return False, 0.0, None, None, None, None
    
    def fetch_active_symbols(self):
        """Fetch symbols that had ~20% movement and are now stable."""
        try:
            # Get market data
            ticker_data = self.exchange.fetch_tickers()
            markets = self.exchange.load_markets()
            
            active_markets = [
                symbol for symbol, market in markets.items()
                if market.get('settle') == 'USDT' and market.get('swap') and 'BTC' not in symbol and 'ETH' not in symbol
            ]
            
            active_markets_with_volume = [
                symbol for symbol in active_markets 
                if symbol in ticker_data and ticker_data[symbol].get('quoteVolume', 0) > 75000
            ]
            
            # Time frames
            now = int(time.time() * 1000)
            stability_period = now - (4 * 60 * 60 * 1000)  # 4 hours for stability check
            history_period = now - (14 * 24 * 60 * 60 * 1000)  # 14 days for historical movement
            
            pre_filtered_symbols = sorted(
                active_markets_with_volume,
                key=lambda x: ticker_data[x].get('quoteVolume', 0),
                reverse=True
            )[:100]
            
            logger.info(f"Analyzing {len(pre_filtered_symbols)} markets for movement + stability")
            
            suitable_symbols = []
            target_movement_pct = 20.0
            movement_margin = 5.0  # Accept 15-25% movement
            
            for symbol in pre_filtered_symbols:
                try:
                    time.sleep(0.1)
                    
                    # PART 1: Check historical significant movement
                    history_ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='4h', since=history_period, limit=84)
                    if not history_ohlcv or len(history_ohlcv) < 30:
                        continue
                    
                    # Convert to simple arrays for faster processing
                    highs = [candle[2] for candle in history_ohlcv]
                    lows = [candle[3] for candle in history_ohlcv]
                    
                    # Find max gain and loss
                    max_gain_pct = 0
                    max_loss_pct = 0
                    
                    # Calculate maximum gain (from any low to subsequent high)
                    for i in range(len(lows) - 5):  # At least 5 candles between points
                        low_price = lows[i]
                        if low_price <= 0:
                            continue
                            
                        for j in range(i + 5, len(highs)):
                            gain_pct = (highs[j] - low_price) / low_price * 100
                            max_gain_pct = max(max_gain_pct, gain_pct)
                    
                    # Calculate maximum loss (from any high to subsequent low)
                    for i in range(len(highs) - 5):
                        high_price = highs[i]
                        if high_price <= 0:
                            continue
                            
                        for j in range(i + 5, len(lows)):
                            loss_pct = (lows[j] - high_price) / high_price * 100
                            max_loss_pct = min(max_loss_pct, loss_pct)
                    
                    # Determine primary movement
                    movement_type = "gain" if max_gain_pct >= abs(max_loss_pct) else "loss"
                    movement_pct = max_gain_pct if movement_type == "gain" else abs(max_loss_pct)
                    
                    # Check if movement is within target range
                    if not (target_movement_pct - movement_margin <= movement_pct <= target_movement_pct + movement_margin):
                        continue
                    
                    # PART 2: Verify CURRENT stability
                    recent_ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='5m', since=stability_period, limit=48)
                    if not recent_ohlcv or len(recent_ohlcv) < 20:
                        continue
                    
                    # Extract recent prices
                    recent_highs = [candle[2] for candle in recent_ohlcv]
                    recent_lows = [candle[3] for candle in recent_ohlcv]
                    recent_closes = [candle[4] for candle in recent_ohlcv]
                    
                    # Calculate stability metrics
                    current_range_pct = (max(recent_highs) - min(recent_lows)) / (sum(recent_closes) / len(recent_closes)) * 100
                    
                    # Check candle sizes
                    candle_sizes = [(recent_highs[i] - recent_lows[i]) / recent_closes[i] * 100 
                                for i in range(len(recent_ohlcv))]
                    avg_candle_size = sum(candle_sizes) / len(candle_sizes)
                    max_candle_size = max(candle_sizes)
                    
                    # Calculate price changes between candles
                    price_changes = [abs((recent_closes[i] - recent_closes[i-1]) / recent_closes[i-1] * 100) 
                                    for i in range(1, len(recent_closes))]
                    max_price_change = max(price_changes)
                    
                    # STRICT stability criteria - must meet ALL conditions
                    is_stable = (
                        current_range_pct < 4.0 and  # Less than 4% total range in recent period
                        avg_candle_size < 0.7 and    # Average candle size under 0.7%
                        max_candle_size < 1.5 and    # No single candle over 1.5%
                        max_price_change < 0.8       # No sharp price changes over 0.8%
                    )
                    
                    if not is_stable:
                        continue
                    
                    # Symbol passed both significant movement AND current stability
                    stability_score = (
                        0.4 * current_range_pct/4.0 +    # Normalized range (0-1)
                        0.3 * avg_candle_size/0.7 +      # Normalized avg candle (0-1)
                        0.2 * max_candle_size/1.5 +      # Normalized max candle (0-1)
                        0.1 * max_price_change/0.8       # Normalized price change (0-1)
                    )
                    
                    suitable_symbols.append({
                        'symbol': symbol,
                        'stability_score': stability_score,
                        'movement_type': movement_type,
                        'movement_pct': movement_pct,
                        'current_range': current_range_pct,
                        'avg_candle': avg_candle_size,
                        'max_candle': max_candle_size
                    })
                    
                except Exception as e:
                    logger.debug(f"Error analyzing {symbol}: {e}")
                    continue
            
            if not suitable_symbols:
                logger.warning("No symbols found with significant movement and current stability")
                return []
            
            # Sort by stability (most stable first)
            sorted_symbols = sorted(suitable_symbols, key=lambda x: x['stability_score'])
            
            # Take top 30 most stable symbols that had significant movement
            result_symbols = [item['symbol'] for item in sorted_symbols[:30]]
            
            # Log the results
            for i, item in enumerate(sorted_symbols[:10]):
                logger.info(
                    f"{i+1}. {item['symbol']}: {item['movement_type'].capitalize()}={item['movement_pct']:.1f}%, "
                    f"Now Stable: Range={item['current_range']:.2f}%, "
                    f"AvgCandle={item['avg_candle']:.2f}%"
                )
            
            return result_symbols
            
        except Exception as e:
            logger.exception(f"Error finding suitable symbols: {e}")
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
            
    def fetch_binance_data(self, market_id, timeframe='5m', limit=100, include_current=True):
        """
        Fetch OHLCV data from Binance with proper timestamp handling.
        
        Args:
            market_id (str): The trading pair symbol
            timeframe (str): Timeframe for candles (e.g., '1m', '5m', '1h')
            limit (int): Maximum number of candles to return
            include_current (bool): Whether to include the current (potentially incomplete) candle
            
        Returns:
            pandas.DataFrame: DataFrame with OHLCV data
        """
        try:
            # Fetch data - increase the limit to ensure we have enough after processing
            actual_fetch_limit = limit * 2  # Double the requested limit to account for potential losses
            ohlcv = self.exchange.fetch_ohlcv(market_id, timeframe=timeframe, limit=actual_fetch_limit)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            
            # Check for duplicate timestamps
            duplicates = df['timestamp'].duplicated()
            if duplicates.any():
                logger.debug(f"Removed {duplicates.sum()} duplicate timestamps for {market_id}")
                df = df.drop_duplicates(subset=['timestamp'], keep='first')
            
            # Now set the timestamp as index after removing duplicates
            df.set_index('timestamp', inplace=True)
            
            # Convert columns to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Drop rows with NaN values
            df.dropna(inplace=True)
            
            # Verify the index is still unique after all processing
            if df.index.duplicated().any():
                df = df[~df.index.duplicated(keep='first')]
            
            # Identify current candle
            current_candle_timestamp = None
            if len(df) > 0:
                tf_ms = ccxt.Exchange.parse_timeframe(timeframe) * 1000
                current_time_ms = int(time.time() * 1000)
                current_candle_start = current_time_ms - (current_time_ms % tf_ms)
                
                # Mark candles with is_current_candle flag
                df['is_current_candle'] = False
                
                # Convert index to timestamp in milliseconds
                df['timestamp_ms'] = df.index.astype(np.int64) // 10**6
                
                # Find the current candle
                current_candle_mask = df['timestamp_ms'] >= current_candle_start
                if current_candle_mask.any():
                    df.loc[current_candle_mask, 'is_current_candle'] = True
                    current_candle_idx = df[current_candle_mask].index[0]
                    current_candle_timestamp = pd.Timestamp(current_candle_start, unit='ms', tz='UTC')
                    logger.debug(f"Current candle for {market_id} identified at {current_candle_timestamp}")
                
                # Clean up temporary column
                df.drop('timestamp_ms', axis=1, inplace=True)
            
            # If requested, remove the most recent (potentially incomplete) candle
            if not include_current and 'is_current_candle' in df.columns:
                prev_len = len(df)
                df = df[~df['is_current_candle']]
                if len(df) < prev_len:
                    logger.debug(f"Removed current candle for {market_id} (include_current=False)")
            
            # Return only the requested number of candles (from the end)
            if len(df) > limit:
                df = df.iloc[-limit:]
            
            logger.debug(f"Fetched {len(df)} candles for {market_id}, current candle included: {include_current}")
            return df
            
        except Exception as e:
            logger.exception(f"Failed to fetch data for {market_id}: {e}")
            return pd.DataFrame()
