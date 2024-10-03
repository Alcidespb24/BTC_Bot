from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import time
import config as cg
import df_price as dfp
import df_init as dfi
from order_summary import write_order_summary

# Initialize the trading client
client = TradingClient(cg.api_key, cg.secret_key, paper=True)

# In-memory cache with TTL (Time to Live)
cache = {
    'account_info': None,
    'account_timestamp': 0,
    'latest_quote': None,
    'quote_timestamp': 0
}

# TTL duration in seconds
TTL_DURATION = 60  # 1 minute for cache

def get_cached_account_info():
    """
    Fetch account info from the cache or API if cache is expired.
    """
    current_time = time.time()
    if cache['account_info'] is None or (current_time - cache['account_timestamp']) > TTL_DURATION:
        cache['account_info'] = dfi.get_account_info()
        cache['account_timestamp'] = current_time
    return cache['account_info']

def get_cached_crypto_quote(symbol):
    """
    Fetch the latest crypto quote from the cache or API if cache is expired.
    """
    current_time = time.time()
    if cache['latest_quote'] is None or (current_time - cache['quote_timestamp']) > TTL_DURATION:
        cache['latest_quote'] = dfp.get_latest_crypto_quote(symbol)
        cache['quote_timestamp'] = current_time
    return cache['latest_quote']

def place_order(symbol, qty, side):
    """
    Places a market order and logs the order details.
    """
    order_details = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC
    )
    order = client.submit_order(order_details)
    
    # Get the latest price
    latest_quote = get_cached_crypto_quote(symbol)
    price = latest_quote["ask_price"].iloc[0] if side == OrderSide.BUY else latest_quote["bid_price"].iloc[0]
    side_str = "Buy" if side == OrderSide.BUY else "Sell"
    
    # Log the order summary
    write_order_summary("Market Order", symbol, qty, price, side_str)
    return order

def trading_bot():
    symbol = 'BTC/USD'
    
    while True:
        # Get account and market data using cache
        account = get_cached_account_info()
        positions = client.get_all_positions()  # Assuming this doesn’t need caching since it might change rapidly.
        latest_quote = get_cached_crypto_quote(f"{symbol}")
        current_price = float(latest_quote['ask_price'].iloc[0])

        # Entry condition: Buy if price drops below a certain threshold
        if not positions:
            print('No open positions. Evaluating entry conditions...')
            # Define your entry price or condition
            entry_price = 60000  # Example threshold
            if current_price <= entry_price:
                print(f"Price is ${current_price}, which is below or equal to the entry price of ${entry_price}. Placing buy order.")
                # Calculate quantity to buy
                buying_power = float(account['buying_power'].iloc[0]) / 3
                buy_qty = buying_power / current_price
                place_order(symbol, buy_qty, OrderSide.BUY)
                entry_trade_price = current_price  # Record the price at which the trade was entered
                print('Buy order placed.')
        else:
            print('Open position detected. Evaluating exit conditions...')
            position = positions[0]  # Assuming only one position
            entry_trade_price = float(position.avg_entry_price)
            qty = float(position.qty)
            # Calculate the profit percentage
            profit_percentage = ((current_price - entry_trade_price) / entry_trade_price) * 100
            print(f"Current profit percentage: {profit_percentage:.2f}%")

            # Exit condition: Sell if profit is 5% or more
            if profit_percentage >= 5:
                print(f"Profit target reached ({profit_percentage:.2f}%). Placing sell order.")
                place_order(symbol, qty, OrderSide.SELL)
                print('Sell order placed.')
            # Stop-loss condition: Sell if loss exceeds 2%
            elif profit_percentage <= -2:
                print(f"Stop-loss triggered ({profit_percentage:.2f}%). Placing sell order.")
                place_order(symbol, qty, OrderSide.SELL)
                print('Sell order placed.')
            else:
                print('Holding position. No action taken.')

        # Wait for a specified interval before checking again
        time.sleep(300)  # Wait for 5 minutes

# Run the trading bot
trading_bot()
