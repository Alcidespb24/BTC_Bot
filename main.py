from alpaca.trading.client import TradingClient
import config as cg
import df_price as dfp
import df_init as dfi
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import conditions as c
import time

from order_summary import write_order_summary

client = TradingClient(cg.api_key, cg.secret_key, paper=True)
positions = client.get_all_positions()

def order(order_type):
    client.submit_order(order_type)

    symbol = order_details['symbol']
    qty = order_details['qty']
    price = dfp.get_latest_crypto_quote(symbol)["ask_price"].iloc[0] if order_details.side == OrderSide.BUY else dfp.get_latest_crypto_quote(symbol)["bid_price"].iloc[0]
    side = "Buy" if order_details['side'] == OrderSide.BUY else "Sell"

    write_order_summary("Market Order", symbol, qty, price, side)

def order_details():

    account = dfi.get_account_info()
    price = dfp.get_latest_crypto_quote("BTC/USD")

    buying_power = float(account['buying_power'].iloc[0]) / 3
    ask_price = float(price['ask_price'].iloc[0])

    buy_qty = buying_power / ask_price   
    
    buy_order_details = MarketOrderRequest(symbol='BTCUSD', qty=buy_qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
    order = client.submit_order(buy_order_details)

    latest_quote = dfp.get_latest_crypto_quote("BTC/USD")

    while True:
        positions = client.get_all_positions()  # Update positions within the loop

        if not positions:
            print('No positions')
            if latest_quote['bid_price'].iloc[0] < 60000:
                print("Buy condition met")
                order(buy_order_details)
                print('Buy Order placed')
                print(positions)
        elif positions:
            print('Position exists')
            if latest_quote['ask_price'].iloc[0] > 70000:
                client.close_all_positions()
                print('Sell Order placed')
                print(positions)
            else:
                print('Checking conditions to sell')
        time.sleep(300)

order_details()