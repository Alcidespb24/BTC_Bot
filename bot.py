# bot.py

import asyncio
import logging
import os
from functools import partial
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.live import CryptoDataStream
from alpaca.trading.models import Order
import signal

# Access environment variables for API keys
API_KEY = os.environ.get('API_KEY')
SECRET_KEY = os.environ.get('SECRET_KEY')

# Initialize the trading client
client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# Global variables
latest_price = None
position = None

# Set your trading parameters
SYMBOL = 'BTC/USD'         # Use 'BTC/USD' for the data stream
PROFIT_TARGET = 5          # Profit target in percentage
STOP_LOSS = -2             # Stop loss in percentage

# Bot control flag
bot_running = False

# Configure a dedicated logger for the bot
logger = logging.getLogger('bot')
logger.setLevel(logging.INFO)  # Set to INFO to capture relevant messages
logger.propagate = False      # Prevent log messages from being passed to the root logger

# To handle graceful shutdowns
stop_event = asyncio.Event()

# Add imports
from alpaca.trading.models import Order

# Modify place_order function
async def place_order(symbol, qty, side):
    global latest_price
    try:
        order_details = MarketOrderRequest(
            symbol=symbol.replace('/', ''),  # Remove '/' for trading API
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC
        )
        # Place the order asynchronously
        order: Order = await asyncio.to_thread(client.submit_order, order_details)
        price = latest_price
        side_str = "Buy" if side == OrderSide.BUY else "Sell"
        logger.info(f"{side_str} order placed: {qty:.6f} {symbol} at ${price:.2f}")
        return order
    except Exception as e:
        logger.error(f"Error placing {side_str.lower()} order: {e}")
        return None


async def on_quote(data, config, config_lock):
    """
    Callback function to handle price updates from the WebSocket.
    """
    global latest_price, position, bot_running
    if not bot_running:
        logger.info("Bot is stopped. Exiting on_quote.")
        return

    latest_price = float(data.bid_price)
    logger.info(f"Received price update: {SYMBOL} at ${latest_price:.2f}")
    try:
        # Access the dynamic ENTRY_THRESHOLD
        async with config_lock:
            entry_threshold = config.get('ENTRY_THRESHOLD', 60000)  # Default if not set

        if position is None:
            if latest_price <= entry_threshold:
                logger.info(f"Price ${latest_price:.2f} <= entry threshold ${entry_threshold:.2f}. Evaluating buy opportunity.")
                account = await asyncio.to_thread(client.get_account)
                buying_power = float(account.buying_power) / 3
                qty = buying_power / latest_price
                logger.info(f"Calculated order quantity: {qty:.6f}")
                order = await place_order(SYMBOL, qty, OrderSide.BUY)
                if order:
                    position = {
                        'entry_price': latest_price,
                        'qty': qty
                    }
                    logger.info(f"Entered position: Bought {qty:.6f} {SYMBOL} at ${latest_price:.2f}")
        else:
            entry_price = position['entry_price']
            profit_percentage = ((latest_price - entry_price) / entry_price) * 100
            logger.info(f"Current profit: {profit_percentage:.2f}%")
            if profit_percentage >= PROFIT_TARGET:
                logger.info(f"Profit target reached ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    position = None
                    logger.info(f"Exited position: Sold {qty:.6f} {SYMBOL} at ${latest_price:.2f}")
            elif profit_percentage <= STOP_LOSS:
                logger.info(f"Stop-loss triggered ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    position = None
                    logger.info(f"Exited position: Sold {qty:.6f} {SYMBOL} at ${latest_price:.2f} due to stop-loss")
                else:
                    logger.error("Sell order failed.")
            else:
                logger.info("No action taken. Holding position.")
    except Exception as e:
        logger.error(f"Error in trading logic: {e}")

async def start_price_stream(config, config_lock):
    """
    Starts the WebSocket stream to receive real-time price updates with exponential backoff.
    """
    crypto_stream = CryptoDataStream(API_KEY, SECRET_KEY)
    callback = partial(on_quote, config=config, config_lock=config_lock)
    crypto_stream.subscribe_quotes(callback, SYMBOL)
    
    backoff = 1  # Start with a 1-second delay
    max_backoff = 60  # Maximum delay of 60 seconds
    max_retries = 10  # Maximum number of reconnection attempts
    retries = 0
    
    while bot_running and retries < max_retries:
        try:
            logger.info("Starting price stream...")
            await crypto_stream._run_forever()
        except ValueError as ve:
            logger.error(f"ValueError encountered: {ve}. Backing off for {backoff} seconds.")
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Backing off for {backoff} seconds.")
        
        # Wait before attempting to reconnect
        await asyncio.sleep(backoff)
        
        # Exponential backoff
        backoff = min(backoff * 2, max_backoff)
        retries += 1
    
    if retries >= max_retries:
        logger.error("Maximum reconnection attempts reached. Bot will stop.")
        bot_running = False
    
    await crypto_stream.close()
    logger.info("Price stream closed.")

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
                logger.info(f"Existing position detected: {position}")
                break
    except Exception as e:
        logger.error(f"Error updating position state: {e}")

async def main(config, config_lock):
    global bot_running
    bot_running = True
    logger.info("Trading bot is running.")

    # Initialize position state
    await update_position_state()

    # Start the price stream
    await start_price_stream(config, config_lock)

def stop_bot():
    global bot_running
    bot_running = False
    logger.info("Bot has been stopped.")

if __name__ == "__main__":
    # This block allows the bot to be run independently if needed
    import sys

    # Define default config and config_lock for standalone execution
    config = {
        'ENTRY_THRESHOLD': 60000  # Default value
    }
    config_lock = asyncio.Lock()

    if len(sys.argv) > 1 and sys.argv[1] == 'run':
        # Example usage: python bot.py run
        # Load configuration from a file or environment variables as needed
        # For simplicity, we'll use default config
        asyncio.run(main(config, config_lock))