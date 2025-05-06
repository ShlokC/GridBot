import numpy as np
import pandas as pd
import logging
import time
from exchange import ExchangeClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('grid_logic')

class GridBot:
    def __init__(self, config, exchange_client=None):
        """
        Initialize the Grid Trading Bot with configuration
        
        Args:
            config (dict): Configuration parameters for the grid bot
            exchange_client (ExchangeClient, optional): Exchange client instance
        """
        self.config = config
        self.exchange = exchange_client or ExchangeClient()
        self.symbol = config['symbol']
        self.direction = config['direction']
        
        # Configure price range
        self.lower_price = float(config['price_range']['lower']) if config['price_range']['lower'] else 0
        self.upper_price = float(config['price_range']['upper']) if config['price_range']['upper'] else 0
        
        # Grid configuration
        self.grid_number = int(config['grid']['number']) if config['grid']['number'] else 10
        self.grid_type = config['grid']['type']  # 'Arithmetic' or 'Geometric'
        
        # Investment details
        self.currency = config['investment']['currency']
        self.leverage = config['investment']['leverage'].replace('x', '')  # Remove 'x' to get the numeric value
        self.leverage = float(self.leverage)
        self.investment_percentage = config['investment']['amount']  # This is a percentage value
        
        # Track orders and grid levels
        self.grid_levels = []
        self.active_orders = {}
        
        # Support and resistance levels
        self.support_levels = []
        self.resistance_levels = []
        
    def analyze_market(self, timeframe='5m', limit=288):
        """
        Analyze market to identify support and resistance levels using direct price methods
        
        Args:
            timeframe (str): Timeframe for analysis (e.g., '5m', '15m', '1h')
            limit (int): Number of candles to analyze
            
        Returns:
            tuple: (support_levels, resistance_levels)
        """
        logger.info(f"Analyzing market data for {self.symbol} on {timeframe} timeframe")
        
        # Fetch historical data
        df = self.exchange.fetch_binance_data(self.symbol, timeframe=timeframe, limit=limit, include_current=False)
        
        if df.empty:
            logger.warning(f"No data retrieved for {self.symbol}")
            return [], []
        
        # Get current price to reference against
        ticker = self.exchange.fetch_ticker(self.symbol)
        if not ticker or 'last' not in ticker:
            logger.warning(f"Could not fetch current price for {self.symbol}")
            return [], []
            
        current_price = ticker['last']
        logger.info(f"Current price for {self.symbol}: {current_price}")
        
        # Find support and resistance using touchpoint analysis
        support_levels, resistance_levels = find_touchpoint_levels(df, current_price)
        
        # Also get fractal levels for additional confirmation
        fractal_supports, fractal_resistances = find_price_fractals(df)
        
        # Combine the results
        all_supports = support_levels + fractal_supports
        all_resistances = resistance_levels + fractal_resistances
        
        # Remove duplicates and sort by proximity to current price
        final_supports = remove_duplicates(all_supports, tolerance=0.005)
        final_resistances = remove_duplicates(all_resistances, tolerance=0.005)
        
        # Sort by distance to current price
        final_supports = sorted(final_supports, key=lambda x: abs(current_price - x))
        final_resistances = sorted(final_resistances, key=lambda x: abs(current_price - x))
        
        # Filter out levels that are too far from current price
        max_distance = current_price * 0.15  # 15% maximum distance
        final_supports = [s for s in final_supports if current_price - s <= max_distance]
        final_resistances = [r for r in final_resistances if r - current_price <= max_distance]
        
        # Filter supports below current price and resistances above current price
        final_supports = [s for s in final_supports if s < current_price]
        final_resistances = [r for r in final_resistances if r > current_price]
        
        # Filter out levels with too low strength
        if len(final_supports) > 0 and len(final_resistances) > 0:
            logger.info(f"Found {len(final_supports)} support levels and {len(final_resistances)} resistance levels")
            logger.info(f"Support levels: {final_supports}")
            logger.info(f"Resistance levels: {final_resistances}")
        else:
            logger.warning("No strong support/resistance levels found, using default percentages")
            final_supports = [current_price * 0.97]
            final_resistances = [current_price * 1.03]
        
        self.support_levels = final_supports
        self.resistance_levels = final_resistances
        
        return final_supports, final_resistances
        
    def calculate_grid_levels(self):
        """
        Calculate grid levels based on the price range and number of grids
        
        Returns:
            list: Grid price levels
        """
        levels = []
        
        # Use identified support and resistance if available
        if self.support_levels and self.resistance_levels:
            # Filter support and resistance within our price range
            filtered_support = [s for s in self.support_levels if self.lower_price <= s <= self.upper_price]
            filtered_resistance = [r for r in self.resistance_levels if self.lower_price <= r <= self.upper_price]
            
            # Combine and sort the levels
            key_levels = sorted(filtered_support + filtered_resistance)
            
            # If we have enough key levels, use them directly
            if len(key_levels) >= self.grid_number - 1:
                # Select evenly distributed key levels
                indices = np.linspace(0, len(key_levels) - 1, self.grid_number - 1, dtype=int)
                selected_levels = [key_levels[i] for i in indices]
                
                # Add upper and lower bounds
                levels = [self.lower_price] + selected_levels + [self.upper_price]
            else:
                # We don't have enough key levels, so include them all and fill the gaps
                levels = [self.lower_price] + key_levels + [self.upper_price]
                
                # Calculate how many more levels we need
                remaining = self.grid_number + 1 - len(levels)
                
                if remaining > 0:
                    # Add remaining levels based on grid type
                    if self.grid_type == 'Arithmetic':
                        # Arithmetic grid (equal price difference)
                        filled_levels = self.generate_arithmetic_grid(self.lower_price, self.upper_price, self.grid_number + 1)
                    else:
                        # Geometric grid (equal percentage difference)
                        filled_levels = self.generate_geometric_grid(self.lower_price, self.upper_price, self.grid_number + 1)
                    
                    # Combine with the key levels
                    all_levels = sorted(set(levels + filled_levels))
                    
                    # Select the required number of levels
                    indices = np.linspace(0, len(all_levels) - 1, self.grid_number + 1, dtype=int)
                    levels = [all_levels[i] for i in indices]
        else:
            # No support/resistance levels, generate grid based on type
            if self.grid_type == 'Arithmetic':
                # Arithmetic grid (equal price difference)
                levels = self.generate_arithmetic_grid(self.lower_price, self.upper_price, self.grid_number + 1)
            else:
                # Geometric grid (equal percentage difference)
                levels = self.generate_geometric_grid(self.lower_price, self.upper_price, self.grid_number + 1)
        
        self.grid_levels = levels
        return levels
        
    def generate_arithmetic_grid(self, lower_price, upper_price, num_levels):
        """
        Generate arithmetic grid levels (equal price difference)
        
        Args:
            lower_price (float): Lower price bound
            upper_price (float): Upper price bound
            num_levels (int): Number of grid levels
            
        Returns:
            list: Grid price levels
        """
        return np.linspace(lower_price, upper_price, num_levels).tolist()
        
    def generate_geometric_grid(self, lower_price, upper_price, num_levels):
        """
        Generate geometric grid levels (equal percentage difference)
        
        Args:
            lower_price (float): Lower price bound
            upper_price (float): Upper price bound
            num_levels (int): Number of grid levels
            
        Returns:
            list: Grid price levels
        """
        return np.geomspace(lower_price, upper_price, num_levels).tolist()
        
    def create_grid_orders(self):
        """
        Create grid orders based on calculated levels
        
        Returns:
            dict: Created orders
        """
        # First calculate grid levels if not already done
        if not self.grid_levels:
            self.calculate_grid_levels()
            
        # Get available balance
        balance = self.exchange.get_balance()
        available_balance = balance.get(self.currency, {}).get('free', 0)
        
        # Calculate investment amount based on percentage
        investment_amount = available_balance * (self.investment_percentage / 100)
        
        # Calculate order size (per grid)
        order_size = investment_amount / self.grid_number
        
        orders = {}
        
        # Create buy and sell orders based on direction
        if self.direction == 'Neutral':
            # For neutral, create both buy and sell orders
            for i in range(len(self.grid_levels) - 1):
                # Buy order at lower grid level
                buy_price = self.grid_levels[i]
                buy_qty = order_size / buy_price
                
                buy_order = self.exchange.create_order(
                    self.symbol,
                    'limit',
                    'buy',
                    buy_qty,
                    buy_price
                )
                
                if buy_order:
                    orders[buy_order['id']] = buy_order
                
                # Sell order at upper grid level
                sell_price = self.grid_levels[i + 1]
                sell_qty = order_size / sell_price
                
                sell_order = self.exchange.create_order(
                    self.symbol,
                    'limit',
                    'sell',
                    sell_qty,
                    sell_price
                )
                
                if sell_order:
                    orders[sell_order['id']] = sell_order
                    
        elif self.direction == 'Long':
            # For long, create only buy orders
            for i in range(len(self.grid_levels)):
                buy_price = self.grid_levels[i]
                buy_qty = order_size / buy_price
                
                buy_order = self.exchange.create_order(
                    self.symbol,
                    'limit',
                    'buy',
                    buy_qty,
                    buy_price
                )
                
                if buy_order:
                    orders[buy_order['id']] = buy_order
                    
        elif self.direction == 'Short':
            # For short, create only sell orders
            for i in range(len(self.grid_levels)):
                sell_price = self.grid_levels[i]
                sell_qty = order_size / sell_price
                
                sell_order = self.exchange.create_order(
                    self.symbol,
                    'limit',
                    'sell',
                    sell_qty,
                    sell_price
                )
                
                if sell_order:
                    orders[sell_order['id']] = sell_order
        
        self.active_orders = orders
        return orders
        
    def start(self):
        """
        Start the grid trading bot
        
        Returns:
            bool: Success or failure
        """
        try:
            # Analyze market to find support and resistance
            self.analyze_market()
            
            # Calculate grid levels
            self.calculate_grid_levels()
            
            # Create grid orders
            self.create_grid_orders()
            
            logger.info(f"Grid bot started for {self.symbol} with {len(self.grid_levels)} levels")
            logger.info(f"Price range: {self.lower_price} - {self.upper_price}")
            logger.info(f"Grid type: {self.grid_type}")
            logger.info(f"Direction: {self.direction}")
            
            return True
            
        except Exception as e:
            logger.exception(f"Failed to start grid bot: {e}")
            return False
    
    def stop(self):
        """
        Stop the grid trading bot and cancel all orders
        
        Returns:
            bool: Success or failure
        """
        try:
            # Cancel all active orders
            for order_id in self.active_orders:
                self.exchange.cancel_order(order_id, self.symbol)
            
            logger.info(f"Grid bot stopped for {self.symbol}")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to stop grid bot: {e}")
            return False


# ----- Support & Resistance Detection Functions -----

def find_touchpoint_levels(df, current_price, min_touches=2):
    """
    Find support and resistance levels based on price touchpoints
    This method identifies levels where price has repeatedly touched and reversed
    
    Args:
        df (DataFrame): OHLCV dataframe with price data
        current_price (float): Current market price
        min_touches (int): Minimum number of touches required to confirm a level
    
    Returns:
        tuple: (support_levels, resistance_levels)
    """
    # Define the price range to look for touchpoints
    price_min = df['low'].min() * 0.995  # Add small buffer
    price_max = df['high'].max() * 1.005
    price_range = price_max - price_min
    
    # Create price bins - more bins for more granularity
    bin_size = price_range / 500  # 500 bins
    
    # Track touchpoints for each price level
    support_touches = {}  # Price level -> count of touches
    resistance_touches = {}
    
    # For each candle, check if it's a touchpoint for any level
    for i in range(1, len(df) - 1):
        # Potential support: low price with higher lows on both sides
        if df['low'].iloc[i] <= df['low'].iloc[i-1] and df['low'].iloc[i] <= df['low'].iloc[i+1]:
            # This is a local low point - potential support
            price_level = round(df['low'].iloc[i] / bin_size) * bin_size
            
            if price_level not in support_touches:
                support_touches[price_level] = 0
            support_touches[price_level] += 1
        
        # Potential resistance: high price with lower highs on both sides
        if df['high'].iloc[i] >= df['high'].iloc[i-1] and df['high'].iloc[i] >= df['high'].iloc[i+1]:
            # This is a local high point - potential resistance
            price_level = round(df['high'].iloc[i] / bin_size) * bin_size
            
            if price_level not in resistance_touches:
                resistance_touches[price_level] = 0
            resistance_touches[price_level] += 1
    
    # Also add highest highs and lowest lows as significant levels
    for i in range(len(df)):
        # Check for significant highs and lows
        high_val = df['high'].iloc[i]
        if high_val > df['high'].quantile(0.95):  # Top 5% of highs
            price_level = round(high_val / bin_size) * bin_size
            if price_level not in resistance_touches:
                resistance_touches[price_level] = 0
            resistance_touches[price_level] += 1
            
        low_val = df['low'].iloc[i]
        if low_val < df['low'].quantile(0.05):  # Bottom 5% of lows
            price_level = round(low_val / bin_size) * bin_size
            if price_level not in support_touches:
                support_touches[price_level] = 0
            support_touches[price_level] += 1
    
    # Filter for levels with sufficient touches
    strong_supports = [level for level, touches in support_touches.items() 
                       if touches >= min_touches]
    strong_resistances = [level for level, touches in resistance_touches.items() 
                          if touches >= min_touches]
    
    # Sort by strength (number of touches)
    strong_supports = sorted(strong_supports, 
                            key=lambda level: support_touches[level], 
                            reverse=True)
    strong_resistances = sorted(strong_resistances, 
                               key=lambda level: resistance_touches[level], 
                               reverse=True)
    
    # Remove levels that are too close to each other (within 0.5% of each other)
    supports = remove_duplicates(strong_supports, tolerance=0.005)
    resistances = remove_duplicates(strong_resistances, tolerance=0.005)
    
    # Check for price ceiling/floor behavior
    recent_df = df.iloc[-50:]  # Focus on recent price action
    
    # Calculate trading range boundary behavior
    ceiling = recent_df['high'].max()
    floor = recent_df['low'].min()
    if ceiling not in resistances:
        resistances.append(ceiling)
    if floor not in supports:
        supports.append(floor)
    
    # Add the all-time high and low as important levels if not already included
    all_time_high = df['high'].max()
    all_time_low = df['low'].min()
    if all_time_high not in resistances:
        resistances.append(all_time_high)
    if all_time_low not in supports:
        supports.append(all_time_low)
    
    # Filter for S&R that actually behave as S&R (price respects these levels)
    supports, resistances = validate_sr_levels(df, supports, resistances)
    
    return supports, resistances

def find_price_fractals(df, window_size=2):
    """
    Find price fractals (significant swing points with confirmation)
    
    Args:
        df (DataFrame): OHLCV dataframe
        window_size (int): Window size for fractal detection
    
    Returns:
        tuple: (support_fractals, resistance_fractals)
    """
    support_fractals = []
    resistance_fractals = []
    
    # Each price fractal has a center point with window_size candles on each side
    for i in range(window_size, len(df) - window_size):
        # Check for support fractal (low point surrounded by higher lows)
        is_support = True
        for j in range(1, window_size + 1):
            if df['low'].iloc[i] >= df['low'].iloc[i-j] or df['low'].iloc[i] >= df['low'].iloc[i+j]:
                is_support = False
                break
                
        if is_support:
            support_fractals.append(df['low'].iloc[i])
            
        # Check for resistance fractal (high point surrounded by lower highs)
        is_resistance = True
        for j in range(1, window_size + 1):
            if df['high'].iloc[i] <= df['high'].iloc[i-j] or df['high'].iloc[i] <= df['high'].iloc[i+j]:
                is_resistance = False
                break
                
        if is_resistance:
            resistance_fractals.append(df['high'].iloc[i])
    
    # Recent fractal points are more important - add extra weight by duplicating them
    if len(df) > window_size * 4:
        recent_start = -window_size * 10  # Focus on recent fractals
        
        recent_support_fractals = []
        for i in range(max(window_size, len(df) + recent_start), len(df) - window_size):
            # Check for support fractal (low point surrounded by higher lows)
            is_support = True
            for j in range(1, window_size + 1):
                if df['low'].iloc[i] >= df['low'].iloc[i-j] or df['low'].iloc[i] >= df['low'].iloc[i+j]:
                    is_support = False
                    break
                    
            if is_support:
                # Add with double weight for recent fractals
                recent_support_fractals.append(df['low'].iloc[i])
                
        recent_resistance_fractals = []
        for i in range(max(window_size, len(df) + recent_start), len(df) - window_size):
            # Check for resistance fractal (high point surrounded by lower highs)
            is_resistance = True
            for j in range(1, window_size + 1):
                if df['high'].iloc[i] <= df['high'].iloc[i-j] or df['high'].iloc[i] <= df['high'].iloc[i+j]:
                    is_resistance = False
                    break
                    
            if is_resistance:
                # Add with double weight for recent fractals
                recent_resistance_fractals.append(df['high'].iloc[i])
        
        # Combine with extra weight for recent
        support_fractals.extend(recent_support_fractals)
        resistance_fractals.extend(recent_resistance_fractals)
    
    # Remove duplicates
    support_fractals = remove_duplicates(support_fractals, tolerance=0.005)
    resistance_fractals = remove_duplicates(resistance_fractals, tolerance=0.005)
    
    return support_fractals, resistance_fractals

def validate_sr_levels(df, supports, resistances, validation_threshold=0.6):
    """
    Validate support and resistance levels by checking if price actually respects them
    
    Args:
        df (DataFrame): OHLCV dataframe
        supports (list): Potential support levels
        resistances (list): Potential resistance levels
        validation_threshold (float): Minimum percentage of times price must respect a level
    
    Returns:
        tuple: (validated_supports, validated_resistances)
    """
    validated_supports = []
    validated_resistances = []
    
    # For each support level, check how often it actually acts as support
    for level in supports:
        respect_count = 0
        test_count = 0
        
        # Check if price approaches the level from above and bounces
        for i in range(1, len(df)):
            # Price is near the support level (within 0.5%)
            if abs(df['low'].iloc[i] - level) / level < 0.005:
                test_count += 1
                # Price bounces higher after touching
                if i < len(df) - 1 and df['close'].iloc[i+1] > df['open'].iloc[i]:
                    respect_count += 1
        
        # Include level if it has been tested and respected often enough
        if test_count > 0 and respect_count / test_count >= validation_threshold:
            validated_supports.append(level)
        # Or if it hasn't been tested much but is a significant low
        elif test_count < 3 and level < df['low'].quantile(0.1):
            validated_supports.append(level)
    
    # For each resistance level, check how often it actually acts as resistance
    for level in resistances:
        respect_count = 0
        test_count = 0
        
        # Check if price approaches the level from below and reverses
        for i in range(1, len(df)):
            # Price is near the resistance level (within 0.5%)
            if abs(df['high'].iloc[i] - level) / level < 0.005:
                test_count += 1
                # Price drops lower after touching
                if i < len(df) - 1 and df['close'].iloc[i+1] < df['open'].iloc[i]:
                    respect_count += 1
        
        # Include level if it has been tested and respected often enough
        if test_count > 0 and respect_count / test_count >= validation_threshold:
            validated_resistances.append(level)
        # Or if it hasn't been tested much but is a significant high
        elif test_count < 3 and level > df['high'].quantile(0.9):
            validated_resistances.append(level)
    
    # Make sure we don't end up with empty lists
    if not validated_supports:
        validated_supports = supports[:min(3, len(supports))]
    if not validated_resistances:
        validated_resistances = resistances[:min(3, len(resistances))]
    
    return validated_supports, validated_resistances

def remove_duplicates(levels, tolerance=0.01):
    """
    Remove duplicate price levels that are within tolerance of each other
    
    Args:
        levels (list): List of price levels
        tolerance (float): Percentage tolerance for considering levels as duplicates
        
    Returns:
        list: Deduplicated list of price levels
    """
    if not levels:
        return []
        
    # Sort levels
    sorted_levels = sorted(levels)
    
    # Initialize result with the first level
    result = [sorted_levels[0]]
    
    # Check each level against the last added one
    for level in sorted_levels[1:]:
        last = result[-1]
        
        # If levels are far enough apart, add the new one
        if (level - last) / last > tolerance:
            result.append(level)
    
    return result
