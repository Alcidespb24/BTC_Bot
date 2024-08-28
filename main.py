from alpaca.trading.client import TradingClient
import config as cg
import df_price as dfp
import df_init as dfi
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import time

from order_summary import write_order_summary

# Initialize the Alpaca Trading Client
client = TradingClient(cg.api_key, cg.secret_key, paper=True)

def order(order_details):
    """Submit the order and log the details."""
    client.submit_order(order_details)

    symbol = order_details.symbol
    qty = order_details.qty
    price = dfp.get_latest_crypto_quote(symbol)["ask_price"].iloc[0] if order_details.side == OrderSide.BUY else dfp.get_latest_crypto_quote(symbol)["bid_price"].iloc[0]
    side = "Buy" if order_details.side == OrderSide.BUY else "Sell"

    write_order_summary("Market Order", symbol, qty, price, side)
    print(f"{side} order placed for {qty} units of {symbol} at {price}.")

def get_order_details():
    """Generate order details based on the account balance and latest price."""
    account = dfi.get_account_info()
    price = dfp.get_latest_crypto_quote("BTC/USD")

    buying_power = float(account['buying_power'].iloc[0]) / 3
    ask_price = float(price['ask_price'].iloc[0])

    buy_qty = buying_power / ask_price   
    
    buy_order_details = MarketOrderRequest(
        symbol='BTCUSD', 
        qty=buy_qty, 
        side=OrderSide.BUY, 
        time_in_force=TimeInForce.GTC
    )
    
    return buy_order_details  # Return the order details for further use

def close_all_positions():
    """Close all open positions and verify they are closed."""
    client.close_all_positions()
    time.sleep(5)  # Wait for a few seconds to allow the API to update

    positions = client.get_all_positions()
    if not positions:
        print("All positions successfully closed.")
    else:
        print(f"Failed to close all positions, current positions: {positions}")

def trading_loop():
    """Main trading loop to check conditions and place orders."""
    while True:
        positions = client.get_all_positions()  # Update positions within the loop
        latest_quote = dfp.get_latest_crypto_quote("BTC/USD")  # Get the latest quote

        if not positions:  # No open positions
            if latest_quote['bid_price'].iloc[0] < 60000:
                print("Buy condition met")
                buy_order_details = get_order_details()  # Get the order details
                order(buy_order_details)  # Place the buy order
            else:
                print("There are no positions open, but conditions have not been met")
        else:  # Positions are open
            print("There are positions open: " + str(positions))
            if latest_quote['ask_price'].iloc[0] > 70000:
                print('Sell condition met')
                close_all_positions()  # Close all positions and verify
            else:
                print('No condition met')
        
        time.sleep(300)  # Wait for 5 minutes before checking conditions again

# Start the trading loop
trading_loop()
