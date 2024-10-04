# bot.py

import asyncio
import logging
import os
import signal
from functools import partial
from threading import Lock

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.models import Order
from alpaca.data.live import CryptoDataStream

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

# In-memory state shared with the web app
bot_state = {
    'status': 'Initializing',
    'position': None,
    'latest_price': None,
    'account_balance': None,
    'pnl': None,
    'pnl_history': [],
    'execute_trade': False
}

state_lock = Lock()

# To handle graceful shutdowns
stop_event = asyncio.Event()

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
        order: Order = await asyncio.to_thread(client.submit_order, order_details)
        price = latest_price
        side_str = "Buy" if side == OrderSide.BUY else "Sell"
        logger.info(f"{side_str} order placed: {qty:.6f} {symbol} at ${price:.2f}")
        return order
    except Exception as e:
        logger.error(f"Error placing {side.name.lower()} order: {e}")
        return None

def calculate_current_pnl():
    """
    Calculates the current profit and loss.
    """
    global position, latest_price
    if position and latest_price:
        entry_price = position['entry_price']
        qty = position['qty']
        pnl = (latest_price - entry_price) * qty
        return pnl
    return 0.0

async def on_quote(data, config, config_lock, state_lock):
    """
    Callback function to handle price updates from the WebSocket.
    """
    global latest_price, position, bot_running
    if not bot_running:
        logger.info("Bot is stopped. Exiting on_quote.")
        return

    latest_price = float(data.bid_price)
    logger.info(f"Received price update: {SYMBOL} at ${latest_price:.2f}")

    # Update shared state
    with state_lock:
        bot_state['latest_price'] = latest_price

    try:
        # Access the dynamic ENTRY_THRESHOLD
        async with config_lock:
            entry_threshold = config.get('ENTRY_THRESHOLD', 60000)  # Default if not set

        # Check if manual trade execution is requested
        with state_lock:
            execute_trade = bot_state.get('execute_trade', False)
            if execute_trade:
                bot_state['execute_trade'] = False  # Reset the flag
                logger.info("Manual trade execution requested.")
                # Place buy order regardless of entry threshold
                if position is None:
                    await enter_position()
                else:
                    logger.info("Already in position. Manual trade execution ignored.")

        if position is None:
            with state_lock:
                bot_state['status'] = 'Waiting to Enter Trade'

            if latest_price <= entry_threshold:
                logger.info(f"Price ${latest_price:.2f} <= entry threshold ${entry_threshold:.2f}. Evaluating buy opportunity.")
                await enter_position()
        else:
            with state_lock:
                bot_state['status'] = 'In Position'

            entry_price = position['entry_price']
            profit_percentage = ((latest_price - entry_price) / entry_price) * 100
            logger.info(f"Current profit: {profit_percentage:.2f}%")
            with state_lock:
                bot_state['pnl'] = calculate_current_pnl()

            # Record P/L history
            with state_lock:
                bot_state['pnl_history'].append({
                    'time': asyncio.get_event_loop().time(),
                    'pnl': bot_state['pnl']
                })
                # Limit the history to the last 1000 entries
                bot_state['pnl_history'] = bot_state['pnl_history'][-1000:]

            if profit_percentage >= PROFIT_TARGET:
                logger.info(f"Profit target reached ({profit_percentage:.2f}%). Placing sell order.")
                await exit_position(reason='Profit target reached')
            elif profit_percentage <= STOP_LOSS:
                logger.info(f"Stop-loss triggered ({profit_percentage:.2f}%). Placing sell order.")
                await exit_position(reason='Stop-loss triggered')
            else:
                logger.info("No action taken. Holding position.")
    except Exception as e:
        logger.error(f"Error in trading logic: {e}")

async def enter_position():
    global position, latest_price
    try:
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
            with state_lock:
                bot_state['position'] = position
        else:
            logger.error("Failed to enter position.")
    except Exception as e:
        logger.error(f"Error entering position: {e}")

async def exit_position(reason=''):
    global position, latest_price
    if position is None:
        logger.info("No position to exit.")
        return
    try:
        qty = position['qty']
        order = await place_order(SYMBOL, qty, OrderSide.SELL)
        if order:
            logger.info(f"Exited position: Sold {qty:.6f} {SYMBOL} at ${latest_price:.2f}. Reason: {reason}")
            position = None
            with state_lock:
                bot_state['position'] = None
        else:
            logger.error("Failed to exit position.")
    except Exception as e:
        logger.error(f"Error exiting position: {e}")

async def start_price_stream(config, config_lock):
    """
    Starts the WebSocket stream to receive real-time price updates with exponential backoff.
    """
    crypto_stream = CryptoDataStream(API_KEY, SECRET_KEY)
    callback = partial(on_quote, config=config, config_lock=config_lock, state_lock=state_lock)
    await crypto_stream.subscribe_quotes(callback, SYMBOL)

    backoff = 1  # Start with a 1-second delay
    max_backoff = 60  # Maximum delay of 60 seconds
    max_retries = 10  # Maximum number of reconnection attempts
    retries = 0

    while bot_running and retries < max_retries:
        try:
            logger.info("Starting price stream...")
            await crypto_stream._connect()
            await crypto_stream._handle_messages()
        except Exception as e:
            logger.error(f"Error in price stream: {e}. Backing off for {backoff} seconds.")
            await asyncio.sleep(backoff)
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
                with state_lock:
                    bot_state['position'] = position
                break
    except Exception as e:
        logger.error(f"Error updating position state: {e}")

async def update_account_balance():
    """
    Periodically updates the account balance.
    """
    while bot_running:
        try:
            account = await asyncio.to_thread(client.get_account)
            cash = float(account.cash)
            with state_lock:
                bot_state['account_balance'] = cash
            await asyncio.sleep(60)  # Update every 60 seconds
        except Exception as e:
            logger.error(f"Error updating account balance: {e}")
            await asyncio.sleep(60)

async def main(config, config_lock):
    global bot_running
    bot_running = True
    logger.info("Trading bot is running.")

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_bot)

    # Initialize position state
    await update_position_state()

    # Start the price stream and account updater concurrently
    await asyncio.gather(
        start_price_stream(config, config_lock),
        update_account_balance(),
    )

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