import asyncio
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from alpaca.data.live import CryptoDataStream
import config as cg
from order_summary import write_order_summary

# Initialize the trading client
client = TradingClient(cg.api_key, cg.secret_key, paper=True)

# Global variables to hold the latest price and position state
latest_price = None
position = None

# Set your trading parameters
SYMBOL = 'BTC/USD'  # Use 'BTC/USD' for the data stream
ENTRY_THRESHOLD = 60000  # Example entry price threshold
PROFIT_TARGET = 5        # Profit target in percentage
STOP_LOSS = -2           # Stop loss in percentage

async def place_order(symbol, qty, side):
    """
    Places a market order and logs the order details.
    """
    global latest_price
    try:
        order_details = MarketOrderRequest(
            symbol=symbol.replace('/', ''),  # Remove '/' for trading API
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC
        )
        # Run the blocking submit_order in a separate thread
        order = await asyncio.to_thread(client.submit_order, order_details)

        # Log the order summary
        price = latest_price
        side_str = "Buy" if side == OrderSide.BUY else "Sell"
        write_order_summary("Market Order", symbol, qty, price, side_str)
        print(f"{side_str} order placed at ${price} for {qty} {symbol}.")

        return order
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

async def on_quote(data):
    """
    Callback function to handle price updates from the WebSocket.
    """
    global latest_price, position

    latest_price = float(data.bid_price)  # Use bid_price or ask_price as appropriate
    print(f"Received price update: {SYMBOL} at ${latest_price}")

    # Trading logic
    try:
        if position is None:
            # Entry condition: Buy if price drops below the threshold
            if latest_price <= ENTRY_THRESHOLD:
                print(f"Price ${latest_price} <= entry threshold ${ENTRY_THRESHOLD}. Evaluating buy opportunity.")
                # Get account info once before buying
                account = await asyncio.to_thread(client.get_account)
                buying_power = float(account.buying_power) / 3
                qty = buying_power / latest_price
                order = await place_order(SYMBOL, qty, OrderSide.BUY)
                if order:
                    # Update the position state
                    position = {
                        'entry_price': latest_price,
                        'qty': qty
                    }
        else:
            # Calculate profit percentage
            entry_price = position['entry_price']
            profit_percentage = ((latest_price - entry_price) / entry_price) * 100
            print(f"Current profit: {profit_percentage:.2f}%")

            # Exit conditions
            if profit_percentage >= PROFIT_TARGET:
                print(f"Profit target reached ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    # Reset the position state
                    position = None
            elif profit_percentage <= STOP_LOSS:
                print(f"Stop-loss triggered ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    # Reset the position state
                    position = None
                else:
                    print("Sell order failed.")
            else:
                print("No action taken. Holding position.")
    except Exception as e:
        print(f"Error in trading logic: {e}")

async def start_price_stream():
    """
    Starts the WebSocket stream to receive real-time price updates.
    """
    crypto_stream = CryptoDataStream(cg.api_key, cg.secret_key)

    # Subscribe to the crypto quote stream
    crypto_stream.subscribe_quotes(on_quote, SYMBOL)

    try:
        print("Starting price stream...")
        await crypto_stream._run_forever()
    except Exception as e:
        print(f"Error in price stream: {e}")
    finally:
        await crypto_stream.close()

async def update_position_state():
    """
    Initializes the position state based on current holdings.
    """
    global position
    try:
        positions = await asyncio.to_thread(client.get_all_positions)
        for pos in positions:
            if pos.symbol == SYMBOL.replace('/', ''):
                position = {
                    'entry_price': float(pos.avg_entry_price),
                    'qty': float(pos.qty)
                }
                print(f"Existing position detected: {position}")
                break
    except Exception as e:
        print(f"Error updating position state: {e}")

async def main():
    # Initialize position state
    await update_position_state()

    # Start the price stream
    await start_price_stream()

if __name__ == "__main__":
    asyncio.run(main())
