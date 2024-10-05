# bot.py

import asyncio
import logging
import os
import signal
from functools import partial

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.models import Order
from alpaca.data.live import CryptoDataStream

import redis
import json
import ssl

# Access environment variables for API keys
API_KEY = os.environ.get('API_KEY')
SECRET_KEY = os.environ.get('SECRET_KEY')

# Initialize the trading client
client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# Configure logging
logger = logging.getLogger('bot')
logger.setLevel(logging.INFO)

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Global variables
latest_price = None
position = None

# Set your trading parameters
SYMBOL = 'BTC/USD'         # Use 'BTC/USD' for the data stream
PROFIT_TARGET = 5          # Profit target in percentage
STOP_LOSS = -2             # Stop loss in percentage

# Bot control flag
bot_running = False

# Shared configuration dictionary
config = {
    'ENTRY_THRESHOLD': 60000  # Default value
}

# To handle graceful shutdowns
stop_event = asyncio.Event()

# Redis connection
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

try:
    if REDIS_URL.startswith('rediss://'):
        # SSL/TLS connection to Heroku Redis
        redis_client = redis.Redis.from_url(
            REDIS_URL,
            ssl=True,
            ssl_cert_reqs=ssl.CERT_NONE  # Disables SSL certificate verification
        )
    else:
        # Non-SSL connection (local development)
        redis_client = redis.Redis.from_url(REDIS_URL)

    # Test the Redis connection
    redis_client.ping()
    logger.info("Connected to Redis successfully.")
except Exception as e:
    logger.error(f"Redis connection error: {e}")
    redis_client = None  # Set redis_client to None to prevent further errors

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

async def on_quote(data, config, config_lock):
    """
    Callback function to handle price updates from the WebSocket.
    """
    global latest_price, position, bot_running, redis_client
    if not bot_running:
        logger.info("Bot is stopped. Exiting on_quote.")
        return

    latest_price = float(data.bid_price)
    logger.info(f"Received price update: {SYMBOL} at ${latest_price:.2f}")

    # Update Redis with latest price
    if redis_client:
        redis_client.hset('bot_state', 'latest_price', latest_price)

    try:
        # Read the ENTRY_THRESHOLD from Redis
        if redis_client:
            entry_threshold = redis_client.hget('bot_config', 'ENTRY_THRESHOLD')
            if entry_threshold is not None:
                entry_threshold = float(entry_threshold)
            else:
                entry_threshold = config.get('ENTRY_THRESHOLD', 60000)  # Default if not set
        else:
            entry_threshold = config.get('ENTRY_THRESHOLD', 60000)

        if position is None:
            if redis_client:
                redis_client.hset('bot_state', 'status', 'Waiting to Enter Trade')
            logger.info("No current position.")
            if latest_price <= entry_threshold:
                logger.info(f"Price ${latest_price:.2f} <= entry threshold ${entry_threshold:.2f}. Evaluating buy opportunity.")
                await enter_position()
            else:
                logger.info("Price above entry threshold. Waiting.")
        else:
            if redis_client:
                redis_client.hset('bot_state', 'status', 'In Position')
            entry_price = position['entry_price']
            profit_percentage = ((latest_price - entry_price) / entry_price) * 100
            logger.info(f"Current profit: {profit_percentage:.2f}%")

            # Update PnL in Redis
            pnl = calculate_current_pnl()
            if redis_client:
                redis_client.hset('bot_state', 'pnl', pnl)

            # Update position in Redis
            if redis_client:
                redis_client.hset('bot_state', 'position', json.dumps(position))

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
    global position, latest_price, redis_client
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
            # Update position in Redis
            if redis_client:
                redis_client.hset('bot_state', 'position', json.dumps(position))
        else:
            logger.error("Failed to enter position.")
    except Exception as e:
        logger.error(f"Error entering position: {e}")

async def exit_position(reason=''):
    global position, latest_price, redis_client
    if position is None:
        logger.info("No position to exit.")
        return
    try:
        qty = position['qty']
        order = await place_order(SYMBOL, qty, OrderSide.SELL)
        if order:
            logger.info(f"Exited position: Sold {qty:.6f} {SYMBOL} at ${latest_price:.2f}. Reason: {reason}")
            position = None
            # Remove position from Redis
            if redis_client:
                redis_client.hdel('bot_state', 'position')
                redis_client.hset('bot_state', 'status', 'Waiting to Enter Trade')
        else:
            logger.error("Failed to exit position.")
    except Exception as e:
        logger.error(f"Error exiting position: {e}")

async def start_price_stream(config, config_lock):
    global bot_running
    bot_running = True  # Ensure bot_running is set to True
    crypto_stream = CryptoDataStream(API_KEY, SECRET_KEY)
    callback = partial(on_quote, config=config, config_lock=config_lock)
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
    global position, redis_client
    try:
        positions = await asyncio.to_thread(client.get_all_positions)
        for pos in positions:
            if pos.symbol == SYMBOL.replace('/', ''):
                position = {
                    'entry_price': float(pos.avg_entry_price),
                    'qty': float(pos.qty)
                }
                logger.info(f"Existing position detected: {position}")
                # Update position in Redis
                if redis_client:
                    redis_client.hset('bot_state', 'position', json.dumps(position))
                break
    except Exception as e:
        logger.error(f"Error updating position state: {e}")

async def update_account_balance():
    global bot_running, redis_client
    while bot_running:
        try:
            account = await asyncio.to_thread(client.get_account)
            cash = float(account.cash)
            # Update Redis
            if redis_client:
                redis_client.hset('bot_state', 'account_balance', cash)
            await asyncio.sleep(60)  # Update every 60 seconds
        except Exception as e:
            logger.error(f"Error updating account balance: {e}")
            await asyncio.sleep(60)

async def listen_for_commands():
    global bot_running, redis_client
    if redis_client is None:
        logger.error("Redis client is not available. Command listener will not start.")
        return
    pubsub = redis_client.pubsub()
    pubsub.subscribe('bot_commands')
    while bot_running:
        message = pubsub.get_message()
        if message and message['type'] == 'message':
            command = message['data'].decode('utf-8')
            if command == 'execute_trade':
                logger.info("Received execute_trade command from web app.")
                # Implement logic to execute trade immediately
                if position is None:
                    await enter_position()
                else:
                    logger.info("Already in position. Ignoring execute_trade command.")
        await asyncio.sleep(0.1)

async def main(config, config_lock):
    logger.info("Trading bot is running.")

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_bot)

    # Initialize position state
    await update_position_state()

    # Start the price stream, account updater, and command listener
    tasks = [
        start_price_stream(config, config_lock),
        update_account_balance(),
    ]

    if redis_client:
        tasks.append(listen_for_commands())
    else:
        logger.error("Redis client is not available. Skipping command listener.")

    await asyncio.gather(*tasks)

def stop_bot():
    global bot_running
    bot_running = False
    logger.info("Bot has been stopped.")

if __name__ == "__main__":
    import sys

    config_lock = asyncio.Lock()

    if len(sys.argv) > 1 and sys.argv[1] == 'run':
        asyncio.run(main(config, config_lock))